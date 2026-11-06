# DRSI-Anything

**Delegative Recursive Self-Improvement across General Domains**: LLMs do not act themselves; they delegate the acting to programs they write and repeatedly improve, for games, embodied robotics and computer use. Neuro-symbolic programs (code, optionally calling smaller models) are our main form of delegation. The programme was earlier called NS-RSI-Anything.

**[Project page & progress log](https://smu-diga.github.io/drsi-anything-programme/)** · [中文](README.zh-CN.md) · [Design](https://smu-diga.github.io/drsi-anything-programme/#design) · [Environments](https://smu-diga.github.io/drsi-anything-programme/#environments) · [Roadmap](https://smu-diga.github.io/drsi-anything-programme/#roadmap)

An LLM writes a program that solves a task (a game bot, a robot controller, a desktop agent). Then LLMs
improve that program over many generations, using only interaction feedback from the environment. The
object being improved is a **delegate**. Today it is mostly software (a policy, its state detectors and skills, and a
notes file that serves as the program's memory), and a program may hand part of a decision to an LLM through a typed
decision function. Following [Weight-Space Programming](https://rikiyat.github.io/blog/weight-space-programming/), where an LLM reads and writes a network's weights
directly without an optimizer, the weights of that delegate LLM can also be edited directly by an improver. The results
reported so far use code only (plus a frozen small model in computer use); direct weight editing is planned and has not been run.

```
incumbent program ──► K improvers edit it in parallel (Codex CLI · Claude Code · chat APIs such as DeepSeek)
                        │ each one tests its own edits on the train seeds
                        ▼
                independent re-evaluation on train ──► best candidate vs. incumbent on hidden dev seeds
                        │ paired bootstrap promotion gate
                        ▼
                new incumbent ──► optional simplification pass (kept only if dev does not drop) ──► next generation
```

The project combines two lines of work:

- **[RSI-Anything](https://github.com/Gen-Verse/RSI-Anything)**: a cross-domain recursive self-improvement
  loop of propose, predict, select, evaluate and keep, with frozen evaluation protocols and promotion gates.
- **[Learning Beyond Gradients](https://trinkle23897.github.io/learning-beyond-gradients/)**
  ("Heuristic Learning"): a coding agent iteratively edits hand-written programs and reaches competitive
  scores on Atari, MuJoCo and VizDoom without gradient updates.

## Status

Work in progress. The core loop and the EnvPool task families work end to end. See the
[roadmap](https://smu-diga.github.io/drsi-anything-programme/#roadmap) for what remains. This repository hosts the programme's documents and results;
the implementation is not public.

| Component | Status |
|---|---|
| RSI loop, archive, promotion gate, resume, env-step ledger | Done |
| Isolated evaluator (policy in a separate process, no access to reward or seed) | Done |
| Improvers: Codex CLI, Claude Code, OpenAI-compatible chat API (DeepSeek) | Done |
| Games: Atari-5 from pixels, sticky actions (above human on 4 of 5; Q*bert 52,418 test) | Running |
| Games: VizDoom | Done |

Status: Done (integrated and tested) · Running (experiment in progress) · In progress (being built) · Planned (not started).

Headline results (programs written and refined by LLM improvers; no gradient training, no demonstrations):

- **Atari-5 (pixels only, sticky actions):** above the human score on 4 of 5 games on 64 unseen test seeds; Q*bert 183 → 52,418.
- **ScienceWorld:** one program for all 30 task types, 2.5 → 85.0 on all 1,819 official test variations after four rounds and one merged specialist (86.8 on SwiftSage's first 10 variations per type, above SwiftSage with GPT-4: 84.68).


## Progress log

The [project page](https://smu-diga.github.io/drsi-anything-programme/) is built by GitHub Pages from the
repository root. To add an update, create `_posts/YYYY-MM-DD-short-title.md`:

```markdown
---
title: One-line headline
summary: One or two sentences shown in the progress list.
tags: [games, robotics]
---

Body in Markdown: what was done, results tables, next steps.
```

## License

MIT
