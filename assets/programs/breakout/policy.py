"""Breakout RAM policy: predict where the ball meets the paddle and plan paddle moves to be there.

RAM map (probed, see NOTES.md):
  ram[57]  lives
  ram[70]  paddle controller value r (0..184). Per frame: RIGHT r -= ~5.6, LEFT r += ~5.6, clipped.
  ram[72]  drawn paddle x px (55..191). Per frame (exact):
           px' = clip(ceil((px + 234 - r) / 2), 55, 191)
  ram[76], ram[77] score (hundreds; BCD tens/ones)
  ram[99]  ball x (walls at ~55 and ~201)
  ram[101] ball y (grows downward; 0 = no ball in play)
  ram[103:105] vertical velocity as signed 8.8 fixed point
  ram[105:107] negated horizontal velocity as signed 8.8 fixed point
  ram[108] half paddle width w (8 normal; 6 after the paddle shrinks)
Actions: 0 NOOP, 1 FIRE, 2 RIGHT, 3 LEFT. One agent step = 4 frames.

Hit rule (fit with 0 errors on ~6000 frame-level contacts): the ball is returned iff on some
frame with ball y in [177, 183], (ball_x - paddle_x) is in [1, 2w+1]. Offsets in [1, w] send
the ball left, [w+1, 2w+1] send it right.

Each step:
  1. simulate the ball (walls + bricks) until it passes the paddle band;
  2. enumerate short paddle action sequences under several sticky-action delays;
  3. select a safe interception, preferring early, steady movement.
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
OFF_D = 1               # default aim: ball_x - paddle_x = w + OFF_D (centre of the hit window)
SAFE = 5                # wanted margin (px) inside the hit window
PEN = 10.0              # cost per px of missing margin
DEAD_PEN = 0.02         # cost per unit of controller travel inside a wall dead zone (per step)
SIM_FRAMES = 400        # max frames of ball flight to simulate
DELAY_WEIGHTS = np.array([.75, .1875, .0625])
SCENARIO_WEIGHTS = np.outer(DELAY_WEIGHTS, DELAY_WEIGHTS).reshape(-1)
# stall breaking
STALL = 400             # steps without scoring before perturbing the aim point
JIT_EDGE = 3            # keep the jittered aim at least this far from the window edges
STALL2 = 3000           # steps without scoring before dropping, if another life remains


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
        self.last_move = 0              # last requested paddle direction
        self.prev = None                # ball (x, y) at the previous step
        self.rng = np.random.default_rng(12345)
        self.last_score = 0
        self.lives = None
        self.since_score = 0            # steps since the score (or lives) last changed
        self.jitter = 0                 # stall breaker: shift of the aim point
        self.dropping = False           # stall breaker: losing the ball on purpose
        self.prev_vy_sign = 0
        self.loop_history = []
        self.escape_moves = []

    # ------------------------------------------------------------------ main loop
    def act(self, obs, info: dict) -> int:
        action = self._act(obs, info)
        self.last_move = 1 if action == RIGHT else -1 if action == LEFT else 0
        return action

    def _act(self, obs, info: dict) -> int:
        ram = np.asarray(obs, dtype=np.int32)
        r, px, bx, by = int(ram[70]), int(ram[72]), int(ram[99]), int(ram[101])
        w = int(ram[108])
        prev = self.prev
        self.prev = (bx, by)

        vy_byte = int(ram[103])
        vy_sign = 0 if vy_byte == 0 else (1 if vy_byte < 128 else -1)
        returned = self.prev_vy_sign > 0 and vy_sign < 0 and by > 150
        self._update_stall(ram, prev, by, w, returned)
        self.prev_vy_sign = vy_sign
        if by == 0:
            self.dropping = False
            self.escape_moves.clear()
            return FIRE

        # Exact one- or two-return cycles can trap the ball indefinitely.
        # Pulse both directions to find a different controller position before
        # spending a life on a stall. Do not interrupt a deliberate drop.
        if self.since_score <= 2000:
            self.loop_history.clear()
        elif returned and (self.lives == 1 or self.since_score <= STALL2):
            signature = tuple(int(ram[i]) for i in (99, 100, 101, 102, 105, 106))
            self.loop_history.append(signature)
            self.loop_history = self.loop_history[-8:]
            if len(self.loop_history) == 8 and self.loop_history[2:] == self.loop_history[:-2]:
                direction = RIGHT if prev is not None and prev[0] - px > w else LEFT
                opposite = LEFT if direction == RIGHT else RIGHT
                self.escape_moves = [direction, NOOP, opposite, NOOP]
                self.loop_history.clear()
        if self.escape_moves:
            return self.escape_moves.pop(0)

        # long stall: the fast ball's paths form a closed lattice that misses the remaining
        # bricks; losing a life restarts the ball slowly with new angles and a full paddle.
        # Two cleared walls give the maximum 864 points; end that finished
        # game instead of spending the remaining episode on an empty board.
        if self.last_score >= 864 or (self.since_score > STALL2 and self.lives > 1):
            self.dropping = True
        # Ball velocities are stored as signed 8.8 fixed-point numbers;
        # horizontal RAM velocity has the opposite sign to the screen axis.
        vx_byte = int(ram[105])
        vx = -((vx_byte if vx_byte < 128 else vx_byte - 256) + int(ram[106]) / 256.0)
        vy = (vy_byte if vy_byte < 128 else vy_byte - 256) + int(ram[104]) / 256.0
        vel = (vx, vy) if 0 < abs(vy) <= 4 and abs(vx) <= 2 else None
        bricks = read_bricks(ram)
        sim = None if vel is None else self._sim_ball(bx, by, *vel, bricks)
        if self.dropping:
            # move the paddle to the wall farthest from where the ball will come down
            land = bx if sim is None else sim[0][0][1]
            return LEFT if land > 128 else RIGHT

        lo, hi = 1, 2 * w + 1               # hit window for (ball_x - paddle_x)
        aim = w + OFF_D + self.jitter
        pos, dead = self._simulate_paddle(r, px)
        if sim is None:
            return self._choose(self._goal_cost(pos, bx - aim), dead)
        band, out_vx = sim

        # On long scoreless loops, deliberately make the ball meet the paddle
        # later in the contact band. This shifts the next trajectory to a new lattice.
        late = (self.since_score > 1000 and len(band) > 1 and abs(out_vx) >= 1.5
                and P_MIN + hi + 2 <= band[0][1] <= P_MAX - 2)
        if late:
            aim = 0 if out_vx > 0 else hi + 1
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
        cost, _ = self._contact_cost(pos, js, xs, lo, hi, aim)
        return self._choose(cost, dead)

    def _update_stall(self, ram, prev, by, w, returned):
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
        # On the second wall or in a prolonged stall, draw a single jitter
        # per bounce instead of redrawing on each ascending observation.
        if score >= 432 or self.since_score > 1000:
            just_returned = returned
        else:
            just_returned = prev is not None and prev[1] > by > 150
        if self.since_score > STALL and just_returned:
            lim = max(0, w - JIT_EDGE)
            self.jitter = int(self.rng.integers(-lim, lim + 1))

    # ------------------------------------------------------------------ paddle planning
    def _simulate_paddle(self, r, px):
        """Paddle x at every future frame (0..4H) for every plan -> (P, 4H+1), plus the
        controller travel wasted inside the wall dead zones per plan."""
        P, H = self.plans.shape
        # Delays at the first and subsequent changes are independent. This
        # captures, for example, a late start followed by an immediate stop.
        plans = np.tile(self.plans, (9, 1))
        first_delays = np.repeat(np.repeat(np.arange(3), 3), P)
        later_delays = np.repeat(np.tile(np.arange(3), 3), P)
        pos = np.empty((9 * P, 4 * H + 1))
        rr = np.full(9 * P, float(r))
        pp = np.full(9 * P, float(px))
        pos[:, 0] = pp
        dead = np.zeros(9 * P)
        lo_r, hi_r = R_C - P_MAX, R_C - P_MIN
        previous = np.full(9 * P, self.last_move)
        changed = np.zeros(9 * P, dtype=bool)
        for t in range(H):
            current = plans[:, t]
            delays = np.where(changed, later_delays, first_delays)
            changed |= current != previous
            for i in range(4):
                move = np.where(i < delays, previous, current)
                pp = np.clip(np.ceil((pp + R_C - rr) / 2.0), P_MIN, P_MAX)
                rr = np.clip(rr - R_FRAME * move, R_MIN, R_MAX)
                pos[:, 4 * t + i + 1] = pp
            previous = current
            dead += np.maximum(0.0, lo_r - rr) + np.maximum(0.0, rr - hi_r)
        return pos, dead

    @staticmethod
    def _goal_cost(pos, goal):
        """Ball still far away: be at the goal at the end of the horizon, at rest."""
        return np.abs(pos[:, -1] - goal) + 0.5 * np.abs(pos[:, 4::4] - goal).mean(axis=1)

    @staticmethod
    def _contact_cost(pos, js, xs, lo, hi, aim, safe=SAFE):
        """Cost the nominal catch and report the worst timing-shift margin.

        A catch can occur on any frame in the contact band. The worst margin
        across timing shifts is used to gate risky late-contact stall breaking.
        """
        F = pos.shape[1] - 1
        off = xs[None, :] - pos[:, js]
        nominal_m = np.minimum(off - lo, hi - off).max(axis=1)
        best_m = nominal_m
        for shift in (-1, 1):
            off = xs[None, :] - pos[:, np.clip(js + shift, 0, F)]
            margin = np.minimum(off - lo, hi - off).max(axis=1)
            best_m = np.minimum(best_m, margin)
        off0 = xs[0] - pos[:, js[0]]
        cost = PEN * np.maximum(0.0, safe - nominal_m) + np.abs(off0 - aim)
        # Move towards the interception point early, leaving time for the
        # paddle to settle and for sticky-action errors to be corrected.
        goal = xs[0] - aim
        cost += 0.5 * np.abs(pos[:, :int(js[0]) + 1:4] - goal).mean(axis=1)
        cost_by_scenario = cost.reshape(9, -1)
        margin_by_scenario = best_m.reshape(9, -1)
        aggregate = SCENARIO_WEIGHTS @ cost_by_scenario
        best = int(np.argmin(aggregate))
        return cost, float(np.min(margin_by_scenario[:, best]))

    def _choose(self, cost, dead):
        # Weight the delay scenarios and avoid wasted wall travel.
        cost = (cost + DEAD_PEN * dead).reshape(9, -1)
        cost = SCENARIO_WEIGHTS @ cost
        # Do not drive into a wall and reverse solely for a slightly better
        # final pixel: extra changes are unreliable with sticky actions.
        moves = np.abs(self.plans).sum(axis=1)
        reversals = (self.plans[:, 1:] * self.plans[:, :-1] < 0).sum(axis=1)
        cost += 1.0 * moves + 30.0 * reversals
        return S2A[int(self.plans[int(np.argmin(cost)), 0])]

    # ------------------------------------------------------------------ ball model
    @staticmethod
    def _sim_ball(x, y, fx, fy, bricks):
        """Frame-level ball flight (breaking bricks) until it passes the paddle band descending.
        Mutates the fresh brick map; returns ([(frame, x)] in the band, vx at contact) or None."""
        band = []
        if fy > 0 and Y_HIT <= y <= Y_BOT:
            band.append((0, float(x)))
        for j in range(1, SIM_FRAMES + 1):
            x, y, fx, fy = ball_step(x, y, fx, fy)
            cell = brick_cell(x, y, fy)
            if cell is not None and bricks[cell]:
                bricks[cell] = False
                fy = -fy
                continue
            if fy > 0 and y >= Y_HIT:
                if y > Y_BOT:
                    break
                band.append((j, x))
        return (band, fx) if band else None

