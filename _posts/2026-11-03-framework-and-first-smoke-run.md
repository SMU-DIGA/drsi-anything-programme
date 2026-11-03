---
title: Framework built; first self-improvement run on Breakout
summary: The RSI loop, isolated evaluator and three kinds of improvers are working. In one generation, a DeepSeek improver raised Breakout (RAM) from 2.1 to 13.0 on hidden dev seeds.
tags: [framework, games]
---

## What was built

- **RSI loop.** Each generation copies the incumbent program to K workspaces. Improvers edit it in
  parallel, each candidate is re-evaluated independently, and the best one must beat the incumbent on
  hidden dev seeds under a paired bootstrap gate. An optional simplification pass keeps code from growing
  without bound. Every version, evaluation, improver log and environment step is archived.
- **Isolated evaluator.** The environment and the score live in one process; the LLM-written policy runs
  in another, on a fresh copy of its files, and only receives observations. Tests cover crashes,
  timeouts, a policy rewriting its own files, and hiding Atari RAM in image mode.
- **Improvers.** Codex CLI (write-restricted sandbox), Claude Code (headless, narrow tool allow-list), and
  any OpenAI-compatible chat API in a multi-round "send files → get scores back" loop.
- **Tasks.** Atari, VizDoom, MuJoCo and MetaWorld via EnvPool 1.2.5, each with a trivial seed program.

## First run

| Setting | Value |
|---|---|
| Task | Breakout-v5, RAM observations, frame skip 4, no sticky actions |
| Seeds | 4 train / 8 dev |
| Improver | DeepSeek (flash model), 2 inner rounds |
| Generations | 1 |

| Version | Train mean | Dev mean |
|---|---:|---:|
| seed program (random actions) | 2.25 | 2.13 |
| generation 1 | 14.75 | **13.00** (promoted; won 6 of 8 seeds, bootstrap P(gain) ≈ 1.0) |

The improver wrote down facts it worked out in the program's notes: the ball must be served with
FIRE, the paddle needs a deadband because of frame skip, and which RAM bytes hold the paddle and ball
positions, confirmed by measurement rather than assumed.

This is a smoke test of the pipeline, not a result. Full runs come next, with all three improvers, more
seeds and more generations.
