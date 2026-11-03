"""Static knowledge about LIBERO-10 objects/fixtures (measured with probes, see NOTES.md)
and the instruction -> plan parser."""

import re

# Body-frame bounding boxes of collision geometry: base name -> (lo, hi)
BBOX = {
    "alphabet_soup": [[-0.0313, -0.0386, -0.0349], [0.0311, 0.0376, 0.0275]],
    "tomato_sauce": [[-0.0312, -0.0386, -0.0341], [0.031, 0.0376, 0.0275]],
    "basket": [[-0.0841, -0.0785, 0.0042], [0.0854, 0.0788, 0.1457]],
    "butter": [[-0.0381, -0.0198, -0.0087], [0.0381, 0.0198, 0.0087]],
    "cream_cheese": [[-0.0406, -0.0213, -0.0089], [0.0406, 0.0213, 0.0089]],
    "ketchup": [[-0.0277, -0.0724, -0.0176], [0.0286, 0.0732, 0.0191]],
    "milk": [[-0.0265, -0.0697, -0.0263], [0.0266, 0.0614, 0.0263]],
    "orange_juice": [[-0.0266, -0.0697, -0.0263], [0.0264, 0.0614, 0.0263]],
    "chefmate_8_frypan": [[-0.0968, -0.1032, 0.0008], [0.2593, 0.1011, 0.0587]],
    "moka_pot": [[-0.0406, -0.0563, -0.0661], [0.0408, 0.0912, 0.0857]],
    "akita_black_bowl": [[-0.0538, -0.0539, 0.0016], [0.0534, 0.0531, 0.0521]],
    "wine_bottle": [[-0.0207, -0.022, 0.0011], [0.0219, 0.0222, 0.158]],
    "plate": [[-0.068, -0.0684, -0.0025], [0.0696, 0.0691, 0.0164]],
    "porcelain_mug": [[-0.0647, -0.0494, 0.0024], [0.06, 0.0469, 0.1085]],
    "red_coffee_mug": [[-0.0607, -0.0472, -0.0018], [0.0622, 0.046, 0.1308]],
    "white_yellow_mug": [[-0.0713, -0.053, -0.0001], [0.0684, 0.0531, 0.1031]],
    "black_book": [[-0.0148, -0.0673, 0.0022], [0.0139, 0.043, 0.1366]],
    "chocolate_pudding": [[-0.0406, -0.0232, -0.0131], [0.0396, 0.0232, 0.0143]],
}

# Explicit grasps: eef point and finger-closing axis, both in the object's body frame.
GRASP = {
    # handle of the moka pot (thin in local x), at mid height of its vertical bar
    "moka_pot": {"point": [0.0, 0.075, 0.035], "axis": [1, 0, 0]},
    # standing book: across its thickness, a few cm below the top edge
    "black_book": {"point": [0.0, -0.012, 0.105], "axis": [1, 0, 0]},
}

# Rim grasps for cups/bowls: cup centre (body frame xy), wall radius, eef height (body z)
RIM = {
    "porcelain_mug": {"center": [0.012, 0.0], "radius": 0.042, "z": 0.092},
    "white_yellow_mug": {"center": [-0.019, 0.0], "radius": 0.047, "z": 0.088},
    "red_coffee_mug": {"center": [0.0, 0.0], "radius": 0.040, "z": 0.11},
    "akita_black_bowl": {"center": [0.0, 0.0], "radius": 0.047, "z": 0.038},
}

# Handle grasp (microwave task): outer vertical bar of the yellow-white mug's handle (body +x)
MUG_HANDLE = {"white_yellow_mug": {"point": [0.058, 0.0, 0.068], "axis": [0, 1, 0]}}
CENTER = {"moka_pot": [0.0, 0.0]}  # body-frame xy centre override (handle excluded)

# Fixtures (not observed): nominal world positions measured at reset.
# Flat stove: knob (hinge about z, on when angle > ~0.45 rad) sits at the stove main body;
# burner / cook region (On-region is +-6 cm around it) is +0.15 m in x from the main body.
STOVE_SCENE3 = [-0.202, 0.198]   # "turn on the stove and put the moka pot on it"  (+-1 cm)
STOVE_SCENE8 = [-0.206, -0.202]  # "put both moka pots on the stove" (starts switched on)
STOVE_KNOB_Z = 0.937             # eef height to pinch the knob bar (bar top 0.955, disc 0.918)
STOVE_TOP_Z = 0.935              # release moka pot with its bottom at about this height
# Study scene 1: desk caddy (rotated 180 deg) at (-0.403, -0.143, 0.887) +-1 cm.
# Back compartment interior: x in [-0.466, -0.405], y in [-0.21, -0.076], floor z 0.901;
# goal region site at (-0.437, -0.142, 0.973). Tallest caddy wall top ~1.055.
CADDY_BACK = [-0.436, -0.1455, 0.906]  # target xy for the book centre, release bottom z
# (back compartment y-walls at caddy_y + 0.062 and caddy_y - 0.067: centre caddy_y - 0.0025)
CADDY_WALL_TOP = 1.06
# Kitchen scene 4: white cabinet at (0.004, 0.298, 0.905) +-1 cm, bottom drawer opens along -y
# and starts open by ~0.15 m (closed predicate needs it fully shut, joint ~ +0.01).
# Open drawer interior exposed in front of the cabinet: x [-0.095, 0.11], y [0.08, 0.214],
# floor z 0.926. Drawer front plate at y ~0.07 (open), ~0.22 (closed); handle z 0.938-0.954.
# Middle drawer handle protrudes to y~0.183 at z 1.007-1.024, so neither the bowl nor the
# palm can go straight down/forward there.
CABINET4 = {
    "bowl_xy": [0.006, 0.128],
    # drawer-opening probe: closed fingertips inside the drawer push the front wall to -y
    "probe_y": 0.14, "probe_z": 0.966, "finger_half_y": 0.012,
    "wall_range": [0.055, 0.10], "wall_nominal": 0.076,
    # at the open limit (q=-0.16) the gap wall -> middle handle is ~0.116 m (bowl 0.107)
    "bowl_from_wall": 0.058,
    "bowl_release_bottom_z": 0.945,
    "bowl_rest_z": 0.926,               # bowl body z when lying flat on the drawer floor
    "nudge_z": 0.99,                    # fingertip height to shove a bowl stuck on the wall
    "push_start": [0.006, 0.0, 0.946],   # bottom-drawer handle front at y~0.037 (open)
    "push_end_y": 0.19,                  # handle front when fully closed ~0.187
    "push_tilt": 0.6,                    # rad, fingertips lead toward +y
}
# Kitchen scene 6: microwave main body ~(-0.001, 0.348, 0.92) +-1 cm, opening faces -y.
# Cavity (rel. main): x [-0.143, 0.062], y [-0.089, 0.08]; floor z 0.945, ceiling 1.087.
# Door hinge at main + (-0.172, -0.088), axis +z, door length ~0.26, 0.029 thick on the
# outer side of the hinge line; starts open (q -2.06..-1.43), closed predicate needs q~0.
# "In heating region" holds for mug origin y >= ~0.27 (rel. world).
MICROWAVE6 = {
    "main": [-0.001, 0.348],
    "mug_x": -0.022,            # a bit right of the cavity centre: keeps the hand off the door
    "eef_max_y": 0.212,         # hand (+-0.035 in y) must stay in front of the opening
    "insert_bottom_z": 0.957,   # mug bottom while sliding in (floor 0.945)
    "travel_bottom_z": 1.075,   # hand (+-0.105 along x) passes above the open door (top 1.11)
    "stage_y": 0.12,
    "push_z": 0.97,             # closed fingertips on the lower part of the handle
    "hinge_offset": [-0.172, -0.088],  # door hinge rel. main body
    "door_r": 0.17, "door_d": 0.045, "door_z": 1.088,
    "door_theta0": -2.25, "door_theta1": 0.07,
}
# living-room scene 6: goal region for "to the right of the plate" (site, +-2.5 cm)
PLATE_RIGHT_REGION = [0.15, 0.10]

# objects never relocated when they block a grasp
NOT_MOVABLE = ("basket", "plate", "chefmate_8_frypan", "wine_bottle")


def base_name(name):
    return re.sub(r"_\d+$", "", name)


NOUNS = [
    ("yellow and white mug", "white_yellow_mug"),
    ("white mug", "porcelain_mug"),
    ("red mug", "red_coffee_mug"),
    ("alphabet soup", "alphabet_soup"),
    ("tomato sauce", "tomato_sauce"),
    ("cream cheese", "cream_cheese"),
    ("butter", "butter"),
    ("ketchup", "ketchup"),
    ("milk", "milk"),
    ("orange juice", "orange_juice"),
    ("chocolate pudding", "chocolate_pudding"),
    ("black bowl", "akita_black_bowl"),
    ("book", "black_book"),
    ("moka pot", "moka_pot"),
]


def objects_in(obs):
    return sorted(k[:-4] for k in obs if k.endswith("_pos") and not k.startswith("robot") and "_to_" not in k)


def resolve(phrase, obs):
    """Map a noun phrase to an observed object name (e.g. 'white mug' -> porcelain_mug_1)."""
    objs = objects_in(obs)
    for txt, base in NOUNS:
        if txt in phrase:
            for o in objs:
                if base_name(o) == base:
                    return o
    words = [w for w in re.findall(r"[a-z]+", phrase) if w not in ("the", "a", "box")]
    return max(objs, key=lambda o: sum(w in o for w in words))


def make_plan(ins, obs):
    """Instruction -> list of steps (kind, *args); Policy runs `do_<kind>(*args)` for each."""
    ins = ins.lower().strip().rstrip(".")
    objs = objects_in(obs)

    def of_type(base):
        return [o for o in objs if base_name(o) == base]

    m = re.match(r"put both the (.+?) and the (.+?) in the basket", ins)
    if m:
        a, b = resolve(m.group(1), obs), resolve(m.group(2), obs)
        return [("basket", a, (0.0, -0.03)), ("basket", b, (0.0, 0.035))]
    m = re.match(r"put the (.+?) on the left plate and put the (.+?) on the right plate", ins)
    if m:
        plates = sorted(of_type("plate"), key=lambda o: obs[o + "_pos"][1])
        a, b = resolve(m.group(1), obs), resolve(m.group(2), obs)
        return [("on_plate", a, plates[0]), ("on_plate", b, plates[-1])]
    m = re.match(r"put the (.+?) on the plate and put the (.+?) to the right of the plate", ins)
    if m:
        plate = of_type("plate")[0]
        a, b = resolve(m.group(1), obs), resolve(m.group(2), obs)
        return [("on_plate", a, plate), ("right_of", b, plate)]
    if "turn on the stove" in ins:
        knob = STOVE_SCENE3
        burner = [knob[0] + 0.15, knob[1]]
        return [("stove_on", knob), ("moka_on_stove", of_type("moka_pot")[0], burner)]
    if "both moka pots" in ins:  # the stove starts switched on in this scene
        bx, by = STOVE_SCENE8[0] + 0.15, STOVE_SCENE8[1]
        # nearest pot first goes to the far slot
        pots = sorted(of_type("moka_pot"), key=lambda o: (obs[o + "_pos"][0] - bx) ** 2 + (obs[o + "_pos"][1] - by) ** 2)
        return [("moka_on_stove", pots[0], [bx + 0.045, by]),
                ("moka_on_stove", pots[1], [bx - 0.045, by])]
    if "book" in ins and "caddy" in ins:
        return [("book_caddy", resolve("book", obs))]
    if "drawer" in ins:
        return [("bowl_drawer", resolve(ins.split(" in the ")[0], obs))]
    if "microwave" in ins:
        return [("mug_microwave", resolve(ins.split(" in the ")[0], obs))]
    return []
