"""Write _includes/curves-hunl.html: HUNL cards in the same SVG style as curves-poker.html.

Numbers come from the DRSI-Anything runs (path below). Usage: python3 scripts/make_hunl_curves.py [RUNS_DIR]
"""
import json, math, sys
from pathlib import Path

RUNS = Path(sys.argv[1] if len(sys.argv) > 1 else "../DRSI-Anything/runs")
X0, X1, Y0, Y1 = 50, 282, 40, 180  # plot box in the 300x210 viewBox


def fmt(v):
    return f"{v:,.0f}".replace("-", "−")


def frame(title, lo, hi, ticks):
    y = lambda v: Y1 - (v - lo) / (hi - lo) * (Y1 - Y0)
    out = [f'<text class="c-title" x="12" y="22">{title}</text>']
    for t in ticks:
        cls = "c-ref" if t == 0 else "c-grid"
        out.append(f'<line class="{cls}" x1="{X0}" x2="{X1}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text class="c-tick" x="{X0-6}" y="{y(t)+4:.1f}" text-anchor="end">{fmt(t)}</text>')
    return y, out


def pt(x, y, tip, r=4.5):
    return (f'<g class="c-pt"><circle class="c-hit" cx="{x:.1f}" cy="{y:.1f}" r="12"/>'
            f'<circle class="c-dot" cx="{x:.1f}" cy="{y:.1f}" r="{r}"/><title>{tip}</title></g>')


def card(label, body):
    return f'<div class="curve"><svg viewBox="0 0 300 210" role="img" aria-label="{label}">{"".join(body)}</svg></div>'


def bars(title, label, lo, hi, ticks, groups):
    """groups: [(name, mean, std, seeds, css)]; a later group lower than the first is drawn red (a regression)."""
    base_mean = groups[0][1]
    y, out = frame(title, lo, hi, ticks)
    w = 52
    for i, (name, mean, se, seeds, cls) in enumerate(groups):
        bad = i > 0 and mean < base_mean
        if bad: cls = "c-bar-bad"
        cx = X0 + (X1 - X0) * (i + 0.5) / len(groups)
        top, base = sorted([y(mean), y(0)])
        out.append(f'<rect class="{cls}" x="{cx-w/2:.1f}" y="{top:.1f}" width="{w}" height="{max(base-top,1):.1f}" rx="3"><title>{name}: {fmt(mean)} ± {fmt(se)} (std over seeds)</title></rect>')
        if se:
            out.append(f'<line class="c-err" x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(mean-se):.1f}" y2="{y(mean+se):.1f}"/>'
                       f'<line class="c-err" x1="{cx-6:.1f}" x2="{cx+6:.1f}" y1="{y(mean-se):.1f}" y2="{y(mean-se):.1f}"/>'
                       f'<line class="c-err" x1="{cx-6:.1f}" x2="{cx+6:.1f}" y1="{y(mean+se):.1f}" y2="{y(mean+se):.1f}"/>')
        for k, v in enumerate(seeds or []):
            out.append(pt(cx - w/2 - 9 - (k % 2) * 0, y(v), f"{name}, seed {2000+k}: {fmt(v)}", r=2.5))
        ly = (y(mean) - 8) if mean >= 0 else (y(mean) + 15)
        if se: ly = (y(mean + se) - 6) if mean >= 0 else (y(mean - se) + 15)
        out.append(f'<text class="c-val{" bad" if bad else ""}" x="{cx:.1f}" y="{ly:.1f}" text-anchor="middle">{fmt(mean)} ± {fmt(se)}</text>')
        out.append(f'<text class="c-tick" x="{cx:.1f}" y="200" text-anchor="middle">{name}</text>')
    return card(label, out)


# 1. dev score by generation (the loop's gate)
hist = [json.loads(l) for l in open(RUNS / "poker_hunl/history.jsonl")]
# fall back to the log lines for the incumbent's dev score per generation
_ev = lambda g: json.load(open(RUNS / f"poker_hunl/archive/{g}/eval_dev/summary.json"))
dev = {0: _ev("g000")["mean"]}
dev_std = {0: _ev("g000")["std"] * math.sqrt(32 / 31)}
for line in open(RUNS / "poker_hunl.log"):
    if "incumbent" in line and "dev" in line:
        g = int(line.split("]")[0].strip("[g"))
        dev[g] = float(line.split("dev")[1].split()[0])
        dev_std[g] = _ev(line.split("incumbent")[1].split()[0])["std"] * math.sqrt(32 / 31)
gens = sorted(dev)
lo, hi = -5000, 45000
y, out = frame("HUNL vs rule bots · mbb/hand ↑", lo, hi, [0, 20000, 40000])
xs = {g: X0 + (X1 - X0) * i / (len(gens) - 1) for i, g in enumerate(gens)}
for g in gens:
    out.append(f'<text class="c-tick" x="{xs[g]:.1f}" y="200" text-anchor="middle">{"seed" if g == 0 else "g%d" % g}</text>')
out.append('<polyline class="c-line" points="' + " ".join(f"{xs[g]:.1f},{y(dev[g]):.1f}" for g in gens) + '"/>')
for g in gens:
    out.append(pt(xs[g], y(dev[g]), f"{'seed program' if g == 0 else 'generation %d' % g}: {fmt(dev[g])} ± {fmt(dev_std[g])} on hidden dev (32 seeds)"))
out.append(f'<text class="c-val" x="{X1-10}" y="{y(dev[gens[-1]])-10:.1f}" text-anchor="end">{fmt(dev[gens[-1]])} ± {fmt(dev_std[gens[-1]])}</text>')
cards = [card("HUNL vs rule bots: dev score by generation", out)]

# 2. test vs rule bots + past champions
t = json.load(open(RUNS / "poker_hunl/test.json"))
samp = lambda s, n: s * math.sqrt(n / (n - 1))  # summaries store the population std; report the sample std
cards.append(bars("vs rule bots · test", "HUNL vs rule bots and past champions on 64 test seeds", -20000, 35000, [-20000, 0, 20000],
                  [("seed", t["g000"]["mean"], samp(t["g000"]["std"], 64), None, "c-bar-seed"),
                   ("champion", t["g001c0"]["mean"], samp(t["g001c0"]["std"], 64), None, "c-bar")]))

# 3. vs DecisionHoldem, 8 seeds
d0 = json.load(open(RUNS / "_dh_eval/g000/summary.json"))
d1 = json.load(open(RUNS / "_dh_eval/g001c0/summary.json"))
cards.append(bars("vs DecisionHoldem", "HUNL vs DecisionHoldem on 8 unseen seeds", -20000, 8000, [-15000, -10000, -5000, 0, 5000],
                  [("seed", d0["mean"], samp(d0["std"], 8), d0["scores"], "c-bar-seed"),
                   ("champion", d1["mean"], samp(d1["std"], 8), d1["scores"], "c-bar")]))

Path(__file__).resolve().parent.parent.joinpath("_includes/curves-hunl.html").write_text(
    '<div class="curves">\n' + "\n".join(cards) + "\n</div>\n")
print("ok", {g: round(v) for g, v in dev.items()})
