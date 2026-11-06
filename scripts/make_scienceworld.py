"""Write the ScienceWorld includes: overall curve, 30 per-task curves, per-task table.

Ours: the DRSI-Anything run runs/scienceworld (one program for all 30 task types). Scores are ScienceWorld's task
score 0-100 at the end of an episode, a failed task counted as 0. "Full test" = every official test variation
once (1,819 episodes); "300-seed test" = 10 seeds per task type (variations repeat where a type has fewer than
10); dev = 90 hidden seeds. The per-task curves use the full test of the incumbent of every generation.

References: SwiftSage (Lin et al., NeurIPS 2023, arXiv 2305.17390) Table 1: the first 10 test variations of each
task type (270 episodes), a failed episode counted at its last non-negative score. SwiftSage = fine-tuned
flan-T5 (on oracle trajectories) + GPT-4 at run time; Reflexion, ReAct, SayCan with GPT-4; DRRN from the
ScienceWorld paper.
Usage: python3 scripts/make_scienceworld.py [RUNS_DIR]
"""
import json, math, re, sys
from pathlib import Path

RUNS = Path(sys.argv[1] if len(sys.argv) > 1 else "../DRSI-Anything/runs")
RUN = RUNS / "scienceworld"
HERE = Path(__file__).resolve().parent.parent

# ScienceWorld task ids, in the order of the benchmark paper
TASKS = [("1-1", "boil"), ("1-2", "melt"), ("1-3", "freeze"), ("1-4", "change-the-state-of-matter-of"),
         ("2-1", "use-thermometer"), ("2-2", "measure-melting-point-known-substance"),
         ("2-3", "measure-melting-point-unknown-substance"), ("3-1", "power-component"),
         ("3-2", "power-component-renewable-vs-nonrenewable-energy"), ("3-3", "test-conductivity"),
         ("3-4", "test-conductivity-of-unknown-substances"), ("4-1", "find-living-thing"),
         ("4-2", "find-non-living-thing"), ("4-3", "find-plant"), ("4-4", "find-animal"), ("5-1", "grow-plant"),
         ("5-2", "grow-fruit"), ("6-1", "chemistry-mix"), ("6-2", "chemistry-mix-paint-secondary-color"),
         ("6-3", "chemistry-mix-paint-tertiary-color"), ("7-1", "lifespan-longest-lived"),
         ("7-2", "lifespan-shortest-lived"), ("7-3", "lifespan-longest-lived-then-shortest-lived"),
         ("8-1", "identify-life-stages-1"), ("8-2", "identify-life-stages-2"),
         ("9-1", "inclined-plane-determine-angle"), ("9-2", "inclined-plane-friction-named-surfaces"),
         ("9-3", "inclined-plane-friction-unnamed-surfaces"), ("10-1", "mendelian-genetics-known-plant"),
         ("10-2", "mendelian-genetics-unknown-plant")]
SHORT = {"change-the-state-of-matter-of": "change state", "measure-melting-point-known-substance": "melting point, known",
         "measure-melting-point-unknown-substance": "melting point, unknown", "power-component": "power component",
         "power-component-renewable-vs-nonrenewable-energy": "renewable energy", "test-conductivity": "conductivity",
         "test-conductivity-of-unknown-substances": "conductivity, unknown", "find-living-thing": "find living thing",
         "find-non-living-thing": "find non-living", "chemistry-mix-paint-secondary-color": "paint, secondary",
         "chemistry-mix-paint-tertiary-color": "paint, tertiary", "lifespan-longest-lived": "longest lived",
         "lifespan-shortest-lived": "shortest lived", "lifespan-longest-lived-then-shortest-lived": "longest then shortest",
         "identify-life-stages-1": "life stages 1", "identify-life-stages-2": "life stages 2",
         "inclined-plane-determine-angle": "inclined plane, angle", "inclined-plane-friction-named-surfaces": "friction, named",
         "inclined-plane-friction-unnamed-surfaces": "friction, unnamed", "mendelian-genetics-known-plant": "genetics, known",
         "mendelian-genetics-unknown-plant": "genetics, unknown", "use-thermometer": "use thermometer",
         "chemistry-mix": "chemistry mix", "find-plant": "find plant", "find-animal": "find animal",
         "grow-plant": "grow plant", "grow-fruit": "grow fruit"}
# SwiftSage Table 1, per task id: (SwiftSage, Reflexion, ReAct, SayCan, DRRN)
REF = {"1-1": (97.04, 4.22, 3.52, 33.06, 3.52), "1-2": (87.04, 10.61, 13.70, 10.39, 3.52),
       "1-3": (72.78, 7.78, 7.78, 3.88, 0.0), "1-4": (100.0, 0.92, 9.88, 0.37, 0.0),
       "2-1": (99.17, 5.92, 7.19, 26.37, 6.56), "2-2": (88.17, 28.59, 6.10, 8.03, 5.50),
       "2-3": (95.73, 22.37, 22.37, 17.41, 6.0), "3-1": (88.67, 100.0, 56.0, 52.14, 12.0),
       "3-2": (55.33, 17.45, 54.33, 22.50, 9.0), "3-3": (71.90, 72.54, 76.19, 99.56, 9.05),
       "3-4": (77.86, 70.22, 88.81, 47.76, 9.52), "4-1": (100.0, 64.93, 26.67, 22.87, 15.0),
       "4-2": (100.0, 87.27, 80.0, 58.18, 45.0), "4-3": (91.67, 16.42, 53.33, 20.87, 21.67),
       "4-4": (100.0, 100.0, 27.50, 31.43, 19.17), "5-1": (74.59, 7.33, 9.06, 9.92, 8.0),
       "5-2": (93.93, 13.0, 18.57, 13.93, 14.29), "6-1": (49.40, 70.35, 51.04, 47.81, 15.77),
       "6-2": (100.0, 70.67, 58.89, 39.26, 26.67), "6-3": (91.48, 15.77, 40.74, 19.72, 10.37),
       "7-1": (95.0, 100.0, 60.0, 80.0, 50.0), "7-2": (85.0, 84.37, 67.50, 67.50, 50.0),
       "7-3": (93.33, 83.0, 50.0, 50.0, 33.33), "8-1": (89.0, 2.58, 27.67, 20.91, 21.0),
       "8-2": (68.50, 8.0, 8.0, 16.0, 8.0), "9-1": (75.0, 50.63, 40.50, 21.94, 10.0),
       "9-2": (70.0, 100.0, 44.0, 32.26, 10.0), "9-3": (60.0, 70.62, 41.0, 13.67, 10.0),
       "10-1": (92.30, 50.90, 25.70, 67.53, 16.80), "10-2": (77.60, 23.69, 16.80, 59.45, 17.0)}
OVERALL = {"SwiftSage": 84.68, "Reflexion": 45.34, "ReAct": 36.43, "SayCan": 33.82, "DRRN": 15.56}


def ss(x):
    n = len(x); m = sum(x) / n
    return m, (math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)) if n > 1 else 0.0), n


def fmt(v, d=1): return f"{v:,.{d}f}".replace("-", "−")


# ------------------------------------------------------------------ data
incumbent, dev = {0: "g000"}, {}
for line in open(RUNS / "scienceworld.log"):
    if m := re.match(r"\[seed\] train \S+ dev (\S+)", line):
        dev[0] = 100 * float(m.group(1))
    if m := re.match(r"\[g(\d+)\] incumbent (\S+) train \S+ dev (\S+)", line):
        incumbent[int(m.group(1))] = m.group(2); dev[int(m.group(1))] = 100 * float(m.group(3))
gens = sorted(dev)
versions = sorted(set(incumbent.values()), key=lambda v: min(g for g in gens if incumbent[g] == v))


def test300(v):
    f = RUN / "archive" / v / "eval_test" / "summary.json"
    return ss([100 * s for s in json.load(open(f))["scores"]]) if f.exists() else None


def full(v):
    """{task: [scores 0-100 by seed index]} for the tasks whose full test is done."""
    out = {}
    for _, name in TASKS:
        f = RUN / "fulltest" / v / name / "summary.json"
        if f.exists():
            s = json.load(open(f))
            out[name] = [100 * x for x in s["scores"]]
    return out


FULL = {v: full(v) for v in versions}
complete = {v for v in versions if len(FULL[v]) == len(TASKS)}
VAR = json.load(open(RUN / "fulltest" / "variations.json"))


def first10(scores, name):
    """Mean over the first 10 official test variations (SwiftSage's protocol), from the full test."""
    played, first = VAR[name]["played"], set(VAR[name]["official"][:10])
    sel = [s for s, var in zip(scores, played) if var in first]
    return sum(sel) / len(sel)


def macro(v, f=lambda s, name: sum(s) / len(s)):
    return sum(f(FULL[v][name], name) for _, name in TASKS) / len(TASKS) if v in complete else None


seed_v, best_v = "g000", incumbent[gens[-1]]

# ------------------------------------------------------------------ overall curve
X0, X1, Y0, Y1 = 50, 282, 40, 180
y = lambda v: Y1 - v / 100 * (Y1 - Y0)
xs = {g: X0 + (X1 - X0) * i / (len(gens) - 1) for i, g in enumerate(gens)}


def tick_x(out):
    for i, g in enumerate(gens):
        if i % 2 == 0 or g == gens[-1]:
            out.append(f'<text class="c-tick" x="{xs[g]:.1f}" y="200" text-anchor="middle">{"seed" if g == 0 else "g%d" % g}</text>')


def grid(out, small=False):
    for t in (0, 25, 50, 75, 100):
        out.append(f'<line class="c-grid" x1="{X0}" x2="{X1}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text class="c-tick" x="{X0-6}" y="{y(t)+4:.1f}" text-anchor="end">{t}</text>')


def point(out, x, v, cls, tip, r=4.5):
    out.append(f'<g class="c-pt"><circle class="c-hit" cx="{x:.1f}" cy="{y(v):.1f}" r="12"/>'
               f'<circle class="{cls}" cx="{x:.1f}" cy="{y(v):.1f}" r="{r}"/><title>{tip}</title></g>')


def refs(out, items):
    last = -99
    for v, lab in sorted(items, key=lambda t: y(t[0])):
        ly = y(v) - 4
        if ly - last < 13: ly = y(v) + 12
        last = ly
        out.append(f'<line class="c-ref" x1="{X0}" x2="{X1}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text class="c-ref-label" x="{X1-2}" y="{ly:.1f}" text-anchor="end">{lab} {v:.1f}</text>')


def overall_card(title, series, note):
    out = [f'<text class="c-title" x="12" y="22">{title}</text>',
           f'<text class="c-tick" x="{X1}" y="22" text-anchor="end">{note}</text>']
    grid(out)
    refs(out, [(OVERALL["SwiftSage"], "SwiftSage"), (OVERALL["Reflexion"], "Reflexion"), (OVERALL["ReAct"], "ReAct"),
               (OVERALL["DRRN"], "DRRN")])
    tick_x(out)
    for cls, vals, what in series:
        pts = [(g, vals[g]) for g in gens if vals.get(g) is not None]
        if len(pts) > 1:
            out.append(f'<polyline class="{"c-line" if cls == "c-dot" else "c-line c-line2"}" points="' +
                       " ".join(f"{xs[g]:.1f},{y(v):.1f}" for g, v in pts) + '"/>')
        for g, v in pts:
            point(out, xs[g], v, cls, f'{"seed program" if g == 0 else "generation %d" % g} ({incumbent[g]}): {v:.1f} {what}')
    return f'<div class="curve"><svg viewBox="0 0 300 210" role="img" aria-label="{title}">{"".join(out)}</svg></div>'


dev_s = {g: dev[g] for g in gens}
t300 = {g: (test300(incumbent[g]) or (None,))[0] for g in gens}
fullm = {g: macro(incumbent[g]) for g in gens}
cards = [overall_card("All 30 task types", [("c-dot", dev_s, "on 90 hidden dev seeds"),
                                            ("c-test", t300, "on 300 test seeds")], "● dev  ○ test (300 seeds)"),
         overall_card("Full official test", [("c-test", fullm, "macro mean over all 1,819 test variations")],
                      "○ macro mean, 1,819 episodes")]

# ------------------------------------------------------------------ per-task curves (full test)
seed_full = FULL[seed_v]
task_cards = []
for tid, name in TASKS:
    vals = {g: (sum(FULL[incumbent[g]][name]) / len(FULL[incumbent[g]][name]) if name in FULL[incumbent[g]] else None)
            for g in gens}
    base = vals.get(0)
    out = [f'<text class="c-title" x="12" y="22">{tid} {SHORT.get(name, name)}</text>']
    grid(out)
    refs(out, [(REF[tid][0], "SwiftSage")])
    tick_x(out)
    pts = [(g, v) for g, v in vals.items() if v is not None]
    if len(pts) > 1:
        out.append('<polyline class="c-line" points="' + " ".join(f"{xs[g]:.1f},{y(v):.1f}" for g, v in pts) + '"/>')
    for g, v in pts:
        m, sd, n = ss(FULL[incumbent[g]][name])
        bad = base is not None and g > 0 and v < base - 1e-9
        point(out, xs[g], v, "c-dot bad" if bad else "c-dot",
              f'{"seed program" if g == 0 else "generation %d" % g} ({incumbent[g]}): {m:.1f} ± {sd:.1f} over {n} test variations'
              + (" (below the seed program)" if bad else ""))
    if pts:
        g, v = pts[-1]
        out.append(f'<text class="c-val{" bad" if base is not None and v < base - 1e-9 else ""}" x="{xs[g]-8:.1f}" '
                   f'y="{y(v)+16 if v > 20 else y(v)-8:.1f}" text-anchor="end">{v:.0f}</text>')
    n = len(VAR[name]["official"])
    out.append(f'<text class="c-tick" x="{X1}" y="22" text-anchor="end">n={n}</text>')
    task_cards.append(f'<div class="curve"><svg viewBox="0 0 300 210" role="img" aria-label="ScienceWorld {tid} {name}: '
                      f'full-test score by generation">{"".join(out)}</svg></div>')

# ------------------------------------------------------------------ per-task table
def ranked(vals):
    """Per row, over the columns on the SwiftSage protocol (our first 10, SwiftSage, Reflexion, ReAct, DRRN):
    best in bold, second best underlined; ties (at the shown precision) share the mark."""
    shown = {k: (None if v is None else round(v, 1)) for k, v in vals.items()}
    top = sorted({v for v in shown.values() if v is not None}, reverse=True)
    def mark(k, txt):
        v = shown[k]
        if v is None: return txt
        if v == top[0]: return f"<strong>{txt}</strong>"
        if len(top) > 1 and v == top[1]: return f'<span class="second">{txt}</span>'
        return txt
    return mark


rows = []
for tid, name in TASKS:
    n = len(VAR[name]["official"])
    s0 = ss(seed_full[name]) if name in seed_full else None
    s1 = ss(FULL[best_v][name]) if name in FULL[best_v] else None
    f10 = first10(FULL[best_v][name], name) if name in FULL[best_v] else None
    bad = ' class="bad"' if s0 and s1 and s1[0] < s0[0] else ""
    cell = lambda s: f"{fmt(s[0])} ± {fmt(s[1])}" if s else "running"
    sw, rf, ra, sc, dr = REF[tid]
    mk = ranked({"ours": None if f10 is None else round(f10, 1), "sw": sw, "rf": rf, "ra": ra, "dr": dr})
    rows.append(f'<tr><td>{tid}</td><td>{SHORT.get(name, name)}</td><td class="num">{n}</td><td class="num">{cell(s0)}</td>'
                f'<td class="num"><span{bad}>{cell(s1)}</span></td>'
                f'<td class="num">{mk("ours", fmt(f10)) if f10 is not None else "running"}</td><td class="num">{mk("sw", fmt(sw))}</td>'
                f'<td class="num">{mk("rf", fmt(rf))}</td><td class="num">{mk("ra", fmt(ra))}</td><td class="num">{mk("dr", fmt(dr))}</td></tr>')


def macro_cell(v, f=None):
    if v not in complete:
        return "running"
    means = [(f or (lambda s, nm: sum(s) / len(s)))(FULL[v][nm], nm) for _, nm in TASKS]
    m, sd, _ = ss(means)
    return f"{fmt(m)} ± {fmt(sd)}"


f10m = macro(best_v, first10) if best_v in complete else None
mk = ranked({"ours": None if f10m is None else round(f10m, 1), "sw": OVERALL["SwiftSage"], "rf": OVERALL["Reflexion"],
             "ra": OVERALL["ReAct"], "dr": OVERALL["DRRN"]})
rows.append(f'<tr class="best"><td></td><td><strong>Mean of 30 task types</strong></td><td class="num">1,819</td>'
            f'<td class="num">{macro_cell(seed_v)}</td><td class="num">{macro_cell(best_v)}</td>'
            f'<td class="num">{mk("ours", macro_cell(best_v, first10))}</td><td class="num">{mk("sw", OVERALL["SwiftSage"])}</td>'
            f'<td class="num">{mk("rf", OVERALL["Reflexion"])}</td><td class="num">{mk("ra", OVERALL["ReAct"])}</td><td class="num">{mk("dr", OVERALL["DRRN"])}</td></tr>')

row1 = (f'<tr><td>Science (text)</td><td>ScienceWorld, 30 task types, one program</td><td>all 1,819 official test variations</td>'
        f'<td class="num">{macro_cell(seed_v)}</td><td class="num"><strong>{macro_cell(best_v)}</strong></td>'
        f'<td class="num">SwiftSage (GPT-4) {OVERALL["SwiftSage"]}*</td></tr>')
(HERE / "_includes/row-scienceworld.html").write_text(row1 + "\n")
(HERE / "_includes/curves-scienceworld.html").write_text('<div class="curves">\n' + "\n".join(cards) + "\n</div>\n")
(HERE / "_includes/curves-scienceworld-tasks.html").write_text('<div class="curves curves-5">\n' + "\n".join(task_cards) + "\n</div>\n")
(HERE / "_includes/table-scienceworld.html").write_text("\n".join(rows) + "\n")
summary = {"best": best_v, "dev": {g: round(dev[g], 1) for g in gens}, "test300": {g: t300[g] and round(t300[g], 1) for g in gens},
           "full_macro": {v: macro(v) and round(macro(v), 2) for v in versions},
           "first10_best": macro(best_v, first10), "complete": sorted(complete), "seed_test300": test300(seed_v),
           "best_test300": test300(best_v)}
print(json.dumps(summary, indent=1, default=str))
