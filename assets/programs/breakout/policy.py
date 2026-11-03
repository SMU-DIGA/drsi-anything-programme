"""Breakout RAM policy: predict where the ball meets the paddle and plan paddle moves to be there.

RAM map (probed, see NOTES.md):
  ram[57]  lives
  ram[70]  paddle controller value r (0..184). Per frame: RIGHT r -= ~5.6, LEFT r += ~5.6, clipped.
  ram[72]  drawn paddle x px (55..191). Per frame (exact):
           px' = clip(ceil((px + 234 - r) / 2), 55, 191)
  ram[76], ram[77] score (hundreds; BCD tens/ones)
  ram[99]  ball x (walls at ~55 and ~201)
  ram[101] ball y (grows downward; 0 = no ball in play)
  ram[108] half paddle width w (8 normal; 6 after the paddle shrinks)
Actions: 0 NOOP, 1 FIRE, 2 RIGHT, 3 LEFT. One agent step = 4 frames.

Hit rule (fit with 0 errors on ~6000 frame-level contacts): the ball is returned iff on some
frame with ball y in [177, 183], (ball_x - paddle_x) is in [1, 2w+1]. Offsets in [1, w] send
the ball left, [w+1, 2w+1] send it right.

Each step:
  1. simulate the ball (walls + bricks) until it passes the paddle band;
  2. pick the paddle half that sends the next flight into a brick (steering);
  3. enumerate short action sequences, simulate the paddle frame by frame and pick the one with
     the largest hit margin (or, if the ball is still far away, the one that ends at rest under
     the landing point).
If no brick is scored for a long time, perturb the aim point and finally drop the ball on
purpose (a fresh life restarts the ball slowly with new angles).
"""

import numpy as np

NOOP, FIRE, RIGHT, LEFT = 0, 1, 2, 3
S2A = {0: NOOP, 1: RIGHT, -1: LEFT}

# Brick (row, col) is present iff ram[base - row] & mask, with (base, mask) per column 0..17.
# Rows 0 (top, red) .. 5 (bottom, blue). Column c spans ball x ~[57+8c, 64+8c],
# row r spans ball y ~[49+6r, 54+6r].
BRICK_COLS = ([(35, 0xC0)]
              + [(29, m) for m in (0xC0, 0x30, 0x0C, 0x03)]
              + [(23, m) for m in (0x03, 0x0C, 0x30, 0xC0)]
              + [(17, m) for m in (0x30, 0xC0)]
              + [(11, m) for m in (0xC0, 0x30, 0x0C, 0x03)]
              + [(5, m) for m in (0x03, 0x0C, 0x30)])

# geometry / dynamics (probed)
Y_TOP = 23              # top wall (ball y at reversal)
Y_HIT, Y_BOT = 177, 183  # ball y range in which the paddle can return the ball
X_MIN, X_MAX = 55, 201  # ball x reflection bounds
P_MIN, P_MAX = 55, 191  # paddle x bounds
R_MIN, R_MAX = 0, 184   # controller bounds
R_FRAME = 5.6           # controller change per frame while moving
R_C = 234               # resting paddle x = R_C - r
# planning
HORIZON = 10            # planning horizon in steps
VMAX = 20               # max plausible per-step ball displacement
OFF_D = 1               # default aim: ball_x - paddle_x = w + OFF_D (centre of the hit window)
SAFE = 3                # wanted margin (px) inside the hit window
PEN = 10.0              # cost per px of missing margin
DEAD_PEN = 0.02         # cost per unit of controller travel inside a wall dead zone (per step)
SIM_FRAMES = 400        # max frames of ball flight to simulate
SIDE_MIN_MARGIN = 1.5   # only steer if the planner can hit the chosen half with this margin
SIDE_MIN_MARGIN_STALLED = -0.5  # same, while stalled (riskier: the alternative is a drop)
LOOKAHEAD = 12          # extra bounces searched when no direction hits a brick right away
# stall breaking
STALL = 400             # steps without scoring before perturbing the aim point
JIT_EDGE = 3            # keep the jittered aim at least this far from the window edges
STALL2 = 2000           # steps without scoring before dropping, if another life remains


def ball_step(x, y, fx, fy):
    """Advance the ball one frame, reflecting off the side and top walls."""
    x += fx
    y += fy
    if x < X_MIN:
        x, fx = 2 * X_MIN - x, -fx
    elif x > X_MAX:
        x, fx = 2 * X_MAX - x, -fx
    if y < Y_TOP:
        y, fy = 2 * Y_TOP - y, -fy
    return x, y, fx, fy


def brick_cell(x, y, fy):
    """(row, col) of the brick area the ball touches, or None (leading edge when descending)."""
    yy = y if fy < 0 else y + 3
    if 49 <= yy < 85:
        return int((yy - 49) // 6), min(17, max(0, int((x - 57) // 8)))
    return None


def read_bricks(ram):
    g = np.zeros((6, 18), dtype=bool)
    for c, (b, m) in enumerate(BRICK_COLS):
        for row in range(6):
            g[row, c] = bool(ram[b - row] & m)
    return g


def build_plans():
    """Candidate action sequences: s1 x n1, then s2 x n2, then NOOP -> (P, HORIZON)."""
    H = HORIZON
    plans = {tuple([s1] * n1 + [s2] * n2 + [0] * (H - n1 - n2))
             for s1 in (-1, 0, 1) for s2 in (-1, 0, 1)
             for n1 in range(H + 1) for n2 in range(H + 1 - n1)}
    return np.array(sorted(plans), dtype=np.float64)


class Policy:
    def __init__(self, spec: dict):
        self.plans = build_plans()
        self.reset()

    def reset(self) -> None:
        self.prev = None                # ball (x, y) at the previous step
        self.prev2 = None
        self.rng = np.random.default_rng(12345)
        self.last_score = 0
        self.lives = None
        self.since_score = 0            # steps since the score (or lives) last changed
        self.jitter = 0                 # stall breaker: shift of the aim point
        self.dropping = False           # stall breaker: losing the ball on purpose

    # ------------------------------------------------------------------ main loop
    def act(self, obs, info: dict) -> int:
        ram = np.asarray(obs, dtype=np.int32)
        r, px, bx, by = int(ram[70]), int(ram[72]), int(ram[99]), int(ram[101])
        w = int(ram[108])
        prev, prev2 = self.prev, self.prev2
        self.prev, self.prev2 = (bx, by), prev

        self._update_stall(ram, prev, by, w)
        if by == 0:
            self.dropping = False
            return FIRE

        # long stall: the fast ball's paths form a closed lattice that misses the remaining
        # bricks; losing a life restarts the ball slowly with new angles and a full paddle.
        if self.since_score > STALL2 and self.lives > 1:
            self.dropping = True
        vel = self._velocity(bx, by, prev, prev2)
        bricks = read_bricks(ram)
        sim = None if vel is None else self._sim_ball(bx, by, *vel, bricks)
        rebound = False
        # A wall rebound between observations can hide the true horizontal speed.
        # Use the preceding speed only if reflection explains the observed endpoint
        # and the corrected landing exposes a miss hidden by the original forecast.
        if sim is not None and prev is not None and prev2 is not None and by >= 130:
            old_dx = prev[0] - prev2[0]
            dx = bx - prev[0]
            projected = prev[0] + old_dx
            reflected = (2 * X_MAX - projected if old_dx > 0 and projected > X_MAX else
                         2 * X_MIN - projected if old_dx < 0 and projected < X_MIN else None)
            if (prev2[1] < prev[1] < by and abs(old_dx) >= 4 and dx * old_dx <= 0
                    and reflected is not None and abs(bx - reflected) <= 3):
                corrected = self._sim_ball(bx, by, -old_dx / 4.0, vel[1], bricks)
                if corrected is not None:
                    old_offset = sim[0][0][1] - px
                    new_offset = corrected[0][0][1] - px
                    if 1 <= old_offset <= 2 * w + 1 and not 1 <= new_offset <= 2 * w + 1:
                        sim, rebound = corrected, True
        if self.dropping:
            # move the paddle to the wall farthest from where the ball will come down
            land = bx if sim is None else sim[0][0][1]
            return LEFT if land > 128 else RIGHT

        lo, hi = 1, 2 * w + 1               # hit window for (ball_x - paddle_x)
        aim = w + OFF_D + (0 if rebound else self.jitter)
        pos, dead = self._simulate_paddle(r, px)
        if sim is None:
            return self._choose(self._goal_cost(pos, bx - aim), dead)
        band, out_vx, out_vy, bricks_left = sim

        # which half of the paddle should the ball hit? (left half -> ball goes left)
        stalled = self.since_score > STALL
        # On long scoreless loops, deliberately make the ball meet the paddle
        # later in the contact band. This shifts the next trajectory to a new lattice.
        late = (not rebound and self.since_score > 1000 and len(band) > 1 and abs(out_vx) >= 1.5
                and P_MIN + hi + 2 <= band[0][1] <= P_MAX - 2)
        if late:
            aim = 0 if out_vx > 0 else hi + 1
        side = 0
        # After an urgent correction, use the whole paddle rather than steering.
        if bricks_left.any() and not late and not rebound:
            side = self._pick_side(band[0][1], abs(out_vx), abs(out_vy), bricks_left, stalled)
        if side != 0:
            lo_s, hi_s = (lo, w) if side < 0 else (w + 1, hi)
            aim = 0.5 * (lo_s + hi_s)

        F = pos.shape[1] - 1
        if band[0][0] >= F:
            # ball is beyond the planning horizon: be at rest under its landing point
            return self._choose(self._goal_cost(pos, band[0][1] - aim), dead)
        js = np.array([j for j, _ in band if j <= F])
        xs = np.array([x for j, x in band if j <= F])
        if late:
            cost, m = self._contact_cost(pos, js, xs, lo, hi, aim, safe=1)
            if m >= 0.5:
                return self._choose(cost, dead)
            aim = w + OFF_D + self.jitter
        if side != 0:
            # when stalled, steering is worth more risk (the alternative is a deliberate drop)
            cost, m = self._contact_cost(pos, js, xs, lo_s, hi_s, aim,
                                         robust=not stalled, full=(lo, hi))
            if m >= (SIDE_MIN_MARGIN_STALLED if stalled else SIDE_MIN_MARGIN):
                return self._choose(cost, dead)
            aim = w + OFF_D + self.jitter
        cost, _ = self._contact_cost(pos, js, xs, lo, hi, aim)
        return self._choose(cost, dead)

    def _update_stall(self, ram, prev, by, w):
        """Count steps without scoring; once stalled, re-randomise the aim after each return."""
        score = int(ram[76]) * 100 + (int(ram[77]) >> 4) * 10 + (int(ram[77]) & 15)
        lives = int(ram[57])
        if lives != self.lives:
            self.lives = lives
            self.since_score = 0
        if score != self.last_score:
            self.last_score = score
            self.since_score = 0
            self.jitter = 0
        else:
            self.since_score += 1
        just_returned = prev is not None and prev[1] > by > 150
        if self.since_score > STALL and just_returned:
            lim = max(0, w - JIT_EDGE)
            self.jitter = int(self.rng.integers(-lim, lim + 1))

    @staticmethod
    def _velocity(bx, by, prev, prev2):
        """Estimate per-frame velocity, averaging eight consistent frames when possible.
        Return None if there is no plausible previous position."""
        if prev is None or prev[1] == 0:
            return None
        vx, vy = bx - prev[0], by - prev[1]
        if not (abs(vx) <= VMAX and 0 < abs(vy) <= VMAX):
            return None
        if prev2 is not None and prev2[1] != 0:
            vx2, vy2 = prev[0] - prev2[0], prev[1] - prev2[1]
            if vx * vx2 > 0 and vy * vy2 > 0 and abs(vx2) <= VMAX and abs(vy2) <= VMAX:
                return (vx + vx2) / 8.0, (vy + vy2) / 8.0
            # A horizontal wall bounce does not change vertical speed. Keep its
            # more accurate eight-frame estimate near the paddle independently.
            if by >= 130 and vy * vy2 > 0 and abs(vy2) <= VMAX:
                return vx / 4.0, (vy + vy2) / 8.0
        return vx / 4.0, vy / 4.0

    # ------------------------------------------------------------------ paddle planning
    def _simulate_paddle(self, r, px):
        """Paddle x at every future frame (0..4H) for every plan -> (P, 4H+1), plus the
        controller travel wasted inside the wall dead zones per plan."""
        P, H = self.plans.shape
        pos = np.empty((P, 4 * H + 1))
        rr = np.full(P, float(r))
        pp = np.full(P, float(px))
        pos[:, 0] = pp
        dead = np.zeros(P)
        lo_r, hi_r = R_C - P_MAX, R_C - P_MIN
        for t in range(H):
            d = -R_FRAME * self.plans[:, t]
            for i in range(4):
                pp = np.clip(np.ceil((pp + R_C - rr) / 2.0), P_MIN, P_MAX)
                rr = np.clip(rr + d, R_MIN, R_MAX)
                pos[:, 4 * t + i + 1] = pp
            # controller pushed past the point where the paddle is already at the wall:
            # wasted travel that has to be undone before the paddle can come back
            dead += np.maximum(0.0, lo_r - rr) + np.maximum(0.0, rr - hi_r)
        return pos, dead

    @staticmethod
    def _goal_cost(pos, goal):
        """Ball still far away: be at the goal at the end of the horizon, at rest."""
        return np.abs(pos[:, -1] - goal) + 0.1 * np.abs(pos[:, 4::4] - goal).mean(axis=1)

    @staticmethod
    def _contact_cost(pos, js, xs, lo, hi, aim, robust=True, full=None, safe=SAFE):
        """Cost per plan of returning the ball with offset in [lo, hi], and the best plan's margin.

        The ball returns if ANY band frame is inside the window; to be robust to a 1-frame error
        in the predicted arrival time, the margin is the worst over arrival shifts -1/0/+1.
        full=(lo, hi) of the whole paddle when (lo, hi) is only one half: the bounce happens at
        the FIRST band frame inside the whole paddle, and that frame decides the direction."""
        F = pos.shape[1] - 1
        rows = np.arange(pos.shape[0])
        best_m = None
        for s in ((0, -1, 1) if robust else (0,)):
            off = xs[None, :] - pos[:, np.clip(js + s, 0, F)]
            if full is None:
                m = np.minimum(off - lo, hi - off).max(axis=1)
            else:
                inside = (off >= full[0]) & (off <= full[1])
                of = off[rows, np.argmax(inside, axis=1)]
                m_full = np.minimum(off - full[0], full[1] - off).max(axis=1)
                m = np.where(inside.any(axis=1), np.minimum(of - lo, hi - of), m_full - (hi - lo))
            best_m = m if best_m is None else np.minimum(best_m, m)
        off0 = xs[0] - pos[:, js[0]]
        cost = PEN * np.maximum(0.0, safe - best_m) + np.abs(off0 - aim)
        return cost, float(best_m[int(np.argmin(cost))])

    def _choose(self, cost, dead):
        # avoid driving the controller into the wall dead zones; tie-break: prefer fewer moves
        cost = cost + DEAD_PEN * dead + 1e-3 * np.abs(self.plans).sum(axis=1)
        return S2A[int(self.plans[int(np.argmin(cost)), 0])]

    # ------------------------------------------------------------------ ball model
    @staticmethod
    def _sim_ball(x, y, fx, fy, bricks):
        """Frame-level ball flight (breaking bricks) until it passes the paddle band descending.
        Returns ([(frame, x)] in the band, vx, vy at contact, bricks left) or None."""
        g = bricks.copy()
        band = []
        if fy > 0 and Y_HIT <= y <= Y_BOT:
            band.append((0, float(x)))
        for j in range(1, SIM_FRAMES + 1):
            x, y, fx, fy = ball_step(x, y, fx, fy)
            cell = brick_cell(x, y, fy)
            if cell is not None and g[cell]:
                g[cell] = False
                fy = -fy
                continue
            if fy > 0 and y >= Y_HIT:
                if y > Y_BOT:
                    break
                band.append((j, x))
        return (band, fx, fy, g) if band else None

    @staticmethod
    def _flight(x, fx, fy, bricks):
        """Ball leaving the paddle at x: (hits a brick?, landing x if it does not)."""
        y = float(Y_HIT)
        for _ in range(SIM_FRAMES):
            x, y, fx, fy = ball_step(x, y, fx, fy)
            cell = brick_cell(x, y, fy)
            if cell is not None and bricks[cell]:
                return True, None
            if fy > 0 and y >= Y_HIT:
                return False, x
        return False, None

    def _pick_side(self, xc, avx, avy, bricks, stalled):
        """-1/+1 to send the ball left/right from contact x xc, 0 = no preference."""
        hits, lands = {}, {}
        for d in (-1, 1):
            hits[d], lands[d] = self._flight(xc, d * avx, -avy, bricks)
        if hits[-1] != hits[1]:
            return -1 if hits[-1] else 1
        if hits[-1]:
            return 0
        # neither direction hits a brick now: breadth-first search over future landing points
        # (deduplicated) for the first direction that leads to a brick soonest
        frontier = [(d, lands[d]) for d in (-1, 1) if lands[d] is not None]
        seen = {int(round(x)) for _, x in frontier}
        for _ in range(LOOKAHEAD):
            nxt = []
            for first, xl in frontier:
                for d in (-1, 1):
                    hit, land = self._flight(xl, d * avx, -avy, bricks)
                    if hit:
                        return first
                    if land is not None and int(round(land)) not in seen:
                        seen.add(int(round(land)))
                        nxt.append((first, land))
            frontier = nxt
            if not frontier:
                break
        return int(self.rng.choice((-1, 1))) if stalled else 0
