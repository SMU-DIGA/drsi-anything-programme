# NS-RSI-Anything

**Neuro-Symbolic Recursive Self-Improvement across General Domains**: LLMs (neural) write and repeatedly improve programs (symbolic) for games, embodied robotics and computer use.

**[Project page & progress log](https://smu-diga.github.io/ns-rsi-anything-programme/)** · [中文](README.zh-CN.md) · [Design](https://smu-diga.github.io/ns-rsi-anything-programme/#design) · [Environments](https://smu-diga.github.io/ns-rsi-anything-programme/#environments) · [Roadmap](https://smu-diga.github.io/ns-rsi-anything-programme/#roadmap)

An LLM writes a program that solves a task (a game bot, a robot controller, a desktop agent). Then LLMs
improve that program over many generations, using only interaction feedback from the environment. The
object being improved is **software**, not neural-network weights: a policy, its state detectors and
skills, and a notes file that serves as the program's memory.

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
[roadmap](https://smu-diga.github.io/ns-rsi-anything-programme/#roadmap) for what remains. This repository hosts the programme's documents and results;
the implementation is not public.

| Component | Status |
|---|---|
| RSI loop, archive, promotion gate, resume, env-step ledger | Done |
| Isolated evaluator (policy in a separate process, no access to reward or seed) | Done |
| Improvers: Codex CLI, Claude Code, OpenAI-compatible chat API (DeepSeek) | Done |
| Games: Atari RAM: Breakout 864 on all test seeds; Pong 21, Ms. Pac-Man 17,207, Montezuma 9,700 on dev | Running |
| Games: VizDoom | Done |
| Games: poker (Leduc variants by NashConv; heads-up no-limit hold'em, duplicate) | Running |
| Embodied robotics: MuJoCo locomotion, MetaWorld, ManiSkill3 | Done |
| Embodied robotics: LIBERO (Spatial state 99.0% test; LIBERO-10 state 99.0% test; Spatial vision 95.0% dev) | Running |
| Embodied robotics: SimplerEnv, RoboTwin 2.0 | Planned |
| Computer use: OSWorld (pure code vs code + typed 2B decision function) | Running |

Status: Done (integrated and tested) · Running (experiment in progress) · In progress (being built) · Planned (not started).

Headline results (programs written and refined by LLM improvers; no gradient training, no demonstrations):

- **Breakout (RAM):** 864, the maximum, on all 64 unseen test seeds after 4 generations (seed program: 2.2).
- **LIBERO (state):** 99.0% on 400 test episodes for both LIBERO-Spatial and LIBERO-10, each after 1 generation.
- **Montezuma's Revenge / Ms. Pac-Man / Pong (RAM, hidden dev):** 9,700 / 17,207 / 21 after 1 generation.


## Progress log

The [project page](https://smu-diga.github.io/ns-rsi-anything-programme/) is built by GitHub Pages from the
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
