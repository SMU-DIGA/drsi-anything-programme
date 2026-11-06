"""Write _includes/curves-atari5.html and _includes/table-atari5.html (Atari-5, pixels only, sticky actions).

Ours: DRSI-Anything runs (path below). RL numbers: Table A2 of 'Beyond The Rainbow' (Clark et al. 2024, arXiv 2411.03820):
maximum training score, 100-episode average, mean of 3 seeds, 200M frames. Random/Human from the same table.
Usage: python3 scripts/make_atari5_pixel.py [RUNS_DIR]
"""
import json, math, re, sys
from pathlib import Path

RUNS = Path(sys.argv[1] if len(sys.argv) > 1 else "../DRSI-Anything/runs")
HERE = Path(__file__).resolve().parent.parent
# game: (run, display, random, human, Rainbow Dopamine (sticky), Rainbow full, BTR)
# Agent57: Badia et al. 2020 (arXiv 2003.13350), appendix per-game table, mean +- std over seeds.
# No sticky actions, 30 no-ops, grayscale, 30 min episodes; up to 78 B frames (51 games above human within 5 B).
# Muesli paper (Hessel et al. 2021, arXiv 2104.06159), Table 11: sticky actions p=0.25, 0 no-ops, 200M frames,
# mean of the last 200 episodes, +- standard error over 2 seeds. (MuZero, Muesli)
MUESLI = {"Battle Zone": ((320641, 141924), (414107, 13422)), "Name This Game": ((108133, 6935), (105043, 732)),
          "Phoenix": ((748424, 67304), (805305, 26719)), "Q*bert": ((85926, 8980), (157353, 6593)),
          "Double Dunk": ((24, 0), (-3, 2))}
AGENT57 = {"Battle Zone": (934135, 38916), "Name This Game": (54387, 6149), "Phoenix": (908264, 28979), "Q*bert": (580328, 151252)}
GAMES = [
    ("battle_zone_image_sticky", "Battle Zone", 2360, 37188, 40895, 62010, 168340),
    ("double_dunk_image_sticky", "Double Dunk", -18.6, -16.4, 22, 0, 23),
    ("name_this_game_image_sticky", "Name This Game", 2292, 8049, 9229, 13136, 27917),
    ("phoenix_image_sticky", "Phoenix", 761, 7243, 8605, 108529, 427481),
    ("qbert_image_sticky", "Q*bert", 164, 13455, 18503, 33818, 42927),
]
X0, X1, Y0, Y1 = 50, 282, 40, 180


def ss(x):
    n = len(x); m = sum(x) / n
    return m, math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)), n


def ev(run, g, sp):
    f = RUNS / run / "archive" / g / f"eval_{sp}" / "summary.json"
    return ss(json.load(open(f))["scores"]) if f.exists() else None


DEC = {"Double Dunk": 2}  # score differences, not thousands of points


def fmt(v, d=0): return f"{v:,.{d}f}".replace("-", "−")
def short(v): return f"{v/1000:g}k" if abs(v) >= 1000 else f"{v:g}"


def curve(run, name, human, rainbow, muesli, test):
    """Dev score by generation on a log axis, with the sticky-action references and the final test score."""
    dev = {0: ev(run, "g000", "dev")[0]}
    for line in open(RUNS / f"{run}.log"):
        m = re.match(r"\[g(\d+)\] incumbent (\S+) train \S+ dev (\S+)", line)
        if m: dev[int(m.group(1))] = float(m.group(3))
    gens = sorted(dev)
    vals = list(dev.values()) + [human, rainbow, muesli, test]
    linear = min(vals) <= 0  # Double Dunk has negative scores: a log axis cannot draw them
    if linear:
        lo, hi = -25, 25
        y = lambda v: Y1 - (v - lo) / (hi - lo) * (Y1 - Y0)
    else:
        lo, hi = math.floor(math.log10(min(vals))), math.ceil(math.log10(max(vals)))
        y = lambda v: Y1 - (math.log10(max(v, 1)) - lo) / (hi - lo) * (Y1 - Y0)
    d = 1 if linear else 0
    F = lambda v: fmt(v, 1 if linear and abs(v) < 100 else 0)
    name_ = {2: "100", 3: "1k", 4: "10k", 5: "100k", 6: "1M"}
    out = [f'<text class="c-title" x="12" y="22">{name}</text>',
           f'<text class="c-tick" x="{X1}" y="22" text-anchor="end">● dev  ○ test{"" if linear else " · log"}</text>']
    if linear:
        for t in (-20, -10, 0, 10, 20):
            out.append(f'<line class="{"c-ref" if t == 0 else "c-grid"}" x1="{X0}" x2="{X1}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                       f'<text class="c-tick" x="{X0-6}" y="{y(t)+4:.1f}" text-anchor="end">{fmt(t)}</text>')
    for e in ([] if linear else range(lo, hi + 1)):
        out.append(f'<line class="c-grid" x1="{X0}" x2="{X1}" y1="{y(10**e):.1f}" y2="{y(10**e):.1f}"/>'
                   f'<text class="c-tick" x="{X0-6}" y="{y(10**e)+4:.1f}" text-anchor="end">{name_.get(e, "10^%d" % e)}</text>')
    n = len(gens) - 1
    xs = {g: X0 + (X1 - X0) * i / n for i, g in enumerate(gens)}
    for i, g in enumerate(gens):
        if i % max(1, n // 5) == 0 or g == gens[-1]:
            out.append(f'<text class="c-tick" x="{xs[g]:.1f}" y="200" text-anchor="middle">{"seed" if g == 0 else "g%d" % g}</text>')
    # reference lines; a label goes above its line unless that would touch the previous (lower-pixel) label
    last = -99
    for v, lab in sorted([(human, "human"), (rainbow, "Rainbow"), (muesli, "Muesli")], key=lambda t: y(t[0])):
        ly = y(v) - 4
        if ly - last < 13: ly = y(v) + 12
        last = ly
        out.append(f'<line class="c-ref" x1="{X0}" x2="{X1}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text class="c-ref-label" x="{X0+4}" y="{ly:.1f}">{lab} {F(v)}</text>')
    out.append('<polyline class="c-line" points="' + " ".join(f"{xs[g]:.1f},{y(dev[g]):.1f}" for g in gens) + '"/>')
    for g in gens:
        tip = ("seed program" if g == 0 else f"generation {g}") + f": {F(dev[g])} on hidden dev"
        out.append(f'<g class="c-pt"><circle class="c-hit" cx="{xs[g]:.1f}" cy="{y(dev[g]):.1f}" r="12"/>'
                   f'<circle class="c-dot" cx="{xs[g]:.1f}" cy="{y(dev[g]):.1f}" r="4.5"/><title>{tip}</title></g>')
    out.append(f'<g class="c-pt"><circle class="c-hit" cx="{X1}" cy="{y(test):.1f}" r="12"/><circle class="c-test" cx="{X1}" cy="{y(test):.1f}" r="6"/>'
               f'<title>final program: {F(test)} on 64 test seeds</title></g>')
    out.append(f'<text class="c-val" x="{X1-10}" y="{y(test)+16:.1f}" text-anchor="end">test {fmt(test, 2) if linear else F(test)}</text>')
    return f'<div class="curve"><svg viewBox="0 0 300 210" role="img" aria-label="{name}: dev score by generation, log scale">{"".join(out)}</svg></div>', None


def champion(run):
    best = None
    for line in open(RUNS / f"{run}.log"):
        m = re.match(r"\[g\d+\] incumbent (\S+) train \S+ dev (\S+) env_steps (\d+)", line)
        if m: best = (m.group(1), int(m.group(3)))
    return best


cards, rows = [], []
for run, name, rnd, human, rdop, rfull, btr in GAMES:
    cg, steps = champion(run)
    t0, t1 = ev(run, "g000", "test"), ev(run, cg, "test")
    svg, _ = curve(run, name, human, rdop, MUESLI[name][1][0], t1[0]); cards.append(svg)
    dd = DEC.get(name, 0)
    cell = lambda t: f'{fmt(t[0], dd)} ± {fmt(t[1], dd)}'
    bad = ' class="bad"' if t1[0] < t0[0] else ""
    mz, mu = MUESLI[name]
    # per row, among the agents (human is a reference, not ranked): best in bold, second best underlined
    agents = {"seed": t0[0], "ours": t1[0], "rainbow": rdop, "btr": btr, "muzero": mz[0], "muesli": mu[0]}
    top = sorted(set(agents.values()), reverse=True)
    mark = lambda k, txt: (f"<strong>{txt}</strong>" if agents[k] == top[0] else
                           f'<span class="second">{txt}</span>' if len(top) > 1 and agents[k] == top[1] else txt)
    rows.append(f'<tr><td>{name}</td><td class="num">{mark("seed", cell(t0))}</td><td class="num">{mark("ours", f"<span{bad}>{cell(t1)}</span>")}</td>'
                f'<td class="num">{fmt(human, 1 if abs(human) < 100 else 0)}</td><td class="num">{mark("rainbow", fmt(rdop))}</td><td class="num">{mark("btr", fmt(btr))}</td>'
                f'<td class="num">{mark("muzero", f"{fmt(mz[0])} ± {fmt(mz[1])}")}</td><td class="num">{mark("muesli", f"{fmt(mu[0])} ± {fmt(mu[1])}")}</td>'
                f'<td class="num">{steps/1e6:.0f} M</td></tr>')
    print(name, cg, cell(t0), cell(t1), f"{steps/1e6:.1f}M steps")

(HERE / "_includes/curves-atari5.html").write_text('<div class="curves curves-5">\n' + "\n".join(cards) + "\n</div>\n")
(HERE / "_includes/table-atari5.html").write_text("\n".join(rows) + "\n")
