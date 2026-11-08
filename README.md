# DRSI-Anything

**Delegative Recursive Self-Improvement across General Domains**: LLMs do not act themselves; they delegate the acting to programs they write and repeatedly improve, for video games, text games, embodied robotics, computer use and abstract reasoning. Neuro-symbolic programs (code, optionally calling smaller models) are our main form of delegation. The programme was earlier called NS-RSI-Anything.

**[Project page](https://smu-diga.github.io/drsi-anything-programme/)** · [中文](README.zh-CN.md) · [Design](https://smu-diga.github.io/drsi-anything-programme/#design) · [Environments](https://smu-diga.github.io/drsi-anything-programme/#environments) · [Results](https://smu-diga.github.io/drsi-anything-programme/#results)

An LLM writes a program that solves a task (a game bot, a robot controller, a desktop agent). Then LLMs
improve that program over many generations, using only interaction feedback from the environment. The
object being improved is a **delegate**. Today it is mostly software (a policy, its state detectors and skills, and a
notes file that serves as the program's memory), and a program may hand part of a decision to an LLM through a typed
decision function. Following [Weight-Space Programming](https://rikiyat.github.io/blog/weight-space-programming/), where an LLM reads and writes a network's weights
directly without an optimizer, the weights of that delegate LLM can also be edited directly by an improver. The results
reported so far use code only (plus a frozen small model in OSWorld); direct weight editing is planned and has not been run.

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

Work in progress. The core loop and the EnvPool task families work end to end. This repository hosts the programme's documents and results;
the implementation is not public.

| Component | Status |
|---|---|
| RSI loop, archive, promotion gate, resume, env-step ledger | Done |
| Isolated evaluator (policy in a separate process, no access to reward or seed) | Done |
| Improvers: Codex CLI, Claude Code, OpenAI-compatible chat API (DeepSeek) | Done |
| Video games: Atari-5 from pixels, sticky actions (above human on 4 of 5; Q*bert 52,418 test) | Done |
| Video games: VizDoom | Done |
| Text games: ScienceWorld, one program for 30 task types (85.0 test) | Done |
| Embodied robotics: MuJoCo locomotion, MetaWorld, ManiSkill3 | Done |
| Embodied robotics: LIBERO (Spatial state 99.0% test; LIBERO-10 state 99.0% test; Spatial vision 95.3% test; LIBERO-10 vision 87.0% test) | Done |
| Embodied robotics: SimplerEnv, RoboTwin 2.0 | Planned |
| Computer use: OSWorld Calc + OS (test 16.7% with a small model available, 4.2% pure code) | Done |
| Abstract reasoning: ARC-AGI-1, 2 and 3, one program for static puzzles and interactive games | Running |

Status: Done (integrated and tested) · Running (experiment in progress) · In progress (being built) · Planned (not started).

Headline results (programs written and refined by LLM improvers; no gradient training, no demonstrations):

- **Atari-5 (pixels only, sticky actions):** above the human score on 4 of 5 games on 64 unseen test seeds; Q*bert 183 → 52,418.
- **ScienceWorld:** one program for all 30 task types, 2.5 → 85.0 on all 1,819 official test variations after four rounds and one merged specialist (86.8 on SwiftSage's first 10 variations per type, above SwiftSage with GPT-4: 84.68).
- **LIBERO (state):** 99.0% on 400 test episodes for both LIBERO-Spatial and LIBERO-10, each after 1 generation; from vision only (RGB-D), 95.3% on LIBERO-Spatial and 87.0% on LIBERO-10.


## License

MIT
