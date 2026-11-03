### What is being improved

A **program** consists of three parts:

- **a policy** that maps each observation to an action,
- **helper modules** (state detectors, skills, planners) that the policy is free to grow,
- **notes**: the program's memory, holding environment facts, failed ideas and a dated changelog.

Following *Learning Beyond Gradients*, the program is the whole "heuristic system": the policy, its state
representation, and its accumulated knowledge. Weights are never trained. The default constraints are:
no neural networks, no reading the environment's source code, no network access. Each experiment can
change them.

### The loop

Each generation does the following:

1. **Propose.** The incumbent program is copied into K isolated workspaces, one per improver. Improvers are
   assigned round-robin. Each workspace contains:
   - a **brief**: the task, the observation and action description, the program contract, rules and tools;
   - **feedback**: per-seed train scores of the incumbent, the log tail of its worst episode, and a table
     of every earlier attempt (who made it, train and dev scores, accepted or not, notes added);
   - the **program** to edit;
   - an **evaluation tool** restricted to the **train seeds**, and a **probing tool** that opens episodes
     exactly as the evaluator does.
2. **Re-evaluate.** After an improver finishes, the evaluator scores its program on the train seeds again.
   Scores the improver reports about itself are never used.
3. **Gate.** The top candidates by train score, and only if they beat the incumbent on train, are evaluated
   on the **hidden dev seeds**. A candidate is promoted if its mean paired gain over the incumbent exceeds
   a minimum and the bootstrap probability of a gain reaches a confidence threshold.
4. **Simplify (optional).** The improver whose candidate won is asked to simplify it. The simpler version is
   kept only if it has fewer lines and its dev score does not drop. This counters the "big ball of mud"
   that accumulated patches produce.
5. **Record.** Everything is archived: every version's program, its train and dev
   evaluations, the improver logs, and a ledger of all environment steps, including the improvers' own
   test runs.

**Test seeds** are used only once, after the loop has finished.

### Improvers

| Kind | How it works |
|---|---|
| Codex CLI | Runs headless in a write-restricted sandbox. It edits the program, evaluates it on train and probes the environment by itself. |
| Claude Code | Runs headless with a narrow tool allow-list and the same workspace tools. |
| Chat API (DeepSeek or any OpenAI-compatible model) | Cannot run tools. It receives the brief, feedback and program, and replies with complete files. These are evaluated on train and the scores and logs are sent back, for several rounds. The best round is kept. |

Mixing improvers gives diversity. The feedback table also exposes each improver to the others' failed
attempts, so the population shares one memory.

### Isolation and anti-gaming

- The **episode process** owns the environment and computes the score. The **policy process** runs on a
  fresh copy of the program and only ever receives the observation and filtered diagnostics. It never sees the
  environment object, the reward or the seed.
- Per-call and initialization timeouts apply. Crashes and timeouts are recorded as errors.
- In image mode, privileged information such as Atari RAM is withheld.
- Workspaces receive only the train seeds. Promotion uses dev seeds; reporting uses test seeds.
- Known limitation: coding agents run as the same OS user, so they could read files outside their
  workspace. The policy itself never learns the seed, which limits what that could exploit. Container
  isolation is planned.

### Levels of recursion

| Level | What improves | Status |
|---|---|---|
| L1 | the task program | <span class="badge done">Done</span> |
| L1.5 | the program's memory (its notes) and the shared attempt history | <span class="badge done">Done</span> |
| L2 | a cross-task skill library (e.g. *grasp an object*, *open an application*), distilled from train tasks | <span class="badge planned">Planned</span> |
| L3 | the improver itself: prompts, feedback format, search strategy, chosen by meta-evaluation | <span class="badge planned">Planned</span> |
| L4 | the LLM's weights, fine-tuned on its own successful edits (open models only, optional) | <span class="badge planned">Planned</span> |

### Where world models fit

In RSI-Anything a learned world model ranks candidate actions before execution. Here the expensive step
is evaluating a candidate **program** (OSWorld VMs, long robot episodes). A predictor of whether an edit
will improve the score, trained on the archive of (program diff, feedback, outcome), could pre-filter
candidates. It becomes worthwhile once real evaluation is expensive, so it is planned for the OSWorld and
embodied tracks. It will be compared against the plain loop as a baseline.

### Evaluation protocol

- Splits: train (visible to improvers), dev (promotion), test (reported once).
- Report test scores of the seed program and of every promoted version, together with the cumulative
  environment steps, including the improvers' own probing and testing. That makes sample-efficiency
  curves comparable with RL baselines, as in *Learning Beyond Gradients*.
- Also report improver cost (tokens, USD, wall time) per generation.
