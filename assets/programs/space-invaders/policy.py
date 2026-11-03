"""Space Invaders RAM policy: aim at invader columns, fire when aligned, dodge enemy bullets.

RAM map (verified by probing, see NOTES.md):
  28  player x (35..117), moves 2 px/step
  26  x of the leftmost alive invader column; column k is at ram[26] + 16*(k - kmin)
  16  descent counter; missile y at which row r is hit = 62 + ram[16] - 9*r
  18..23  invader rows bitmask, 18 = bottom row (5 pts) .. 23 = top row (30 pts); bit k = column k
  30  mystery ship x (1..151, 1 px/step), 180 when absent
  81/83, 82/84  enemy bullets (y, x); y=246 inactive; fall 2 px/step
  85  player missile y (>= 200 = free), launched at ~89 and rising 4 px/step
  73  lives
Actions: 0 NOOP, 1 FIRE, 2 RIGHT, 3 LEFT, 4 RIGHTFIRE, 5 LEFTFIRE
"""

import math
from collections import deque

import numpy as np

# player and dodging
PX_MIN, PX_MAX = 35, 117
PLAYER_SPEED = 2
BULLET_SPEED = 2
HORIZON = 14                    # dodge look-ahead (steps)
BOX_SAFE = (84, 96, -1, 7)      # (y_lo, y_hi, dx_lo, dx_hi): bullet y and bx - px that hit the player
BOX_LAST = (84, 96, -1, 10)     # extra room for a repeated movement on the last life
BOX_CORE = (86, 94, 1, 5)       # tighter box used only when pinned (accepts some risk)
STUCK_LIMIT = 20
WAVE_WAIT_LIMIT = 20

# formation and aiming
COL_SPACING = 16
EX_LEFT, EX_RIGHT = 23, 130     # ram[26] bounces in [EX_LEFT, EX_RIGHT - 16*(kmax-kmin)]
ROW_Y0, ROW_DY = 62, 9
MISSILE_Y0, MISSILE_SPEED = 89, 4
HIT_LO, HIT_HI = -3, 2          # fire when px - predicted column x is in this window
VEL_WINDOW = 8                  # formation speed = mean |d ram[26]| over this many steps
JUMP = 8                        # larger ram[26] changes are re-references, not motion
FAST_SPEED = 1.75                # fast phase: clamp-then-reverse bounces, go to earliest intercept
INTERCEPT_HORIZON = 60
IDLE_FIRE = 1000                # fire anyway after this many free-missile steps without a shot

# column choice (slow phase): lowest cost = distance + penalties
REACH_SLACK = 2
UNREACHABLE_COST = 1000
INNER_COST = 200
DANGER_LEVEL = 18               # landing is near when ram[16] - 9*lowest_row reaches this
DANGER_COST = 500
EDGE_LOW_COST = 60              # lowest row at landing level: prefer the edge column holding it
DANGER_STEPS_PER_KILL = 15
DANGER_MARGIN = 40
BOUNCE_SPEED_FLOOR = 1.0        # avoid optimistic estimates between formation movement bursts

# mystery ship
UFO_IDLE = 180
UFO_LEAD = {1: 19, -1: -21}     # fire when px - ufo_x = UFO_LEAD[dir] (missile needs 19 steps);
UFO_TOL = 2                     # measured hits: dir +1 at 16..22, dir -1 at -24..-18
UFO_FAR = 30

# (move, fire) -> action
ACTIONS = {(0, False): 0, (0, True): 1, (1, False): 2, (-1, False): 3, (1, True): 4, (-1, True): 5}


class Policy:
    def __init__(self, spec: dict):
        self.reset()

    def reset(self) -> None:
        self.ufo_prev = UFO_IDLE
        self.ufo_dir = 0
        self.ex_hist = deque(maxlen=VEL_WINDOW + 1)
        self.vel = (0.0, 0)
        self.idle = 0
        self.stuck = 0
        self.wave_wait = 0

    # ---------------------------------------------------------------- dodging
    @staticmethod
    def _danger(o, box):
        """Per future step s = 1..HORIZON: list of (lo, hi) player-x intervals hit by a bullet."""
        ylo, yhi, dlo, dhi = box
        bullets = [(int(o[ys]), int(o[xs])) for ys, xs in ((81, 83), (82, 84)) if o[ys] < 120]
        return [[(bx - dhi, bx - dlo) for by, bx in bullets if ylo <= by + BULLET_SPEED * s <= yhi]
                for s in range(1, HORIZON + 1)]

    @staticmethod
    def _rollout(px, target, danger, m1, j, m2):
        """Move m1 for j steps, then m2. Return (hit step or HORIZON+1, sum |x - target| before hit)."""
        p, cost = px, 0
        for s in range(1, HORIZON + 1):
            p = min(max(p + PLAYER_SPEED * (m1 if s <= j else m2), PX_MIN), PX_MAX)
            if any(lo <= p <= hi for lo, hi in danger[s - 1]):
                return s, cost
            cost += abs(p - target)
        return HORIZON + 1, cost

    def _plan(self, px, target, danger):
        """Return first move and hit step for the safest, then closest, two-segment plan."""
        best_key, best_move = None, 0
        for m1 in (-1, 0, 1):
            for j in range(1, HORIZON + 1):
                for m2 in ((-1, 0, 1) if j < HORIZON else (m1,)):
                    hit, cost = self._rollout(px, target, danger, m1, j, m2)
                    key = (-hit, cost)
                    if best_key is None or key < best_key:
                        best_key, best_move = key, m1
        return best_move, -best_key[0]

    # ---------------------------------------------------------------- aiming
    def _ex_velocity(self):
        """(speed px/step, direction) of the formation from recent ram[26] changes."""
        h = list(self.ex_hist)
        diffs = [b - a for a, b in zip(h, h[1:])]
        jumps = [i for i, d in enumerate(diffs) if abs(d) > JUMP]  # wave reset / re-reference
        if jumps:
            diffs = diffs[jumps[-1] + 1:]
        if not diffs:
            return 0.0, 0
        speed = sum(abs(d) for d in diffs) / len(diffs)
        moving = [d for d in diffs if d != 0]
        direction = (1 if moving[-1] > 0 else -1) if moving else 0
        return speed, direction

    def _predict_ex(self, ex, T, width):
        """Predict ram[26] after T steps. Fast formations stop at the edge, then reverse (measured);
        slow ones are modelled as reflecting."""
        speed, direction = self.vel
        lo, hi = EX_LEFT, EX_RIGHT - width
        if direction == 0 or T <= 0 or hi <= lo:
            return float(ex)
        if speed >= FAST_SPEED:
            x, t, d = float(ex), float(T), direction
            while True:
                edge = hi if d > 0 else lo
                te = max(0, math.ceil(abs(edge - x) / speed - 1e-9))
                if te >= t:
                    return min(max(x + d * speed * t, lo), hi)
                t -= te
                x, d = float(edge), -d
        span = hi - lo
        y = (ex + direction * speed * T - lo) % (2 * span)
        return lo + (2 * span - y if y > span else y)

    def _bounce_soon(self, lows, rlow, ex, width):
        """True if the next edge bounce may come before we can clear the lowest row."""
        speed, direction = self.vel
        dist = (EX_RIGHT - width - ex) if direction >= 0 else (ex - EX_LEFT)
        t_bounce = max(dist, 0) / max(speed, BOUNCE_SPEED_FLOOR)
        n_low = sum(1 for r in lows.values() if r == rlow)
        return t_bounce < DANGER_STEPS_PER_KILL * n_low + DANGER_MARGIN

    def _target(self, o, px):
        """Return target, strict/wide shot alignment, and landing danger."""
        lows = {}  # column -> lowest alive row
        for k in range(6):
            for r in range(6):
                if o[18 + r] >> k & 1:
                    lows[k] = r
                    break
        if not lows:
            return px, False, False, False
        ex = int(o[26])
        kmin, kmax = min(lows), max(lows)
        width = COL_SPACING * (kmax - kmin)
        rlow = min(lows.values())
        low_level = int(o[16]) - ROW_DY * rlow >= DANGER_LEVEL
        danger = low_level and self._bounce_soon(lows, rlow, ex, width)

        cols = []  # (column, lowest row, x offset from ex, missile flight steps, predicted x at impact)
        for k, low in lows.items():
            hit_y = ROW_Y0 + int(o[16]) - ROW_DY * low
            T = max(0.0, (MISSILE_Y0 - hit_y) / MISSILE_SPEED)
            if low_level and self.vel[0] >= FAST_SPEED:
                T += 0.5  # account for delayed launches against fast, low invaders
            off = COL_SPACING * (k - kmin)
            cols.append((k, low, off, T, self._predict_ex(ex, T, width) + off))
        strict = any(HIT_LO <= px - aim <= HIT_HI for *_, aim in cols)
        # The extra left-side window is usable only for a rightward move.
        wide = strict or (self.stuck > 5 and low_level and
                          any(HIT_LO - 2 <= px - aim <= HIT_HI for *_, aim in cols))

        if self.vel[0] >= FAST_SPEED:
            # walk to the earliest (tau) predicted firing point reachable in time, then wait there
            best_tau, best = INTERCEPT_HORIZON, px
            for _, _, off, T, _ in cols:
                for tau in range(1, best_tau):
                    a = self._predict_ex(ex, T + tau, width) + off
                    if PX_MIN <= a <= PX_MAX and abs(a - px) <= PLAYER_SPEED * tau:
                        best_tau, best = tau, a
                        break
            return best, strict, wide, danger

        best, bestd = None, 1e9
        for k, low, _, _, aim in cols:
            x = min(max(aim, PX_MIN), PX_MAX)
            d = abs(x - px)
            if abs(x - aim) > REACH_SLACK:   # column outside the player's range right now
                d += UNREACHABLE_COST
            if danger:
                if low != rlow:              # must clear the lowest row before the next descent
                    d += DANGER_COST
            elif k != kmin and k != kmax:    # outer columns first: narrow formation descends slower
                d += INNER_COST
            elif low_level and low != rlow:  # of the two edges, prefer the one holding the lowest row
                d += EDGE_LOW_COST
            if d < bestd:
                best, bestd = x, d
        return best, strict, wide, danger

    def _ufo_aim(self, o):
        """Player x from which a shot hits the mystery ship, or None (absent / out of reach)."""
        u = int(o[30])
        prev, self.ufo_prev = self.ufo_prev, u
        if u == UFO_IDLE or prev == UFO_IDLE:
            self.ufo_dir = 0
            return None
        if u != prev and abs(u - prev) <= 2:
            self.ufo_dir = 1 if u > prev else -1
        if self.ufo_dir == 0:
            return None
        aim = u + UFO_LEAD[self.ufo_dir]
        return aim if PX_MIN <= aim <= PX_MAX else None

    # ---------------------------------------------------------------- act
    def act(self, obs, info: dict) -> int:
        o = np.asarray(obs).astype(int)
        px = int(o[28])
        self.ex_hist.append(int(o[26]))
        self.vel = self._ex_velocity()
        target, strict, wide, landing = self._target(o, px)
        ufo = self._ufo_aim(o)
        if ufo is not None and not landing:
            target = ufo
        want = 1 if target > px + 1 else -1 if target < px - 1 else 0
        missile_free = o[85] >= 200

        # Risk a tight-box crossing only when pinned away from the left wall,
        # a landing is near, and a spare life remains.
        if self.stuck > STUCK_LIMIT and o[73] >= 2 and landing and px > 43:
            box = BOX_CORE
        elif o[73] == 1:
            box = BOX_LAST
        else:
            box = BOX_SAFE
        danger = self._danger(o, box)
        if self._rollout(px, target, danger, want, HORIZON, want)[0] > HORIZON:
            move = want
        else:
            move, hit = self._plan(px, target, danger)
            # When the last-life margin says every path is about to be hit,
            # retry with the normal box to find a possible escape.
            if o[73] == 1 and hit <= 2:
                move, _ = self._plan(px, target, self._danger(o, BOX_SAFE))
        aligned = wide if move == 1 else strict
        if ufo is not None and not landing:
            # Still take an aligned invader shot if the UFO firing point is far away.
            aligned = abs(px - ufo) <= UFO_TOL or (aligned and abs(px - ufo) > UFO_FAR)
        if want != 0 and move != want and missile_free and not aligned:
            self.stuck += 1
        else:
            self.stuck = max(0, self.stuck - 2)

        fire = False
        if missile_free:
            self.idle += 1
            fire = aligned or self.idle > IDLE_FIRE
            if fire:
                self.idle = 0
        # At the beginning of low waves, let an initial bullet just to the
        # right pass before moving into its stream. Abort the wait if staying
        # itself is threatened or the first bullet is elsewhere.
        if o[42] == 1 and o[16] >= 20 and o[17] == 36:
            self.wave_wait = 1
            return 0
        if self.wave_wait and o[42] == 0:
            self.wave_wait += 1
            bullets = [(int(o[y]), int(o[x]) - px) for y, x in ((81, 83), (82, 84))
                       if o[y] < 120]
            threatened = any(by <= 96 and -1 <= dx <= 7 for by, dx in bullets)
            blocked = any(by <= 96 and 8 <= dx <= 12 for by, dx in bullets)
            if not threatened and self.wave_wait <= WAVE_WAIT_LIMIT and (not bullets or blocked):
                return 0
            self.wave_wait = 0
        return ACTIONS[(move, fire)]
