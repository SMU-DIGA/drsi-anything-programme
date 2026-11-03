"""Scripted state-based policy for LIBERO-10.

Structure:
  * low level – Cartesian P-controller (`ctrl`, `move`, `move_path`, `move_R`).
  * skills    – Python generators that yield 7-D actions (grasp, pick, pick_place, ...).
  * planner   – `geometry.make_plan` turns the instruction into steps `(kind, *args)`;
                each step runs the task routine `do_<kind>(*args)`.
"""

import math

import numpy as np

import geometry as G


# ----------------------------------------------------------------------------- math

def quat_to_R(q):  # xyzw
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def Rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def Rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


R_DOWN = np.diag([1.0, -1.0, -1.0])  # gripper pointing down, fingers along world y


def rotvec(R):
    """Axis-angle vector of rotation matrix R."""
    c = min(1.0, max(-1.0, (np.trace(R) - 1) / 2))
    ang = math.acos(c)
    if ang < 1e-6:
        return np.zeros(3)
    s = math.sin(ang)
    if s < 1e-4:  # ~180 deg
        d = np.sqrt(np.maximum((np.diag(R) + 1) / 2, 0))
        i = int(np.argmax(d))
        axis = d.copy()
        for j in range(3):
            if j != i:
                axis[j] = (R[i, j] + R[j, i]) / (4 * d[i]) if d[i] > 1e-6 else 0
        return axis / np.linalg.norm(axis) * ang
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    return v / (2 * s) * ang


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def gripper_yaw(R):
    """Yaw of current gripper (inverse of Rz(yaw) @ R_DOWN)."""
    M = R @ R_DOWN.T
    return math.atan2(M[1, 0], M[0, 0])


def bbox(base):
    """Body-frame bounding box (lo, hi) of an object type (6 cm cube if unknown)."""
    lo, hi = G.BBOX.get(base, ([-0.03] * 3, [0.03] * 3))
    return np.array(lo), np.array(hi)


# ----------------------------------------------------------------------------- policy

class Policy:
    def __init__(self, spec: dict):
        self.instruction = spec.get("instruction", "")
        self.reset()

    def reset(self) -> None:
        self.gen = None
        self.obs = None
        self.t = 0

    def act(self, obs, info: dict):
        self.obs = obs
        if self.gen is None:
            self.instruction = str(obs.get("instruction", self.instruction))
            e = self.eef()
            # robot base sits ~0.46 m behind the initial eef position (measured)
            self.base = np.array([e[0] - 0.46, e[1]])
            self.gen = self.main()
        self.t += 1
        return np.clip(np.asarray(next(self.gen), dtype=float), -1, 1)

    # ---------------------------------------------------------------- observation helpers
    def eef(self):
        return np.asarray(self.obs["robot0_eef_pos"], dtype=float)

    def eef_R(self):
        return quat_to_R(self.obs["robot0_eef_quat"])

    def opos(self, name):
        return np.asarray(self.obs[name + "_pos"], dtype=float)

    def oR(self, name):
        return quat_to_R(self.obs[name + "_quat"])

    def grip_width(self):
        q = self.obs["robot0_gripper_qpos"]
        return float(q[0] - q[1])

    def log(self, *a):
        print("[t=%d]" % self.t, *a, flush=True)

    def obj_ref(self, name):
        """(centre xy, bottom z, top z) of an object in world, from its body-frame bbox."""
        base = G.base_name(name)
        P, R = self.opos(name), self.oR(name)
        lo, hi = bbox(base)
        wz = (self.corners(lo, hi) @ R.T + P)[:, 2]
        if base in G.RIM or base in G.CENTER:
            c = G.RIM[base]["center"] if base in G.RIM else G.CENTER[base]
            ctr = P + R @ np.array([c[0], c[1], 0.0])
        else:
            ctr = P + R @ ((lo + hi) / 2)
        return ctr[:2].copy(), float(wz.min()), float(wz.max())

    @staticmethod
    def corners(lo, hi):
        return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])

    # ---------------------------------------------------------------- low level
    def ctrl(self, target, yaw, grip, kp=25.0, vmax=1.0, kr=3.0, R_target=None):
        dp = (np.asarray(target, dtype=float) - self.eef()) * kp
        n = np.linalg.norm(dp)
        if n > vmax:
            dp = dp / n * vmax
        if R_target is None:
            R_target = Rz(yaw) @ R_DOWN
        dr = np.clip(rotvec(R_target @ self.eef_R().T) * kr, -1, 1)
        return np.concatenate([dp, dr, [grip]])

    def move(self, target, yaw, grip, tol=0.008, max_steps=120, vmax=1.0, rtol=0.08, stall=None):
        """P-control to target. If `stall` is set, give up when the position error has not
        shrunk by 2 mm within `stall` steps (blocked by contact)."""
        target = np.asarray(target, dtype=float)
        errs = []
        for _ in range(max_steps):
            rv = rotvec(Rz(yaw) @ R_DOWN @ self.eef_R().T)
            err = np.linalg.norm(target - self.eef())
            if err < tol and np.linalg.norm(rv) < rtol:
                return True
            errs.append(err)
            if stall and len(errs) > stall and errs[-stall - 1] - err < 0.002 and err > 2 * tol:
                self.log("move stalled, err %.3f" % err)
                return False
            yield self.ctrl(target, yaw, grip, vmax=vmax)
        return False

    def move_R(self, target, R_target, grip, tol=0.01, max_steps=100, vmax=1.0, rtol=0.1):
        """P-control to a position with an arbitrary gripper orientation."""
        target = np.asarray(target, dtype=float)
        for _ in range(max_steps):
            rv = rotvec(R_target @ self.eef_R().T)
            if np.linalg.norm(target - self.eef()) < tol and np.linalg.norm(rv) < rtol:
                return True
            yield self.ctrl(target, 0, grip, vmax=vmax, R_target=R_target)
        return False

    def move_path(self, target, yaw, grip, lookahead=0.05, vmax=1.0, **kw):
        """Follow the straight segment start->target with a carrot point, then converge."""
        start = self.eef()
        target = np.asarray(target, dtype=float)
        seg = target - start
        L = np.linalg.norm(seg)
        stall = kw.get("stall")
        if L > lookahead:
            u = seg / L
            hist = []
            for _ in range(int(L / 0.005) + 40):
                s = float(np.dot(self.eef() - start, u))
                if s > L - lookahead:
                    break
                hist.append(s)
                if stall and len(hist) > stall and s - hist[-stall - 1] < 0.002:
                    self.log("path stalled at %.3f / %.3f" % (s, L))
                    return False
                carrot = start + u * min(L, max(0.0, s) + lookahead)
                yield self.ctrl(carrot, yaw, grip, kp=40.0, vmax=vmax)
        return (yield from self.move(target, yaw, grip, vmax=vmax, **kw))

    def hold(self, n, grip, yaw=None, target=None):
        target = self.eef() if target is None else np.asarray(target)
        if yaw is None:
            yaw = gripper_yaw(self.eef_R())
        for _ in range(n):
            yield self.ctrl(target, yaw, grip)

    def lift(self, dz, yaw, grip, max_steps):
        """Straight move up by dz (used to back off after releasing / pushing)."""
        p = self.eef()
        yield from self.move_path(p + np.array([0, 0, dz]), yaw, grip, tol=0.02, max_steps=max_steps)

    # ---------------------------------------------------------------- grasping
    def grasp(self, gp, yaw, force=False):
        """Descend onto grasp point gp (eef target) with the given yaw and close.
        Unless `force`, a blocked descent aborts the grasp (backs off, returns False)."""
        gp = np.asarray(gp, dtype=float)
        above = gp + np.array([0, 0, 0.10])
        cur = self.eef()
        safe_z = max(cur[2], above[2])
        if cur[2] < above[2] - 0.02:
            yield from self.move_path([cur[0], cur[1], safe_z], yaw, -1, tol=0.02, max_steps=60)
        yield from self.move_path([above[0], above[1], safe_z], yaw, -1, tol=0.015)
        if safe_z > above[2] + 0.02:
            yield from self.move_path(above, yaw, -1, tol=0.015)
        ok = yield from self.move_path(gp, yaw, -1, tol=0.006, max_steps=60, vmax=0.6,
                                       stall=None if force else 8)
        if not ok and not force and self.eef()[2] > gp[2] + 0.015:
            self.log("descent blocked at z %.3f (target %.3f)" % (self.eef()[2], gp[2]))
            yield from self.lift(0.06, yaw, -1, max_steps=25)
            return False
        yield from self.hold(12, 1.0, yaw=yaw, target=gp)
        w = self.grip_width()
        self.log("grasp width %.4f" % w)
        return w > 0.004

    def release(self, yaw, retreat_dz=0.08, steps=10):
        yield from self.hold(steps, -1.0, yaw=yaw)
        yield from self.lift(retreat_dz, yaw, -1.0, max_steps=40)

    def grasp_spec(self, name, rim_side=None, handle=False):
        """(grasp point, finger-axis angle, blocker) for object `name`. `blocker` is a
        neighbour the open hand would collide with at the best generic grasp, else None.
        rim_side: preferred world xy direction of the rim point (cups/bowls);
        handle: grasp a mug by its handle (G.MUG_HANDLE)."""
        base = G.base_name(name)
        P, R = self.opos(name), self.oR(name)
        if handle and base in G.MUG_HANDLE:
            info = G.MUG_HANDLE[base]
        elif base in G.RIM:
            return self.rim_grasp(base, P, R, rim_side) + (None,)
        elif base in G.GRASP:
            info = G.GRASP[base]
        else:
            return self.box_grasp(name, P, R)
        ax = R @ np.array(info["axis"])
        return P + R @ np.array(info["point"]), math.atan2(ax[1], ax[0]), None

    @staticmethod
    def rim_grasp(base, P, R, side):
        """Point on the rim of a cup/bowl: facing the robot (-x) and away from the handle,
        or the one furthest along `side`."""
        r = G.RIM[base]
        c = np.array([r["center"][0], r["center"][1], r["z"]])
        best = None
        for ang in np.linspace(0, 2 * np.pi, 16, endpoint=False):
            u = np.array([math.cos(ang), math.sin(ang), 0.0])
            w = P + R @ (c + r["radius"] * u)
            if side is not None:
                score = -float(np.dot((R @ u)[:2], side))
            else:
                score = w[0] + 0.05 * abs(u[0])
            if best is None or score < best[0]:
                best = (score, w, R @ u)
        _, gp, ax = best
        return gp, math.atan2(ax[1], ax[0])

    def box_grasp(self, name, P, R):
        """Generic grasp: world-top centre, closing across the narrower horizontal extent;
        candidate offsets/angles are scored by finger clearance to the neighbours."""
        lo, hi = bbox(G.base_name(name))
        ctr = P + R @ ((lo + hi) / 2)
        wz = (self.corners(lo, hi) @ R.T + P)[:, 2]
        z = max(wz.max() - 0.025, wz.min() + 0.012)
        ext = hi - lo
        horiz = sorted([(ext[i], R[:, i]) for i in range(3) if abs(R[2, i]) < 0.7], key=lambda t: t[0])
        e, ax = horiz[0]
        cands = []  # (grasp xy, finger axis angle, preference cost)
        if len(horiz) > 1 and horiz[0][0] > 0.85 * horiz[1][0]:
            # nearly round: any finger direction works, prefer little rotation
            cur_phi = gripper_yaw(self.eef_R()) - math.pi / 2
            for a in np.linspace(0, math.pi, 12, endpoint=False):
                cands.append((ctr[:2], a, 0.01 * abs(wrap(2 * (a - cur_phi))) / 2))
        else:
            phi = math.atan2(ax[1], ax[0])
            L = horiz[1][0] if len(horiz) > 1 else 0.0
            lax = horiz[1][1][:2] / max(1e-6, np.linalg.norm(horiz[1][1][:2])) if len(horiz) > 1 else np.zeros(2)
            smax = max(0.0, L / 2 - 0.018)
            for dth in (0.0, -0.18, 0.18, -0.3, 0.3):
                # span across the fingers must stay below the opening (~7 cm usable)
                if e * math.cos(dth) + L * abs(math.sin(dth)) > 0.068:
                    continue
                for s in np.linspace(-smax, smax, 7) if smax > 0 else [0.0]:
                    cands.append((ctr[:2] + s * lax, phi + dth, 0.2 * abs(s) + 0.02 * abs(dth)))
        best = None
        for xy, a, pref in cands:
            clr, blk = self.finger_clearance(xy, a, name, z_tip=z - 0.013)
            score = min(clr, 0.03) - pref
            if best is None or score > best[0]:
                best = (score, xy, a, clr, blk)
        _, xy, a, clr, blk = best
        return np.array([xy[0], xy[1], z]), a, (blk if clr < -0.003 else None)

    def finger_clearance(self, xy, phi, exclude, z_tip, half_open=0.045, finger_r=0.013):
        """(clearance, closest object) between the open fingers (at xy +- half_open along phi)
        / the hand and the footprints of all other objects taller than the fingertips."""
        u = np.array([math.cos(phi), math.sin(phi)])
        v = np.array([-u[1], u[0]])
        pts = [np.asarray(xy) + half_open * u, np.asarray(xy) - half_open * u]
        clr, blocker = 1.0, None
        for o in G.objects_in(self.obs):
            before = clr
            b = G.base_name(o)
            if o == exclude or b not in G.BBOX:
                continue
            otop = self.obj_ref(o)[2]
            if otop < z_tip:
                continue
            lo, hi = bbox(b)
            P, R = self.opos(o), self.oR(o)
            c = P + R @ ((lo + hi) / 2)
            hext = (hi - lo) / 2
            if otop > z_tip + 0.05:  # hand bottom ~5 cm above the tips
                # the hand (+-0.105 along the finger axis, +-0.035 across) is low enough to hit it
                rad = max(hext[i] for i in range(3) if abs(R[2, i]) < 0.7)
                dc = c[:2] - np.asarray(xy)
                du = max(0.0, abs(np.dot(dc, u)) - 0.105 - rad)
                dv = max(0.0, abs(np.dot(dc, v)) - 0.035 - rad)
                clr = min(clr, math.hypot(du, dv) - 0.005)
            for p in pts:
                d = np.zeros(3)
                for i in range(3):
                    axw = R[:, i]
                    if abs(axw[2]) > 0.7:
                        continue  # vertical axis: ignore
                    a2 = axw[:2] / max(1e-6, np.linalg.norm(axw[:2]))
                    d[i] = max(0.0, abs(np.dot(p - c[:2], a2)) - hext[i])
                clr = min(clr, float(np.linalg.norm(d)) - finger_r)
            if clr < before:
                blocker = o
        return clr, blocker

    def j7_for(self, yaw, xy):
        """Rough wrist-joint estimate for gripper yaw `yaw` at world position xy."""
        e = self.eef()
        j1_cur = math.atan2(e[1] - self.base[1], e[0] - self.base[0])
        j1 = math.atan2(xy[1] - self.base[1], xy[0] - self.base[0])
        j7 = float(self.obs["robot0_joint_pos"][6])
        return j7 + (j1 - j1_cur) - wrap(yaw - gripper_yaw(self.eef_R()))

    def choose_yaw(self, phi, xy, xy2=None):
        """Yaw giving finger axis phi (mod pi) that keeps the wrist joint well inside limits
        at xy (and xy2, e.g. the place location)."""
        ref = gripper_yaw(self.eef_R())
        base = wrap(phi + math.pi / 2)
        best = None
        for k in (-1, 0, 1):
            y = wrap(base + k * math.pi)
            j = [self.j7_for(y, xy)] + ([self.j7_for(y, xy2)] if xy2 is not None else [])
            cost = (sum(max(0.0, abs(v) - 1.9) * 10 for v in j) + 0.25 * abs(wrap(y - ref))
                    + 0.15 * max(abs(v - 0.4) for v in j))
            if best is None or cost < best[0]:
                best = (cost, y)
        return best[1]

    def pick(self, name, xy2=None, force=False, rim_side=None):
        """One grasp attempt; returns the grasp yaw, or None (gripper reopened) on failure."""
        gp, phi, _ = self.grasp_spec(name, rim_side=rim_side)
        yaw = self.choose_yaw(phi, gp[:2], xy2=xy2)
        self.log("pick", name, "gp", np.round(gp, 3), "yaw %.2f" % yaw)
        ok = yield from self.grasp(gp, yaw, force=force)
        if ok and self.grip_width() > 0.0045:
            return yaw
        self.log("grasp failed (width %.4f), retry" % self.grip_width())
        yield from self.release(yaw, retreat_dz=0.06)
        return None

    # ---------------------------------------------------------------- planning helpers
    def path_clearance(self, a_xy, b_xy, exclude, margin=0.07):
        """Highest object top near the segment a->b (ignoring `exclude` and the basket)."""
        a, b = np.asarray(a_xy, float), np.asarray(b_xy, float)
        ab = b - a
        top = -1.0
        for o in G.objects_in(self.obs):
            base = G.base_name(o)
            if o == exclude or base not in G.BBOX or base == "basket":
                continue
            c, _, tp = self.obj_ref(o)
            t = 0.0 if np.dot(ab, ab) < 1e-9 else float(np.clip(np.dot(c - a, ab) / np.dot(ab, ab), 0, 1))
            lo, hi = G.BBOX[base]
            r = 0.5 * max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
            if np.linalg.norm(a + t * ab - c) < r + margin:
                top = max(top, tp)
        return top

    def free_spot(self, name, avoid, keep=0.13):
        """A free table spot near `name` (reachable, away from all other objects and from the
        `avoid` points / the segment between the first two of them)."""
        c0 = self.obj_ref(name)[0]
        others = []
        for o in G.objects_in(self.obs):
            if o == name or G.base_name(o) not in G.BBOX:
                continue
            lo, hi = G.BBOX[G.base_name(o)]
            R = self.oR(o)
            rad = max((hi[i] - lo[i]) / 2 for i in range(3) if abs(R[2, i]) < 0.7)
            others.append((self.obj_ref(o)[0], rad))
        lo, hi = G.BBOX[G.base_name(name)]
        myrad = 0.5 * max(hi[i] - lo[i] for i in range(3))
        best = None
        for dx in np.arange(-0.24, 0.241, 0.03):
            for dy in np.arange(-0.24, 0.241, 0.03):
                p = c0 + np.array([dx, dy])
                if not 0.35 <= np.linalg.norm(p - self.base) <= 0.68 or abs(p[1]) > 0.38 or p[0] > 0.25:
                    continue
                m = min([np.linalg.norm(p - c) - r - myrad for c, r in others] + [1.0])
                for a in avoid:
                    m = min(m, np.linalg.norm(p - a) - keep)
                if len(avoid) >= 2:
                    a, b = avoid[0], avoid[1]
                    ab = b - a
                    t = float(np.clip(np.dot(p - a, ab) / max(1e-9, np.dot(ab, ab)), 0, 1))
                    m = min(m, np.linalg.norm(a + t * ab - p) - 0.09)
                score = min(m, 0.06) - 0.1 * np.hypot(dx, dy)
                if m > 0.02 and (best is None or score > best[0]):
                    best = (score, p)
        return None if best is None else best[1]

    # ---------------------------------------------------------------- pick and place
    def pick_place(self, name, dest_xy, bottom_z, travel_z, yaw_place=None, release_dz=0.08,
                   adjust=None, rim_side=None, relocate=True):
        """Pick object, carry it with its bottom at travel_z and lower it until its centre is
        over dest_xy and its bottom at bottom_z; then release.
        adjust(bottom_z) -> xy shift (or None) is called when the final descent stalls."""
        # an unavoidable neighbour in the way of the hand? move it aside first
        blk = self.grasp_spec(name, rim_side=rim_side)[2]
        if relocate and blk is not None and G.base_name(blk) not in G.NOT_MOVABLE:
            spot = self.free_spot(blk, avoid=[self.obj_ref(name)[0], np.asarray(dest_xy)])
            if spot is not None:
                self.log("relocating blocker", blk, "to", np.round(spot, 3))
                bb = self.obj_ref(blk)[1]
                yield from self.pick_place(blk, spot, bb + 0.004, travel_z=bb + 0.03, relocate=False)

        # pick and lift above the obstacles on the way
        for attempt in range(3):
            bot0 = self.obj_ref(name)[1]
            yaw = yield from self.pick(name, xy2=dest_xy, force=attempt >= 1, rim_side=rim_side)
            if yaw is None:
                continue
            ctr0, bot, _ = self.obj_ref(name)
            clear = self.path_clearance(ctr0, dest_xy, name)
            tz = travel_z
            if clear + 0.03 > tz:
                self.log("raise travel for obstacle top %.3f" % clear)
                tz = clear + 0.03
            p = self.eef()
            lift_z = max(tz + (p[2] - bot), p[2] + 0.05)  # travel_z is for the object bottom
            yield from self.move_path([p[0], p[1], lift_z], yaw, 1.0, tol=0.02, vmax=0.8)
            if self.obj_ref(name)[1] > bot0 + 0.03 and self.grip_width() > 0.002:
                break
            self.log("object not lifted (attempt %d), retrying" % attempt)
            yield from self.release(yaw, retreat_dz=0.0, steps=6)
        else:
            return False

        # carry: eef destination from the object's measured offset in the hand
        if yaw_place is None:
            yaw_place = yaw
        ctr, bot, _ = self.obj_ref(name)
        p = self.eef()
        off = p[:2] - ctr
        if abs(wrap(yaw_place - yaw)) > 0.05:  # offset rotates with the gripper
            off = Rz(yaw_place - yaw)[:2, :2] @ off
        below = p[2] - bot
        dest = np.array([dest_xy[0] + off[0], dest_xy[1] + off[1], bottom_z + below])
        self.log("place", name, "eef dest", np.round(dest, 3), "below %.3f" % below)
        tz = max(lift_z, dest[2] + 0.03, p[2])
        yield from self.move_path([p[0], p[1], tz], yaw_place, 1.0, tol=0.02, vmax=0.8)
        yield from self.move_path([dest[0], dest[1], tz], yaw_place, 1.0, tol=0.008, vmax=0.8, max_steps=60)

        # closed-loop correction: re-measure where the object actually is in the hand
        for _ in range(3):
            err = np.asarray(dest_xy) - self.obj_ref(name)[0]
            if np.linalg.norm(err) < 0.004:
                break
            p = self.eef()
            dest[:2] = p[:2] + err
            yield from self.move(np.array([dest[0], dest[1], p[2]]), yaw_place, 1.0, tol=0.003, max_steps=25)

        # lower (optionally shifting when blocked) and release
        for _ in range(4):
            ok = yield from self.move_path(dest, yaw_place, 1.0, tol=0.01, vmax=0.5, max_steps=50,
                                           stall=6 if adjust else None)
            if ok or adjust is None:
                break
            bot = self.obj_ref(name)[1]
            d = adjust(bot)
            self.log("placement blocked (bottom %.3f), adjust %s" % (bot, d))
            if d is None:
                break
            yield from self.move(self.eef() + np.array([0, 0, 0.02]), yaw_place, 1.0, tol=0.006, max_steps=15)
            dest[:2] += np.asarray(d)
            p = self.eef()
            yield from self.move(np.array([dest[0], dest[1], p[2]]), yaw_place, 1.0, tol=0.004, max_steps=25)
        yield from self.release(yaw_place, retreat_dz=release_dz)
        return True

    # ---------------------------------------------------------------- planner
    def main(self):
        ins = self.instruction.lower()
        self.log("instruction:", ins)
        plan = G.make_plan(ins, self.obs)
        self.log("plan:", plan)
        for kind, *args in plan:
            yield from getattr(self, "do_" + kind)(*args)
        self.log("plan finished")
        while True:
            yield np.array([0, 0, 0, 0, 0, 0, -1.0])

    # ---------------------------------------------------------------- task routines
    def do_basket(self, name, slot):
        basket = self.opos("basket_1")
        dest = basket[:2] + np.array(slot)
        # basket rim top ~ basket_z + 0.146; release with object bottom ~2cm above rim
        bottom_z = basket[2] + 0.165
        yield from self.pick_place(name, dest, bottom_z, travel_z=bottom_z + 0.02)

    def do_on_plate(self, name, plate):
        pc, _, ptop = self.obj_ref(plate)
        yield from self.pick_place(name, pc, ptop + 0.012, travel_z=ptop + 0.08)

    def do_right_of(self, name, ref):
        # goal is a fixed table region ("living_room_table_plate_right_region", 5x5 cm)
        _, rbot, rtop = self.obj_ref(ref)
        dest = np.array(G.PLATE_RIGHT_REGION)
        # long axis of the box along x (fingers along world y) so it does not touch the plate
        yaw_place = self.choose_yaw(math.pi / 2, dest)
        yield from self.pick_place(name, dest, rbot + 0.01, travel_z=rtop + 0.06, yaw_place=yaw_place)

    def do_stove_on(self, knob_xy):
        """Pinch the knob bar (it lies along world x) and twist it counter-clockwise."""
        gp = np.array([knob_xy[0], knob_xy[1], G.STOVE_KNOB_Z])
        yaw = self.choose_yaw(math.pi / 2, gp[:2])  # fingers close along y (bar width)
        p = self.eef()
        yield from self.move_path([gp[0], gp[1], max(p[2], gp[2] + 0.08)], yaw, -1, tol=0.015)
        yield from self.move_path(gp, yaw, -1, tol=0.006, max_steps=50, vmax=0.5)
        yield from self.hold(8, 1.0, yaw=yaw, target=gp)
        self.log("knob grasp width %.4f" % self.grip_width())
        # twist in small increments
        tgt = yaw + 0.9
        for _ in range(40):
            cur = gripper_yaw(self.eef_R())
            if wrap(tgt - cur) < 0.05:
                break
            yield self.ctrl(gp, cur + min(0.3, wrap(tgt - cur)), 1.0)
        yield from self.hold(3, 1.0, target=gp)
        self.log("twist done yaw %.2f" % gripper_yaw(self.eef_R()))
        yield from self.release(gripper_yaw(self.eef_R()), retreat_dz=0.08, steps=6)

    def do_moka_on_stove(self, name, dest_xy):
        yield from self.pick_place(name, dest_xy, G.STOVE_TOP_Z, travel_z=G.STOVE_TOP_Z + 0.05)

    def do_book_caddy(self, name):
        """Standing book -> back compartment (6 x 13 cm, long side along world y)."""
        dest = np.array(G.CADDY_BACK[:2])
        # place with the book's thickness along world x: fingers along x
        yaw_place = self.choose_yaw(0.0, dest)

        def adjust(bottom):
            # caddy pose is only known to ~1 cm. The book pivots in the grasp about the finger
            # (x) axis when one of its ends lands on a y-wall: its up-axis then leans away from
            # the blocked end. Otherwise it rests on the back wall (top ~1.055: go +x) or on
            # the divider (top ~0.986: go -x).
            up = self.oR(name)[:, 2]
            if up[1] < -0.06:
                return (0.0, -0.01)
            if up[1] > 0.06:
                return (0.0, 0.01)
            if bottom > 1.02:
                return (0.012, 0.0)
            if bottom > 0.955:
                return (-0.012, 0.0)
            return None

        yield from self.pick_place(name, dest, G.CADDY_BACK[2], travel_z=G.CADDY_WALL_TOP + 0.03,
                                   yaw_place=yaw_place, adjust=adjust)

    def do_bowl_drawer(self, name):
        """Bowl into the (already open) bottom drawer, then push the drawer shut (+y)."""
        D = G.CABINET4
        # 1) open the drawer to its limit by pushing its front wall from the inside (-y);
        #    the stall position tells us where the wall is.
        yaw = self.choose_yaw(0.0, D["bowl_xy"])  # fingers along x -> thin in y
        s = np.array([D["bowl_xy"][0], D["probe_y"], D["probe_z"]])
        p = self.eef()
        yield from self.move_path([s[0], s[1], max(p[2], s[2] + 0.08)], yaw, 1.0, tol=0.015)
        yield from self.move_path(s, yaw, 1.0, tol=0.008, max_steps=40, vmax=0.6)
        hist = []
        for _ in range(60):
            y = self.eef()[1]
            hist.append(y)
            if len(hist) > 6 and hist[-6] - y < 0.0015:
                break
            yield self.ctrl([s[0], y - 0.02, s[2]], yaw, 1.0, kp=15.0)
        wall = self.eef()[1] - D["finger_half_y"]
        if not (D["wall_range"][0] < wall < D["wall_range"][1]):
            self.log("wall estimate %.3f out of range, using nominal" % wall)
            wall = D["wall_nominal"]
        self.log("drawer front wall inner y ~ %.3f" % wall)
        p = self.eef()
        yield from self.move_path([p[0], p[1] + 0.02, p[2] + 0.08], yaw, -1.0, tol=0.02, max_steps=30)
        # 2) bowl: grasp the rim on the robot side (fingers along x). The opening (front wall
        #    y~0.081 .. middle-drawer handle y~0.183) is narrower than the bowl, so lower it
        #    to just above the front wall and drop it in.
        dest = np.array([D["bowl_xy"][0], wall + D["bowl_from_wall"]])
        yield from self.pick_place(name, dest, D["bowl_release_bottom_z"],
                                   travel_z=D["bowl_release_bottom_z"] + 0.05, release_dz=0.10,
                                   rim_side=np.array([-1.0, 0.0]))
        yaw = self.choose_yaw(0.0, D["push_start"][:2])  # fingers along x: wide pusher
        # if the bowl came to rest on the drawer's front wall (tilted), shove it inside
        for _ in range(2):
            b = self.opos(name)
            if b[2] < D["bowl_rest_z"] + 0.004:
                break
            self.log("bowl resting high (z=%.3f), nudging" % b[2])
            p = self.eef()
            s = np.array([b[0], b[1] - 0.075, D["nudge_z"]])
            yield from self.move_path([s[0], s[1], max(p[2], s[2] + 0.06)], yaw, 1.0, tol=0.015, max_steps=50)
            yield from self.move_path(s, yaw, 1.0, tol=0.01, max_steps=30)
            yield from self.move_path(s + np.array([0, 0.045, 0]), yaw, 1.0, tol=0.008, max_steps=30, vmax=0.4)
            p = self.eef()
            yield from self.move_path([p[0], p[1] - 0.03, p[2] + 0.05], yaw, 1.0, tol=0.02, max_steps=20)
            yield from self.hold(5, 1.0, yaw=yaw)
        # 3) push the drawer shut with a forward-tilted gripper (palm stays clear of the
        #    middle drawer's handle)
        Rt = Rx(D["push_tilt"]) @ Rz(yaw) @ R_DOWN
        p = self.eef()
        start = np.array(D["push_start"])
        yield from self.move_path([p[0], start[1], max(p[2], start[2] + 0.10)], yaw, 1.0, tol=0.02, max_steps=50)
        yield from self.move_R([start[0], start[1], start[2] + 0.10], Rt, 1.0, tol=0.015, max_steps=40)
        yield from self.move_R(start, Rt, 1.0, tol=0.01, max_steps=40)
        end = np.array([start[0], D["push_end_y"], start[2]])
        yield from self.move_R(end, Rt, 1.0, tol=0.008, max_steps=70, vmax=0.5)
        for _ in range(10):
            yield self.ctrl(end + np.array([0, 0.02, 0]), 0, 1.0, R_target=Rt)
        p = self.eef()
        yield from self.move_R([p[0], p[1] - 0.08, p[2] + 0.05], Rt, 1.0, tol=0.02, max_steps=30)

    def do_mug_microwave(self, name):
        M = G.MICROWAVE6
        R = self.oR(name)
        # 1) grasp the handle; choose a yaw that can also rotate the mug so its handle
        #    (body +x) points to -y (towards the opening) at the insertion point
        psi0 = math.atan2(R[1, 0], R[0, 0])
        dpsi = wrap(-math.pi / 2 - psi0)
        gp, phi, _ = self.grasp_spec(name, handle=True)
        best = None
        for k in (-1, 0, 1):
            yg = wrap(phi + math.pi / 2 + k * math.pi)
            yp = yg + dpsi
            j = [self.j7_for(yg, gp[:2]), self.j7_for(yp, [M["mug_x"], M["eef_max_y"]])]
            cost = sum(max(0.0, abs(v) - 2.2) * 10 for v in j) + 0.3 * abs(wrap(yg - gripper_yaw(self.eef_R())))
            if best is None or cost < best[0]:
                best = (cost, yg, yp)
        _, yg, yp = best
        self.log("mug: psi0 %.2f dpsi %.2f yaw grasp %.2f place %.2f" % (psi0, dpsi, yg, yp))
        yield from self.grasp(gp, yg)
        # 2) lift above the open door, rotate to the staging point in front of the opening,
        #    lower and slide the mug in
        _, bot, _ = self.obj_ref(name)
        p = self.eef()
        below = p[2] - bot
        tz = M["travel_bottom_z"] + below
        yield from self.move_path([p[0], p[1], tz], yg, 1.0, tol=0.02, vmax=0.8)
        ctr = self.obj_ref(name)[0]
        p = self.eef()
        off = Rz(yp - yg)[:2, :2] @ (p[:2] - ctr)  # eef - cup centre after the rotation
        stage = np.array([M["mug_x"] + off[0], M["stage_y"], tz])
        yield from self.move_path(stage, yp, 1.0, tol=0.012, vmax=0.8, max_steps=80)
        low = np.array([stage[0], stage[1], M["insert_bottom_z"] + below])
        yield from self.move_path(low, yp, 1.0, tol=0.008, vmax=0.6, max_steps=40)
        ins = np.array([stage[0], M["eef_max_y"], low[2]])
        yield from self.move_path(ins, yp, 1.0, tol=0.006, vmax=0.5, max_steps=60)
        self.log("mug inserted at", np.round(self.opos(name), 3))
        yield from self.hold(8, -1.0, yaw=yp, target=ins - np.array([0, 0, 0.01]))
        p = self.eef()
        yield from self.move_path([p[0], p[1] - 0.01, p[2] + 0.06], yp, -1.0, tol=0.015, max_steps=30)
        # 3) push the handle further in with closed fingertips (fingers along x: thin in y)
        yawp = self.choose_yaw(0.0, ins[:2])
        s = np.array([self.opos(name)[0], M["eef_max_y"] - 0.07, M["push_z"]])
        p = self.eef()
        yield from self.move_path([s[0], s[1], p[2]], yawp, 1.0, tol=0.015, max_steps=40)
        yield from self.move_path(s, yawp, 1.0, tol=0.01, max_steps=40)
        yield from self.move_path([s[0], M["eef_max_y"] + 0.003, s[2]], yawp, 1.0, tol=0.006, max_steps=50, vmax=0.4)
        self.log("mug pushed to", np.round(self.opos(name), 3))
        p = self.eef()
        yield from self.move_path([p[0], p[1] - 0.04, M["door_z"] + 0.12], yawp, 1.0, tol=0.02, max_steps=40)
        # 4) close the door: sweep the outer face of the door around the hinge
        hinge = np.array(M["main"]) + np.array(M["hinge_offset"])
        r, d, z = M["door_r"], M["door_d"], M["door_z"]

        def door_pt(th):
            return np.array([hinge[0] + r * math.cos(th) + d * math.sin(th),
                             hinge[1] + r * math.sin(th) - d * math.cos(th), z])

        yawd = self.choose_yaw(0.0, door_pt(0.0)[:2])
        th = M["door_theta0"]
        s = door_pt(th)
        yield from self.move_path([s[0], s[1], z + 0.12], yawd, 1.0, tol=0.02, max_steps=60)
        yield from self.move_path(s, yawd, 1.0, tol=0.012, max_steps=40)
        while th < M["door_theta1"]:
            th = min(M["door_theta1"], th + 0.05)
            tgt = door_pt(th)
            for _ in range(3):
                yield self.ctrl(tgt, yawd, 1.0)
        # finish with a straight push into the frame (hinge position is only known to ~1 cm)
        fin = door_pt(0.0) + np.array([0.0, 0.04, 0.0])
        for _ in range(12):
            yield self.ctrl(fin, yawd, 1.0)
        self.log("door sweep done; mug at", np.round(self.opos(name), 3))
        p = self.eef()
        yield from self.move_path([p[0], p[1] - 0.06, p[2] + 0.05], yawd, 1.0, tol=0.02, max_steps=30)
