"""Scripted pick-and-place policy for LIBERO-spatial (state observations).

Every task: "pick up the black bowl <where> and place it on the plate".
Ground the target bowl from <where>, then run a waypoint state machine:
above -> descend -> close -> lift -> carry -> lower -> release -> retreat,
with a regrasp whenever the bowl fails to lift, drops, or the placement
did not end the episode.
"""

import re

import numpy as np

GAIN = 12.0            # P gain on position error (action units per metre)
# Grasp (r, dz): hand offset r from the bowl centre toward the robot (-x) and
# dz above the bowl origin, so the fingers (closing along x) pinch the bowl
# wall.  Each retry uses the next entry.
ATTEMPTS = [(0.042, 0.030), (0.040, 0.022), (0.045, 0.035)]
OFF_DIR = np.array([-1.0, 0.0, 0.0])
ABOVE_Z = 0.12         # pre-grasp height above the bowl origin
LIFT_DZ = 0.20         # lift height above max(plate, bowl start)
PLACE_DZ = 0.03        # bowl origin height above plate origin when releasing
# Gripper pointing down, yawed 90 deg so the fingers close along world x.
R_DES = np.array([[0, 1, 0], [1, 0, 0], [0, 0, -1]], dtype=float)


def quat_to_mat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def mat_to_axisangle(m):
    ang = np.arccos(np.clip((np.trace(m) - 1) / 2, -1, 1))
    if ang < 1e-6:
        return np.zeros(3)
    if np.pi - ang < 1e-3:  # near pi: axis from the dominant diagonal column
        i = int(np.argmax(np.diag(m)))
        ax = m[:, i] + np.eye(3)[i]
    else:
        ax = np.array([m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1]])
    return ax / np.linalg.norm(ax) * ang


def object_positions(obs):
    return {k[:-4]: obs[k] for k in obs
            if k.endswith("_pos") and not k.startswith("robot0") and "_to_robot0" not in k}


def find(objs, word):
    return next((p for name, p in objs.items() if word in name), None)


def ground_bowl(instruction, objs):
    """Pick the bowl described by the instruction.  LIBERO-spatial names the
    instructed bowl akita_black_bowl_1, so keep it unless the geometry favours
    another bowl by more than 5 cm."""
    bowls = sorted(n for n in objs if "bowl" in n)
    where = instruction.lower().split(" and place")[0]
    plate = find(objs, "plate")

    def dist(p, q):
        return np.linalg.norm((p - q)[:2])

    def score(p):
        if "between" in where:
            a, b = find(objs, "plate"), find(objs, "ramekin")
            return -dist(p, (a + b) / 2) if a is not None and b is not None else 0.0
        if "table center" in where:
            return -dist(p, np.zeros(3))
        m = re.search(r"(next to|on) the (\w+)", where)
        ref = find(objs, m.group(2).rstrip("s")) if m else None
        if ref is None:
            return 0.0
        if m.group(1) == "on":   # stacked on ref: close in xy and raised
            return -dist(p, ref) + (p[2] - ref[2])
        on_table = plate is None or p[2] < plate[2] + 0.005
        return -dist(p, ref) if on_table else -9.0

    scores = {b: score(objs[b]) for b in bowls}
    default = "akita_black_bowl_1" if "akita_black_bowl_1" in bowls else bowls[0]
    best = max(bowls, key=scores.get)
    if scores[best] < scores[default] + 0.05:
        best = default
    print(f"[ground] {instruction!r} scores={scores} -> {best}", flush=True)
    return best


class Policy:
    def __init__(self, spec: dict):
        self.instruction = spec.get("instruction", "")
        self.reset()

    def reset(self) -> None:
        self.phase = "above"
        self.t = 0
        self.phase_t = 0
        self.target = None
        self.attempt = 0
        self.grip_pt = None   # eef - bowl at the moment of grasping
        self.bowl_z0 = 0.0
        self.retry_z = 0.0

    def _move(self, obs, goal, grip):
        d = np.clip(GAIN * (goal - obs["robot0_eef_pos"]), -1, 1)
        err = mat_to_axisangle(R_DES @ quat_to_mat(obs["robot0_eef_quat"]).T)
        return np.concatenate([d, np.clip(2.0 * err, -0.5, 0.5), [grip]])

    def _set(self, phase):
        print(f"[t={self.t}] phase {self.phase} -> {phase}", flush=True)
        self.phase = phase
        self.phase_t = 0

    def _retry(self, why, eef):
        self.attempt += 1
        print(f"[t={self.t}] retry #{self.attempt}: {why}", flush=True)
        self.retry_z = eef[2] + 0.06
        self._set("regrasp")
        return np.array([0, 0, 0.5, 0, 0, 0, -1.0])

    def act(self, obs, info: dict):
        self.t += 1
        self.phase_t += 1
        objs = object_positions(obs)
        if self.target is None:
            self.target = ground_bowl(self.instruction, objs)
        eef = obs["robot0_eef_pos"]
        bowl = objs[self.target]
        plate = find(objs, "plate")
        r, dz = ATTEMPTS[min(self.attempt, len(ATTEMPTS) - 1)]
        grasp = bowl + r * OFF_DIR + [0, 0, dz]
        ph, pt = self.phase, self.phase_t

        if ph == "above":
            goal = bowl + r * OFF_DIR + [0, 0, ABOVE_Z]
            if np.linalg.norm(goal - eef) < 0.015 or pt > 80:
                self._set("descend")
            return self._move(obs, goal, -1)
        if ph == "descend":
            if np.linalg.norm(grasp - eef) < 0.008 or pt > 40:
                self._set("close")
            return self._move(obs, grasp, -1)
        if ph == "close":
            if pt > 10:
                self.grip_pt = eef - bowl
                self.bowl_z0 = bowl[2]
                self._set("lift")
            return self._move(obs, grasp, 1)
        if ph == "lift":
            z = max(plate[2], self.bowl_z0) + LIFT_DZ
            # once the hand has risen 6 cm the bowl must have risen with it
            if eef[2] - self.grip_pt[2] > self.bowl_z0 + 0.06 and bowl[2] < self.bowl_z0 + 0.03:
                return self._retry("bowl did not lift", eef)
            if eef[2] > z - 0.02 or pt > 40:
                self._set("carry")
            return self._move(obs, np.array([eef[0], eef[1], z]), 1)
        if ph in ("carry", "lower"):
            hold = eef - bowl
            if hold[2] > self.grip_pt[2] + 0.04 or np.linalg.norm((hold - self.grip_pt)[:2]) > 0.05:
                return self._retry(f"bowl dropped during {ph}", eef)
            # Servo the bowl (not the hand) onto the plate centre, so slip of
            # the bowl inside the grasp is corrected.  Success needs about
            # +-2.5 cm in xy, so no offsets.
            goal = plate + hold
            if ph == "carry":
                goal[2] = max(eef[2], plate[2] + 0.12)
                if np.linalg.norm((plate - bowl)[:2]) < 0.008 or pt > 80:
                    self._set("lower")
            else:
                goal[2] = plate[2] + self.grip_pt[2] + PLACE_DZ
                if np.linalg.norm(goal - eef) < 0.01 or pt > 40:
                    self._set("release")
            return self._move(obs, goal, 1)
        if ph == "release":
            if pt > 10:
                self._set("retreat")
            return np.array([0, 0, 0, 0, 0, 0, -1.0])
        if ph == "regrasp":   # open and back off upward before re-approaching
            if pt > 8:
                self._set("above")
            return self._move(obs, np.array([eef[0], eef[1], self.retry_z]), -1)
        # retreat: the episode ends on success, so still being here means the
        # placement did not count -> pick the bowl up again.
        if pt > 15:
            return self._retry("placement not successful", eef)
        return self._move(obs, eef + [0, 0, 0.1], -1)
