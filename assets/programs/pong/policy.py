"""Pong RAM policy: model-predictive paddle aiming.

RAM layout (probed, see NOTES.md):
  ram[51] player (right) paddle y, ram[50] CPU paddle y,
  ram[49] ball x (increases toward us), ram[54] ball y (0 = no ball in play).
Actions: 0 NOOP, 2 up (y decreases), 3 down (y increases).

Paddle dynamics: UP/DOWN shift a hidden commanded position R by ~23 px; the
displayed paddle follows through a short linear filter.  A linear model
  dp[t+1] = sum_{i<4} c_i u[t-i] + sum_{j<3} d_j dp[t-j],   u = -1/0/+1
fits each episode to ~0.5 px, but the c coefficients depend on an
episode-specific frame phase, so they are refined online with recursive
least squares starting from a prior.

Hit geometry: rel = ball_y - paddle_y on the frame the ball reaches x>=186.
The ball is returned for rel in about [-3, 16]; outgoing dy is
-8 for rel<=0, -4 for 1..4, 0 for 5..8, +4 for 8..12, +8 for >=12.

Per point: wait near the centre, predict where the incoming ball crosses
CONTACT_X, pick a steep shot the CPU paddle cannot reach, then plan the last
few moves by brute-force search over action sequences with the paddle model.
"""

import itertools

import numpy as np

CONTACT_X = 186         # first ball x counted as "at our paddle"
CPU_X = 72              # ball x at which the CPU paddle meets it
TOP, BOTTOM = 45.0, 206.0   # ball y bounce limits
PMIN, PMAX = 38.0, 203.0    # paddle y limits
UP, DOWN, NOOP = 2, 3, 0
U = {NOOP: 0, UP: -1, DOWN: 1}
STEP = 23.0             # commanded-position shift per UP/DOWN

HIT_LO, HIT_HI = -3, 16     # rel window in which we return the ball
SAFE_LO, SAFE_HI = -1.0, 14.0
CPU_LO, CPU_HI = -2, 12     # CPU returns the ball for ball_y - cpu_y in this range
CPU_SPEED = 7.0             # CPU paddle max px/step
SHOTS = {-8: -1.0, 8: 14.0}   # outgoing dy -> rel to aim for (only steep shots beat the CPU)
WALL_MARGIN = 10.0          # keep the aimed paddle position this far from the walls
LOOP_AFTER = 4              # after this many returns in a rally, pick random shots

HORIZON = 4                 # MPC search when contact is at most this many steps away
SEQS = {k: list(itertools.product((NOOP, UP, DOWN), repeat=k)) for k in range(1, HORIZON + 2)}
VEL_PEN, SAFE_PEN, WALL_PEN = 0.25, 4.0, 2.0

NU, NV = 4, 3
PRIOR = np.array([7.5, 14.3, 7.7, 2.4, -0.34, -0.08, 0.05])
PRIOR_WEIGHT = 30.0


def reflect(y, lo=TOP, hi=BOTTOM):
    span = hi - lo
    p = (y - lo) % (2 * span)
    if p > span:
        p = 2 * span - p
    return lo + p


def run_ball_and_cpu(y, vy, c, n):
    """Advance ball y (bouncing) and the CPU paddle tracking it for n steps."""
    for _ in range(n):
        y_raw = y + vy
        if y_raw < TOP or y_raw > BOTTOM:
            vy = -vy
        y = reflect(y_raw)
        c += max(-CPU_SPEED, min(CPU_SPEED, y - c))
    return y, c


def eff_u(R, a):
    """Next commanded position and the effective (clamp-aware) input for action a."""
    Rn = min(max(R + STEP * U[a], PMIN), PMAX + 1)
    return Rn, (Rn - R) / STEP


def allowed_shots(yc):
    """Steep shots whose paddle position stays clear of the walls (model is poor there).

    Only dy = +-8 shots beat the CPU.  Since yc is in [TOP, BOTTOM], at least one of
    them is allowed except for a ball hugging the top wall, where -8 is the closest.
    """
    lo, hi = PMIN + WALL_MARGIN, PMAX - WALL_MARGIN
    return [s for s in (-8, 8) if lo <= yc - SHOTS[s] <= hi] or [-8]


def choose_shot(yc, dxa, cpu):
    """Pick the shot that leaves the CPU paddle farthest outside its return window."""
    n = max(1, int(round((CONTACT_X - CPU_X) / dxa)))
    best, best_m = None, -1e9
    for s in allowed_shots(yc):
        y, c = run_ball_and_cpu(yc, s, cpu, n)
        rel = y - c
        margin = max(CPU_LO - rel, rel - CPU_HI)
        if margin > best_m:
            best, best_m = s, margin
    return best


def ball_velocity(o, prev):
    if prev is None or o[54] == 0 or prev[54] == 0:
        return None
    dx = int(o[49]) - int(prev[49])
    dy = int(o[54]) - int(prev[54])
    if dx == 0 or abs(dx) > 12 or abs(dy) > 20:
        return None
    return dx, dy


class Policy:
    def __init__(self, spec: dict):
        self.rng = np.random.default_rng(7)
        self.reset()

    def reset(self) -> None:
        self.prev = None            # previous RAM
        self.plan_rel = None        # rel aimed for at the coming contact
        self.rally = 0              # returns in the current point
        self.us = [0.0] * NU        # recent effective inputs, most recent first
        self.dps = [0.0] * NV       # recent paddle steps, most recent first
        self.R = None               # estimated commanded position
        self.last_p = None
        self.last_feat = None
        self.theta = PRIOR.copy()   # RLS state
        self.P = np.eye(len(PRIOR)) / PRIOR_WEIGHT

    def act(self, obs, info: dict) -> int:
        o = obs.astype(np.int64)
        self.observe_paddle(float(o[51]))
        a = self.decide(o)
        self.R, u = eff_u(self.R, a)
        self.us = [u] + self.us[:-1]
        self.last_feat = np.array(self.us + self.dps)
        self.prev = o
        return a

    # ---- paddle model ----------------------------------------------------
    def observe_paddle(self, p):
        if self.last_p is None:
            self.last_p = p
            self.R = p + 1.0
            return
        dp = p - self.last_p
        # RLS update, away from the walls where the model does not hold
        if self.last_feat is not None and 50 < self.last_p < 192 and 50 < p < 192:
            x = self.last_feat
            Px = self.P @ x
            g = Px / (1.0 + x @ Px)
            self.theta = self.theta + g * (dp - x @ self.theta)
            self.P = self.P - np.outer(g, Px)
        self.dps = [dp] + self.dps[:-1]
        self.last_p = p
        # resync the command estimate when the paddle rests after NOOPs or sits at a wall
        if all(abs(d) < 0.5 for d in self.dps[:2]) and all(u == 0 for u in self.us[:3]):
            self.R = p + 1.0 if p > PMIN + 0.5 else PMIN
        if p <= PMIN + 0.5 and self.us[0] < 0:
            self.R = PMIN
        if p >= PMAX - 0.5 and self.us[0] > 0:
            self.R = PMAX + 1

    def simulate(self, seq):
        """Predicted paddle positions after each action of seq."""
        th = self.theta
        us, dps, p, R = list(self.us), list(self.dps), self.last_p, self.R
        ps = []
        for a in seq:
            R, u = eff_u(R, a)
            us = [u] + us[:-1]
            dp = float(np.dot(th[:NU], us) + np.dot(th[NU:], dps))
            p = min(max(p + dp, PMIN), PMAX)
            dps = [dp] + dps[:-1]
            ps.append(p)
        return ps

    # ---- control ---------------------------------------------------------
    def decide(self, o):
        bx, by = int(o[49]), int(o[54])
        vel = ball_velocity(o, self.prev)

        if by == 0:
            self.rally = 0
        if vel is None or vel[0] < 0 or bx > CONTACT_X + 4:
            # ball not coming at us: wait between the ball and the centre
            self.plan_rel = None
            target = 124.0 if by == 0 else 0.5 * (by + 124.0)
            return self.settle_toward(target - 6.0)

        dx, dy = vel
        k = max(0, int(np.ceil((CONTACT_X - bx) / dx)))   # steps until contact
        yc = reflect(by + dy * k)          # ball y on the contact frame
        yn = reflect(by + dy * (k + 1))    # and one frame later
        if self.plan_rel is None:
            self.rally += 1
            if self.rally > LOOP_AFTER:
                # long rally: the deterministic choice is probably looping
                ok = allowed_shots(yc)
                shot = ok[int(self.rng.integers(len(ok)))]
            else:
                _, cpu = run_ball_and_cpu(float(by), dy, float(o[50]), k)
                shot = choose_shot(yc, abs(dx), cpu)
            self.plan_rel = SHOTS[shot]

        if k > HORIZON:
            return self.settle_toward(yc - self.plan_rel)
        best, best_c = NOOP, None
        for seq in SEQS[k + 1]:
            ps = self.simulate(seq)
            p1 = ps[-1]
            p0 = ps[-2] if k > 0 else self.last_p
            rel0, rel1 = yc - p0, yn - p1
            aim = 0.5 * (rel0 + rel1)
            c = (abs(aim - self.plan_rel) + VEL_PEN * abs(p1 - p0)
                 + SAFE_PEN * (max(0.0, SAFE_LO - aim) + max(0.0, aim - SAFE_HI))
                 + SAFE_PEN * sum(max(0.0, HIT_LO + 1.0 - r) + max(0.0, r - HIT_HI + 1.0)
                                  for r in (rel0, rel1))
                 + WALL_PEN * sum(max(0.0, PMIN + 4.0 - q) + max(0.0, q - PMAX + 4.0) for q in ps))
            if best_c is None or c < best_c - 1e-9:
                best, best_c = seq[0], c
        return best

    def settle_toward(self, target):
        """Coarse move of the commanded position toward target (only if it gains > 2 px)."""
        target = min(max(target, PMIN + 8.0), PMAX - 8.0) + 1.0
        best, best_c = NOOP, abs(self.R - target)
        for a in (UP, DOWN):
            c = abs(eff_u(self.R, a)[0] - target)
            if c < best_c - 2.0:
                best, best_c = a, c
        return best
