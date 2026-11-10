"""RoboCasa365 single-skill stage: improvement curve and per-task dev table, read from the run archives.

    python scripts/make_robocasa.py /path/to/DRSI-Anything

Writes _includes/curves-robocasa.html and _includes/table-robocasa.html. Stage 1 is runs/robocasa_vision_code_atomic
(36 fresh train episodes per version); its round-10 program was checked on dev once by hand after the run
(manual/g010c0_dev). Stage 2 is runs/robocasa_vision_code_atomic2, started from that program (54 per version)."""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "../DRSI-Anything")
SITE = Path(__file__).resolve().parent.parent
S1, S2 = ROOT / "runs/robocasa_vision_code_atomic", ROOT / "runs/robocasa_vision_code_atomic2"
MANUAL = S1 / "manual/g010c0_dev/summary.json"

NAMES = {
    "CloseFridge": "Close the fridge", "PickPlaceSinkToCounter": "Pick from the sink, place on the counter",
    "PickPlaceCounterToCabinet": "Pick from the counter, place in a cabinet",
    "PickPlaceCounterToStove": "Pick from the counter, place on the stove",
    "SlideDishwasherRack": "Slide the dishwasher rack", "TurnOnMicrowave": "Turn on the microwave",
    "OpenDrawer": "Open a drawer", "PickPlaceDrawerToCounter": "Pick from a drawer, place on the counter",
    "CloseToasterOvenDoor": "Close the toaster oven door", "OpenStandMixerHead": "Open the stand mixer head",
    "TurnOnElectricKettle": "Turn on the electric kettle", "NavigateKitchen": "Navigate to a fixture",
    "CloseBlenderLid": "Close the blender lid", "CoffeeSetupMug": "Set a mug under the coffee machine",
    "OpenCabinet": "Open a cabinet", "PickPlaceToasterToCounter": "Pick from the toaster, place on the counter",
    "TurnOffStove": "Turn off the stove", "TurnOnSinkFaucet": "Turn on the sink faucet",
}


def load(path):
    return json.loads(Path(path).read_text())


def rate(summary):
    eps = summary["episodes"]
    return sum(int(e["success"]) for e in eps) / len(eps)


def versions(run):
    """Per round: the version made in it, its fresh-seed train rate (None if voided or not measured yet) and its
    dev rate when it was checked on dev."""
    out = []
    for meta in sorted(run.glob("archive/*/meta.json"), key=lambda p: load(p)["generation"]):
        m = load(meta)
        train = m.get("train") or {}
        tr = train.get("mean") if train.get("seeds") else None
        dev = meta.parent / "eval_dev/summary.json"
        out.append({"id": m["id"], "round": m["generation"], "train": tr if tr is None or tr >= 0 else None,
                    "dev": rate(load(dev)) if dev.exists() else None, "promoted": bool(m.get("promoted"))})
    return out


def per_task(run, gid, summary=None):
    names = [t for t, _ in load(run / "config.json")["task"]["tasks"]]
    summary = summary or load(run / f"archive/{gid}/eval_dev/summary.json")
    by = {}
    for e in summary["episodes"]:
        k = names[e["seed"] // 1000]
        by[k] = by.get(k, 0) + int(e["success"])
    return by


v1, v2 = versions(S1), versions(S2)
manual = rate(load(MANUAL))
v1[-1]["dev"] = manual          # round 10 of stage 1, checked by hand after the run
n1, n2 = max(v["round"] for v in v1), max(v["round"] for v in v2)
live = load(S2 / "state.json")
best2 = [v for v in v2 if v["promoted"] and v["dev"] is not None][-1]

# x positions: stage 1 rounds 0..n1, then stage 2 rounds 1..n2 continue at n1+1..; stage 2's round 0 is stage 1's 10.
W, H, X0, X1, Y0, Y1, TOP = 640, 260, 52, 624, 214, 44, 0.5
span = n1 + max(n2, 10)
x = lambda i: X0 + (X1 - X0) * i / span
y = lambda v: Y0 - (Y0 - Y1) * v / TOP
pct = lambda v: f"{100 * v:.1f}%"

o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="RoboCasa365 single skills: hidden dev success of the best '
     f'version by round, and fresh train success of each round\'s version">',
     f'<text class="c-title" x="12" y="22">RoboCasa365 · 18 single-skill tasks · vision, code only</text>']
for t in (0, 0.1, 0.2, 0.3, 0.4, 0.5):
    o.append(f'<line class="c-grid" x1="{X0}" x2="{X1}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
             f'<text class="c-tick" x="{X0 - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{round(100 * t)}%</text>')
for i in range(0, span + 1, 2):
    lab = "start" if i == 0 else (f"r{i}" if i <= n1 else f"r{i - n1}")
    o.append(f'<text class="c-tick" x="{x(i):.1f}" y="{Y0 + 18}" text-anchor="middle">{lab}</text>')
xb = x(n1)
o.append(f'<line class="c-ref" x1="{xb:.1f}" x2="{xb:.1f}" y1="{Y1 - 8}" y2="{Y0}"/>'
         f'<text class="c-ref-label" x="{(X0 + xb) / 2:.1f}" y="{Y1 - 2}" text-anchor="middle">stage 1 · 36 train episodes per round</text>'
         f'<text class="c-ref-label" x="{(xb + X1) / 2:.1f}" y="{Y1 - 2}" text-anchor="middle">stage 2 · 54 per round</text>')

# train of each round's version (dashed)
tr = [(v["round"], v["train"], v["id"], 1) for v in v1] + [(n1 + v["round"], v["train"], v["id"], 2) for v in v2 if v["round"] > 0]
seg, segs = [], []
for i, t, _, _ in tr:
    if t is None:
        segs.append(seg); seg = []
    else:
        seg.append(f"{x(i):.1f},{y(t):.1f}")
segs.append(seg)
for s in segs:
    if len(s) > 1:
        o.append(f'<polyline class="c-line c-line2" points="{" ".join(s)}"/>')

# best version on dev so far (step line), with a dot at each dev check
best, pts, dots = None, [], []
for i, v, stage in [(v["round"], v, 1) for v in v1] + [(n1 + v["round"], v, 2) for v in v2 if v["round"] > 0]:
    if v["dev"] is not None:
        new = v["dev"] if (best is None or v["promoted"] or v["id"] == "g000" or (stage == 1 and v is v1[-1])) else best
        tip = (f"stage {stage} round {v['round']} ({v['id']}): {pct(v['dev'])} on hidden dev"
               + (", checked by hand after the run" if stage == 1 and v is v1[-1] else "")
               + ("" if new == v["dev"] else ", not promoted"))
        if best is not None and new != best:
            pts.append(f"{x(i):.1f},{y(best):.1f}")
        dots.append((i, v["dev"], tip, new == v["dev"]))
        best = new
    if best is not None:
        pts.append(f"{x(i):.1f},{y(best):.1f}")
o.append(f'<polyline class="c-line" points="{" ".join(pts)}"/>')
for i, d, tip, kept in dots:
    o.append(f'<g class="c-pt"><circle class="c-hit" cx="{x(i):.1f}" cy="{y(d):.1f}" r="12"/>'
             f'<circle class="c-dot{"" if kept else " c-dot-off"}" cx="{x(i):.1f}" cy="{y(d):.1f}" r="4.5"/><title>{tip}</title></g>')
for i, d, _, kept in dots:
    if kept and d in (dots[0][1], manual, best):
        first = i == dots[0][0]
        o.append(f'<text class="c-val" x="{x(i) + (8 if first else -6):.1f}" y="{y(d) - 10:.1f}" '
                 f'text-anchor="{"start" if first else "end"}">{pct(d)}</text>')
lx = X1 - 4
o.append(f'<line class="c-line" x1="{lx - 196}" x2="{lx - 176}" y1="{Y0 - 34}" y2="{Y0 - 34}"/>'
         f'<text class="c-tick" x="{lx - 170}" y="{Y0 - 30}">best version, hidden dev</text>'
         f'<line class="c-line c-line2" x1="{lx - 196}" x2="{lx - 176}" y1="{Y0 - 16}" y2="{Y0 - 16}"/>'
         f'<text class="c-tick" x="{lx - 170}" y="{Y0 - 12}">each round, fresh train</text>')
o.append("</svg>")
(SITE / "_includes/curves-robocasa.html").write_text(
    '<div class="curves curves-1">\n<div class="curve">' + "".join(o) + "</div>\n</div>\n")

# per-task dev table: start of stage 1, end of stage 1 (= start of stage 2), best of stage 2
cols = [per_task(S1, "g000"), per_task(S1, None, load(MANUAL)), per_task(S2, best2["id"])]
rows = sorted(NAMES, key=lambda k: (-cols[2].get(k, 0), -cols[1].get(k, 0), NAMES[k]))
html = []
for k in rows:
    a, b, c = (col.get(k, 0) for col in cols)
    if a == b == c == 0:
        continue
    html.append(f'          <tr><td>{NAMES[k]}</td><td class="num">{a}</td><td class="num">{b}</td>'
                f'<td class="num">{"<strong>%d</strong>" % c if c > b else c}</td></tr>')
zero = [NAMES[k] for k in rows if all(col.get(k, 0) == 0 for col in cols)]
tot = [sum(col.values()) / 72 for col in cols]
html.append(f'          <tr class="best"><td>All 18 tasks (72 episodes)</td><td class="num">{pct(tot[0])}</td>'
            f'<td class="num">{pct(tot[1])}</td><td class="num"><strong>{pct(tot[2])}</strong></td></tr>')
(SITE / "_includes/table-robocasa.html").write_text("\n".join(html) + "\n")
print("stage 2 at round", live.get("generation"), "best", best2["id"], pct(best2["dev"]), "| zero:", "; ".join(zero))
print("dev checks:", [(t, pct(d)) for _, d, t, _ in dots])
