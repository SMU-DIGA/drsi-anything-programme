"""Write _includes/programs-featured.html and copy the sources to assets/programs/: the merged Atari-5 program
(one program for five games, screen only) and the ScienceWorld headline program (round-4 champion plus the
electricity specialist, 86.8 on the SwiftSage protocol).

Usage: python3 scripts/make_programs.py [RUNS_DIR]
"""
import html
import shutil
import sys
from pathlib import Path

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

RUNS = Path(sys.argv[1] if len(sys.argv) > 1 else "../DRSI-Anything/runs")
HERE = Path(__file__).resolve().parent.parent

PROGRAMS = [
    {
        "domain": ("atari", "Atari games",
                   "One program for the five Atari-5 games, from the screen alone."),
        "id": "atari5-merged",
        "title": "Atari-5 · one program, screen only",
        "dir": RUNS / "atari5_merge" / "program_pixels",
        "files": ["policy.py", "battle_zone/policy.py", "double_dunk/policy.py", "name_this_game/policy.py",
                  "phoenix/policy.py", "qbert/policy.py"],
        "meta": "the five per-game champions (Codex 14 promotions, DeepSeek 3) merged into one program · not told the "
                "game, no <code>info</code>, full 18-action set · test: Battle Zone 36,859, Double Dunk 0.8, Name This "
                "Game 20,171, Phoenix 65,076, Q*bert 52,136 (64 seeds each)",
        "learned": [
            "Recognises the game from the first non-blank frame: the screen, averaged into 21 × 16 colour cells, is "
            "matched to five reference screens taken from train seeds; a black opening frame is waited out with NOOP.",
            "Then runs that game's program unchanged and maps its minimal action set to ALE's full 18 actions.",
            "<strong>Battle Zone</strong> (30 lines): finds enemy tanks by colour in the landscape band, turns until "
            "the gun points at them and fires continuously; searches by turning when none is visible.",
            "<strong>Double Dunk</strong> (67 lines): reads possession and the score from a few pixels, runs a fixed "
            "opening attack, recognises an early steal and restarts the attack when it falls behind.",
            "<strong>Name This Game</strong> (95 lines): tracks the boat, the diver and the shark by exact colours, "
            "measures the shark's speed and intercepts it before it reaches the diver, and cuts tentacles first.",
            "<strong>Phoenix</strong> (171 lines): sweeps and fires, dodges falling shots and diving birds, raises "
            "the shield when a collision is predicted and aims at the mothership's centre.",
            "<strong>Q*bert</strong> (220 lines): maps the pyramid's cubes, plans by breadth-first search to the "
            "nearest unfinished cube while avoiding the purple enemies and dead ends, and uses the escape disc.",
            "Not yet distilled: the five programs sit side by side; shared skills (reading objects by colour, "
            "tracking) are written five times.",
        ],
        "excerpt": ("policy.py", 1, 59, "The whole merged program: game recognition from the screen, then the "
                                       "unchanged per-game programs."),
    },
    {
        "domain": ("science", "Science experiments (text)",
                   "One program for all 30 ScienceWorld task types."),
        "id": "scienceworld",
        "title": "ScienceWorld · all 30 task types",
        "dir": RUNS / "scienceworld_spec_elec" / "archive" / "g001c0" / "program",
        "files": ["policy.py"],
        "meta": "round-4 champion g001c1 (Claude Sonnet) plus the electricity specialist (Claude Sonnet) · 85.0 on all "
                "1,819 test variations, 86.8 on SwiftSage's protocol (SwiftSage with GPT-4: 84.68) · no model at "
                "run time",
        "learned": [
            "A text agent written as code: every step it reads the task, the room description, the inventory and "
            "the commands ScienceWorld accepts, and returns one command.",
            "Shared skills used by every task type: teleporting, keeping a map of every room it has seen, searching "
            "the whole world for an exact object, opening containers, filling water, focusing only on the exact "
            "target (a wrong focus ends the task at once), and blacklisting commands the game rejects.",
            "One handler per family of task types, each an experiment rather than a script: heat or cool a "
            "substance and watch its state change, measure a temperature, build a circuit, test conductivity, "
            "time objects sliding down inclined planes, mix paints and chemicals, grow plants and pollinate them.",
            "Answers from written-in general knowledge where ScienceWorld asks for it and an experiment is "
            "impractical: animal lifespans and Mendel's dominant pea traits.",
            "Rounds 3 and 4 removed train-only special cases: a default that only worked on train counts as one; "
            "it searches the world for the exact target, never substitutes another object, and escalates to "
            "another means (another heat source) when one has no effect.",
            "The electricity specialist found why power-component tasks failed: the circuit skill only lit bulbs. "
            "It now reads any target from the task text and searches the world for it (test 8.2 → 46.4).",
        ],
        "excerpt": ("policy.py", 768, 846, "The circuit skill after the electricity specialist: the target comes from "
                                           "the task text, and the world is searched before anything is built."),
    },
]

FORMAT = dict(linenos="table", cssclass="hl")


def code(text, start=1):
    # raw: Python source may contain "{{" or "{%", which Jekyll would read as Liquid
    return "{% raw %}" + highlight(text, PythonLexer(), HtmlFormatter(linenostart=start, **FORMAT)) + "{% endraw %}"


out, done_domains = [], set()
assets = HERE / "assets" / "programs"
for p in PROGRAMS:
    key, name, intro = p["domain"]
    if key not in done_domains:
        done_domains.add(key)
        out.append(f'<h2 class="prog-domain" id="{key}">{name}</h2>\n<p class="prog-domain-intro">{intro}</p>')
    total = sum(len((p["dir"] / f).read_text().splitlines()) for f in p["files"])
    out.append(f'<article class="prog" id="{p["id"]}">')
    out.append(f'<div class="prog-head"><h3>{p["title"]}</h3><p class="prog-meta">{p["meta"]} · {total:,} lines of '
               f'Python in {len(p["files"])} file{"s" if len(p["files"]) > 1 else ""}</p></div>')
    out.append('<ul class="prog-learned">' + "".join(f"<li>{x}</li>" for x in p["learned"]) + "</ul>")
    f, a, b, label = p["excerpt"]
    lines = (p["dir"] / f).read_text().splitlines()
    out.append(f'<p class="prog-excerpt-label">Key excerpt · <code>{f}</code> lines {a}–{b}. {label}</p>')
    out.append(code("\n".join(lines[a - 1:b]) + "\n", a))
    for f in p["files"]:
        src = (p["dir"] / f).read_text()
        dst = assets / p["id"] / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p["dir"] / f, dst)
        out.append(f'<details class="prog-file"><summary><code>{html.escape(f)}</code> · {len(src.splitlines())} lines '
                   f'· full source</summary><p class="prog-raw"><a href="{{{{ \'/assets/programs/{p["id"]}/{f}\' | '
                   f'relative_url }}}}">Open raw file</a></p>{code(src)}</details>')
    out.append("</article>")
(HERE / "_includes" / "programs-featured.html").write_text("\n".join(out) + "\n")
print("wrote", len(PROGRAMS), "programs")
