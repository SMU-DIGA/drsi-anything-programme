### Phase 0: Framework

<span class="badge done">Done</span>

- <span class="check done" aria-label="done">✓</span> RSI loop with archive, promotion gate, simplification pass, resume, env-step budget
- <span class="check done" aria-label="done">✓</span> Isolated evaluator, with tests for crashes, timeouts, artifact tampering and observation filtering
- <span class="check done" aria-label="done">✓</span> Improvers: Codex CLI, Claude Code, OpenAI-compatible chat APIs
- <span class="check done" aria-label="done">✓</span> EnvPool families: Atari, VizDoom, MuJoCo, MetaWorld
- <span class="check done" aria-label="done">✓</span> End-to-end smoke run (Breakout RAM, DeepSeek): dev 2.1 → 13.0 in one generation

### Phase 1: Games

<span class="badge running">Running</span>

- <span class="check" aria-label="open">○</span> Breakout, Pong, Montezuma (RAM and image) with all three improvers (Breakout RAM running); compare against *Learning Beyond Gradients*
- <span class="check" aria-label="open">○</span> VizDoom D1/D3, MuJoCo Ant/HalfCheetah
- <span class="check" aria-label="open">○</span> Atari57 sweep with a fixed env-step budget, reporting human-normalized scores against PPO curves
- <span class="check" aria-label="open">○</span> Ablations: single improver vs. mixed population; with and without shared history; with and without simplification

### Phase 2: Embodied robotics

<span class="badge wip">In progress</span>

- <span class="check done" aria-label="done">✓</span> LIBERO adapter (state and vision modes), all four suites
- <span class="check" aria-label="open">○</span> LIBERO-Spatial (state) self-improvement run (running)
- <span class="check done" aria-label="done">✓</span> ManiSkill3 adapter (PickCube, StackCube, PegInsertionSide, …)
- <span class="check" aria-label="open">○</span> SimplerEnv (Google Robot, WidowX)
- <span class="check" aria-label="open">○</span> RoboTwin 2.0 (bimanual)
- <span class="check" aria-label="open">○</span> L2: a cross-task skill library distilled from train tasks and reused on held-out tasks

### Phase 3: Computer use

<span class="badge planned">Planned</span>

- <span class="check" aria-label="open">○</span> OSWorld adapter with parallel VMs and a fixed small model inside the program (in progress)
- <span class="check" aria-label="open">○</span> App-level skill library

### Phase 4: Deeper recursion

<span class="badge planned">Planned</span>

- <span class="check" aria-label="open">○</span> L3: self-improving improver (prompts, feedback format, search strategy), selected by meta-evaluation
- <span class="check" aria-label="open">○</span> Learned pre-filter ("world model over program edits") for expensive domains
- <span class="check" aria-label="open">○</span> Container isolation for coding agents
- <span class="check" aria-label="open">○</span> L4: let the improver write the weights of an open delegate LLM directly (weight-space programming), gated like any other edit

### Open questions

- Does a mixed population of coding agents improve faster than the best single agent at equal cost?
- How much of the gain transfers across tasks through skills and notes (L2) instead of per-task patching?
- Can programs reach VLA-level success on LIBERO from state alone? From vision alone?
- How should env steps be traded against LLM cost when comparing with RL?
