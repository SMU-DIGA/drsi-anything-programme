# NS-RSI-Anything

**Recursive self-improvement of LLM-written programs: games, embodied robotics and computer use.**

**[Project page & progress log](https://smu-diga.github.io/ns-rsi-anything-programme/)** · [中文](README.zh-CN.md) · [Design](design.md) · [Environments](environments.md) · [Roadmap](roadmap.md)

An LLM writes a program that solves a task (a game bot, a robot controller, a desktop agent). Then LLMs
improve that program over many generations, using only interaction feedback from the environment. The
object being improved is **software**, not neural-network weights: a policy, its state detectors and
skills, and a notes file that serves as the program's memory.

```
incumbent program ──► K improvers edit it in parallel (Codex CLI · Claude Code · chat APIs such as DeepSeek)
                        │ each one tests its own edits on the train seeds (./eval.sh)
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
[roadmap](roadmap.md) for what remains. This repository hosts the programme's documents and results;
the implementation is not public.

| Component | State |
|---|---|
| RSI loop, archive, promotion gate, resume, env-step ledger | done |
| Isolated evaluator (policy in a separate process, no access to reward or seed) | done, tested |
| Improvers: Codex CLI, Claude Code, OpenAI-compatible chat API (DeepSeek) | done; API path verified end to end |
| Games: Atari (RAM / image), VizDoom (EnvPool) | done |
| Robotics: MuJoCo locomotion, MetaWorld (EnvPool) | done |
| Robotics: LIBERO, ManiSkill3, SimplerEnv, RoboTwin 2.0 | simulators verified; adapters in progress |
| Computer use: OSWorld | planned |

First smoke test (Breakout, RAM observations, one generation, one DeepSeek improver): hidden dev mean
went from 2.1 (random seed program) to 13.0. Along the way the program wrote down facts it discovered,
such as "the ball must be served with FIRE" and which RAM bytes hold the paddle and ball positions.


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
