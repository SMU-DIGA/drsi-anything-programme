---
title: Design
permalink: /design/
---

# Design

## 1. What is being improved

A **program** is a directory:

```text
program/
├── policy.py      # class Policy: __init__(spec) / reset() / act(obs, info) -> action
├── *.py           # any helper modules: detectors, skills, planners
└── NOTES.md       # the program's memory: environment facts, failed ideas, dated changelog
```

Following *Learning Beyond Gradients*, the program is the whole "heuristic system": the policy, its state
representation, and its accumulated knowledge. Weights are never trained. The default constraints are:
no neural networks, no reading the environment's source code, no network access. Each experiment can
change them.

## 2. The loop

Each generation does the following:

1. **Propose.** The incumbent program is copied into K isolated workspaces, one per improver. Improvers are
   assigned round-robin from the configured list. Each workspace contains:
   - `BRIEF.md`: task, observation and action description, program contract, rules, tools.
   - `FEEDBACK.md`: per-seed train scores of the incumbent, the log tail of its worst episode, and a table
     of every earlier attempt (who made it, train and dev scores, accepted or not, notes added).
   - `program/`: the artifact to edit.
   - `./eval.sh`: evaluates `program/` on the **train seeds only**.
   - `./py`: Python with the simulator installed, for probing the environment.
2. **Re-evaluate.** After an improver finishes, the evaluator scores its program on the train seeds again.
   Scores the improver reports about itself are never used.
3. **Gate.** The top candidates by train score, and only if they beat the incumbent on train, are evaluated
   on the **hidden dev seeds**. A candidate is promoted if the mean paired difference exceeds `min_gain`
   and its bootstrap probability is at least `confidence`.
4. **Simplify (optional).** The improver whose candidate won is asked to simplify it. The simpler version is
   kept only if it has fewer lines and its dev score does not drop. This counters the "big ball of mud"
   that accumulated patches produce.
5. **Record.** Everything is archived under `runs/<name>/`: every version's program, its train and dev
   evaluations, the improver logs, and a ledger of all environment steps, including the improvers' own
   test runs.

**Test seeds** are used only once, after the loop has finished.

## 3. Improvers

| Kind | How it works |
|---|---|
| Codex CLI | `codex exec` in a `workspace-write` sandbox; can run `./eval.sh` and probe scripts itself |
| Claude Code | `claude -p` in `acceptEdits` mode with a narrow tool allow-list |
| Chat API (DeepSeek or any OpenAI-compatible model) | Sees brief, feedback and all program files, and replies with complete files. The framework evaluates them on train and sends back scores and logs, for `inner_steps` rounds. The best round is kept. |

Mixing improvers gives diversity. The feedback table also exposes each improver to the others' failed
attempts, so the population shares one memory.

## 4. Isolation and anti-gaming

- The **episode process** owns the environment and computes the score. The **policy process** runs on a
  fresh copy of `program/` and only ever receives `obs` and a filtered `info`. It never sees the
  environment object, the reward or the seed.
- Per-call and initialization timeouts apply. Crashes and timeouts are recorded as errors.
- In image mode, privileged information such as Atari RAM is stripped from `info`.
- Workspaces receive only the train seeds. Promotion uses dev seeds; reporting uses test seeds.
- Known limitation: coding agents run as the same OS user, so they could read files outside their
  workspace. The policy itself never learns the seed, which limits what that could exploit. Container
  isolation is planned.

## 5. Levels of recursion

| Level | What improves | Status |
|---|---|---|
| L1 | the task program | done |
| L1.5 | the program's memory (`NOTES.md`) and the shared attempt history | done |
| L2 | a cross-task skill library (e.g. `grasp(obj)`, `open_app(name)`), distilled from train tasks | planned |
| L3 | the improver itself: prompts, feedback format, search strategy, chosen by meta-evaluation | planned |
| L4 | the LLM's weights, fine-tuned on its own successful edits (open models only) | optional |

## 6. Where world models fit

In RSI-Anything a learned world model ranks candidate actions before execution. Here the expensive step
is evaluating a candidate **program** (OSWorld VMs, long robot episodes). A predictor of whether an edit
will improve the score, trained on the archive of (program diff, feedback, outcome), could pre-filter
candidates. It becomes worthwhile once real evaluation is expensive, so it is planned for the OSWorld and
embodied tracks. It will be compared against the plain loop as a baseline.

## 7. Evaluation protocol

- Splits: train (visible to improvers), dev (promotion), test (reported once).
- Report test scores of the seed program and of every promoted version, together with the cumulative
  environment steps, including the improvers' own probing and testing. That makes sample-efficiency
  curves comparable with RL baselines, as in *Learning Beyond Gradients*.
- Also report improver cost (tokens, USD, wall time) per generation.
