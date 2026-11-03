"""Scripted pick-and-place for LIBERO-spatial ("pick up the black bowl ... place it on the plate").

Pipeline (no learning):
  1. perceive: back-project the agentview depth into world points; mean-shift on bowl-coloured
     points from a per-relation prior to the target bowl; find the plate near its prior.
  2. hover above the bowl; refine: re-estimate its centre from the top-down wrist camera
     (the oblique agentview estimate is biased ~4 cm towards -x).
  3. Rim grasp: gripper at bowl centre + GRASP_OFFSET * u, fingers closing along u so the bowl
     wall lies between them. u is the first direction in GRASP_DIRS whose outer-finger footprint
     is free in the wrist height map (u along x needs a 90 degree yaw).
  4. approach, descend, close, lift, carry, lower onto the plate, release, retreat.
"""

import numpy as np
import cv2

from perception import backproject, masks, TABLE_Z

# Approximate world-xy of the target bowl per spatial relation (agentview-estimate frame,
# from train-scene probing). Only a seed for a local search; perception decides.
BOWL_PRIORS = [
    ("between the plate and the ramekin", (-0.095, 0.20)),
    ("next to the ramekin", (-0.205, 0.32)),
    ("table center", (-0.10, 0.015)),
    ("on the cookie box", (0.05, 0.03)),
    ("top drawer", (0.063, -0.145)),
    ("on the ramekin", (-0.22, 0.195)),
    ("next to the cookie box", (0.11, -0.08)),
    ("on the stove", (-0.23, -0.12)),
    ("next to the plate", (-0.01, 0.315)),
    ("on the wooden cabinet", (0.015, -0.28)),
]
DEFAULT_PRIOR = (-0.1, 0.1)
PLATE_PRIOR = (0.05, 0.19)

AGENT_BIAS = np.array([0.04, 0.0])     # agentview bowl estimate is short by this much in +x
PLATE_BIAS = np.array([0.01, 0.006])   # agentview plate estimate vs top-down wrist estimate
BOWL_R = 0.05          # outer bowl radius measured from the wrist camera
GRASP_OFFSET = 0.044   # offset from bowl centre to grasp point along the closing axis

# Candidate closing directions in preference order: (unit vector in xy, yaw change in radians).
# +y works best empirically when its outer-finger footprint is free.
GRASP_DIRS = [
    (np.array([0.0, 1.0]), 0.0),
    (np.array([0.0, -1.0]), 0.0),
    (np.array([-1.0, 0.0]), np.pi / 2),
    (np.array([1.0, 0.0]), np.pi / 2),
]

# phase -> next phase, for the motion phases handled by Policy._<phase>
NEXT = dict(orient="hover", via1="via2", via2="hover", hover="refine", approach="descend", descend="close", close="lift", lift="carry",
            carry="lower", lower="release", release="retreat", retreat="retreat")


def log(*a):
    print(*a, flush=True)


def quat2mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rotvec(R):
    """Axis-angle vector of rotation matrix R."""
    ang = np.arccos(np.clip((np.trace(R) - 1) / 2, -1.0, 1.0))
    if ang < 1e-6:
        return np.zeros(3)
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    s = np.linalg.norm(v)
    if s < 1e-9:   # ~180 degrees: axis is the eigenvector of R + I with the largest eigenvalue
        return np.linalg.eigh(R + np.eye(3))[1][:, -1] * ang
    return v / s * ang


def rotz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def local_median(pts, c, radii, zpct, band=None):
    """Iteratively re-centre c on the median xy of pts within each radius.
    Returns (centre, z percentile of the last neighbourhood or None). With `band`,
    the centre uses only points within `band` of that top height (when >= 5 of them)."""
    z = None
    for radius in radii:
        near = pts[np.linalg.norm(pts[:, :2] - c, axis=1) < radius]
        if len(near) < 5:
            break
        z = float(np.percentile(near[:, 2], zpct))
        if band is not None:
            top = near[near[:, 2] > z - band]
            if len(top) >= 5:
                near = top
        c = np.median(near[:, :2], 0)
    return c, z


class Policy:
    def __init__(self, spec: dict):
        instruction = spec.get("instruction", "")
        self.drawer = "top drawer" in instruction
        cam = spec["cameras"]["agentview"]
        self.K = np.asarray(cam["intrinsic"], float)
        self.E = np.asarray(cam["extrinsic"], float)
        self.Kw = np.asarray(spec["cameras"]["robot0_eye_in_hand"]["intrinsic"], float)
        self.prior = np.array(next((xy for key, xy in BOWL_PRIORS if key in instruction),
                                   DEFAULT_PRIOR), float)
        self.reset()

    def reset(self) -> None:
        self.t = 0
        self.prev_pos = None
        self.plan = None
        self.R0 = None
        self.yaw = 0.0
        self._set("perceive")

    def _set(self, phase):
        if self.t:
            log(f"t={self.t} phase -> {phase}")
        self.phase = phase
        self.phase_t = 0
        self.zhist = []
        self.integ = np.zeros(3)

    # ------------------------------------------------------------------ perception
    def _perceive(self, obs):
        """Initial plan from the static agentview camera."""
        P = backproject(obs["agentview_depth"], self.K, self.E)
        bowl_m, plate_m = masks(obs["agentview_image"], P)
        # The robot can overlap the bowl's prior in the oblique view. Its high
        # grey pixels are not part of any bowl on the available supports.
        bowl_m &= P[..., 2] < 1.20
        bowl, ztop = local_median(P[bowl_m], self.prior, (0.08, 0.06, 0.05, 0.05), 97, band=0.03)
        plate, pz = local_median(P[plate_m], np.array(PLATE_PRIOR, float), (0.10, 0.08, 0.07), 90)
        ztop = TABLE_Z + 0.05 if ztop is None else ztop
        pz = TABLE_Z + 0.01 if pz is None else pz
        self.plan = dict(bowl=bowl + AGENT_BIAS, ztop=ztop, plate=plate + PLATE_BIAS, pz=pz,
                         safe_z=max(ztop + 0.10, 1.05), hover_z=max(ztop + 0.09, 1.04))
        log("agentview", {k: np.round(v, 3) for k, v in self.plan.items()})
        # Low bowls near the front edge need a path around the cabinet.
        self.plan["far"] = self.plan["bowl"][0] > 0.11 and ztop < 1.0

    def _wrist_bowl(self, obs, info, guess):
        """Top-down bowl (centre, half-extent, top z) from the eye-in-hand RGB-D, plus the
        obstacle height where the outer finger would go for each of GRASP_DIRS."""
        E = np.asarray(info["eye_in_hand_extrinsic"], float)
        P = backproject(obs["robot0_eye_in_hand_depth"], self.Kw, E)
        valid = (P[..., 2] < obs["robot0_eef_pos"][2] - 0.04) & (P[..., 2] > 0.5)  # drop fingers
        bm = masks(obs["robot0_eye_in_hand_image"], P)[0] & valid
        n, lab, stats, _ = cv2.connectedComponentsWithStats(bm.astype(np.uint8), connectivity=4)
        best, best_score = None, None
        for k in range(1, n):
            if stats[k, cv2.CC_STAT_AREA] < 40:
                continue
            q = P[lab == k]
            # keep the top 2.5 cm (rim ring + upper wall): separates a bowl from a flat
            # grey support it sits on (stove) that shares its colour
            ztop = float(np.percentile(q[:, 2], 99))
            q = q[q[:, 2] > ztop - 0.025]
            if len(q) < 20:
                continue
            lo, hi = np.percentile(q[:, :2], 1, 0), np.percentile(q[:, :2], 99, 0)
            ctr, half = (lo + hi) / 2, (hi - lo) / 2
            d = np.linalg.norm(ctr - guess)
            if d > 0.09:
                continue
            # bowl-sized blobs (outer radius ~0.05) are strongly preferred
            score = d + (0.0 if np.all((half > 0.035) & (half < 0.065)) else 1.0)
            if best is None or score < best_score:
                best, best_score = (ctr, half, ztop), score
        if best is None:
            return None
        rel = P[valid][:, :2] - best[0]
        zs = P[valid][:, 2]
        heights = []
        for u, _ in GRASP_DIRS:
            along = rel @ u
            perp = np.abs(rel @ np.array([-u[1], u[0]]))
            sel = (perp < 0.02) & (along > BOWL_R + 0.008) & (along < GRASP_OFFSET + 0.055)
            heights.append(float(np.percentile(zs[sel], 95)) if sel.sum() > 5 else -1.0)
        return best + (heights,)

    def _refine(self, obs, info):
        """Refine the bowl from the wrist camera and fix the grasp and place poses."""
        p = self.plan
        k = 0
        res = self._wrist_bowl(obs, info, p["bowl"])
        if res is None:
            log("wrist bowl not found; keep agentview estimate")
        else:
            ctr, half, zt, heights = res
            p["bowl"] = ctr
            if abs(zt - p["ztop"]) < 0.04:
                p["ztop"] = zt
            # first grasp direction whose outer-finger footprint is free (default +y)
            free = [h <= p["ztop"] - 0.015 for h in heights]
            k = free.index(True) if any(free) else 0
            log("wrist bowl", ctr.round(3), half.round(3), round(zt, 3),
                "outer-finger heights", np.round(heights, 3), "image choice", k)
        if self.drawer:
            k = 2  # the drawer walls flank the bowl on the y axis
        u, self.yaw = GRASP_DIRS[k]
        off = GRASP_OFFSET * u
        p["zg"] = p["ztop"] - 0.03                      # grasp height: 3 cm below the rim
        p["grasp_xy"] = p["bowl"] + off
        p["place_xy"] = p["plate"] + off
        # bowl bottom (ztop - 0.05) lands 2 cm above the plate top
        p["place_z"] = p["zg"] + (p["pz"] - (p["ztop"] - 0.05)) + 0.02

    # ------------------------------------------------------------------ control
    def _orient_err(self, obs):
        """Rotation vector from the current to the target (initial + yaw) orientation."""
        R = quat2mat(np.asarray(obs["robot0_eef_quat"], float))
        return rotvec(rotz(self.yaw) @ self.R0 @ R.T)

    def _move(self, obs, pos, target, grip, max_a=1.0, ki=0.15):
        """PI position control (integral only near the target), orientation servo when yawed."""
        err = (target - pos) / 0.05
        if np.linalg.norm(target - pos) < 0.04:
            self.integ = np.clip(self.integ + ki * err, -0.6, 0.6)
        a = np.zeros(7)
        a[:3] = np.clip(err + self.integ, -max_a, max_a)
        if self.yaw != 0.0:
            a[3:6] = np.clip(self._orient_err(obs) * 3.0, -1, 1)
        a[6] = grip
        return a

    def _stalled(self, pos, n=5, eps=0.002):
        """True once the eef has stopped moving downwards (contact or reach limit)."""
        self.zhist.append(pos[2])
        return len(self.zhist) > n + 3 and self.zhist[-n - 1] - self.zhist[-1] < eps

    def act(self, obs, info: dict):
        pos = np.asarray(obs["robot0_eef_pos"], float)
        self.speed = 0.0 if self.prev_pos is None else np.linalg.norm(pos - self.prev_pos)
        self.prev_pos = pos
        self.t += 1
        self.phase_t += 1
        if self.phase == "perceive":
            self.R0 = quat2mat(np.asarray(obs["robot0_eef_quat"], float))
            self._perceive(obs)
            if self.drawer:
                self.yaw = np.pi / 2
                self.orient_pos = pos.copy()
                self._set("orient")
            elif self.plan["far"]:
                self._set("via1")
            else:
                self._set("hover")
        if self.phase == "refine":
            self._refine(obs, info)
            self._set("approach")
        tgt, grip, done, *max_a = getattr(self, "_" + self.phase)(obs, pos, self.plan)
        if done:
            self._set(NEXT[self.phase])
        return self._move(obs, pos, tgt, grip, *max_a)

    # Motion phases: each returns (target eef position, gripper, phase done[, max action]).
    def _orient(self, obs, pos, p):
        return self.orient_pos, -1, np.linalg.norm(self._orient_err(obs)) < 0.08 or self.phase_t > 30

    def _via1(self, obs, pos, p):
        # Go around the cabinet before moving out toward a forward bowl.
        tgt = np.array([-0.04, 0.07, 1.10])
        return tgt, -1, np.linalg.norm(tgt - pos) < 0.025 or self.phase_t > 35

    def _via2(self, obs, pos, p):
        tgt = np.array([p["bowl"][0], 0.07, 1.04])
        return tgt, -1, np.linalg.norm(tgt - pos) < 0.025 or self.phase_t > 45

    def _hover(self, obs, pos, p):
        tgt = np.array([*p["bowl"], p["hover_z"]])
        if np.linalg.norm(tgt[:2] - pos[:2]) > 0.03 and pos[2] < p["safe_z"] - 0.03:
            tgt = np.array([pos[0], pos[1], p["safe_z"]])   # rise before moving sideways
        return tgt, -1, np.linalg.norm(tgt - pos) < 0.012 or self.phase_t > 45

    def _approach(self, obs, pos, p):
        tgt = np.array([*p["grasp_xy"], p["hover_z"]])
        if p["far"]:
            tgt[2] = max(p["ztop"] + 0.065, 1.01)
        settled = (np.linalg.norm(tgt[:2] - pos[:2]) < 0.008 and self.speed < 0.003
                   and np.linalg.norm(self._orient_err(obs)) < 0.08)
        return tgt, -1, settled or self.phase_t > 35

    def _descend(self, obs, pos, p):
        tgt = np.array([*p["grasp_xy"], p["zg"]])
        return tgt, -1, np.linalg.norm(tgt - pos) < 0.007 or self.phase_t > 35 or self._stalled(pos)

    def _close(self, obs, pos, p):
        return np.array([*p["grasp_xy"], p["zg"]]), 1, self.phase_t > 9

    def _lift(self, obs, pos, p):
        tgt = np.array([*p["grasp_xy"], p["safe_z"]])
        return tgt, 1, pos[2] > p["safe_z"] - 0.02 or self.phase_t > 30

    def _carry(self, obs, pos, p):
        # high enough to clear table-top objects with the bowl hanging below the gripper,
        # and first clear the bowl's own support
        tgt = np.array([*p["place_xy"], max(p["place_z"] + 0.10, 1.06)])
        if np.linalg.norm(pos[:2] - p["grasp_xy"]) < 0.15:
            tgt[2] = max(tgt[2], p["safe_z"])
        return tgt, 1, np.linalg.norm(tgt - pos) < 0.015 or self.phase_t > 60

    def _lower(self, obs, pos, p):
        tgt = np.array([*p["place_xy"], p["place_z"]])
        max_a = 1.0 if pos[2] - p["place_z"] > 0.05 else 0.5   # fast, then slow near the plate
        done = np.linalg.norm(tgt - pos) < 0.008 or self.phase_t > 40 or self._stalled(pos)
        return tgt, 1, done, max_a

    def _release(self, obs, pos, p):
        return pos, -1, self.phase_t > 8

    def _retreat(self, obs, pos, p):
        return np.array([pos[0], pos[1], p["safe_z"]]), -1, False
