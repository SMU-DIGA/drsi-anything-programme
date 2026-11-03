---
title: Roadmap
permalink: /roadmap/
summary: "Phases of the programme and the research questions it is designed to answer."
numbered: true
---

## Phase 0: Framework

<span class="badge done">Done</span>

- [x] RSI loop with archive, promotion gate, simplification pass, resume, env-step budget
- [x] Isolated evaluator, with tests for crashes, timeouts, artifact tampering and observation filtering
- [x] Improvers: Codex CLI, Claude Code, OpenAI-compatible chat APIs
- [x] EnvPool families: Atari, VizDoom, MuJoCo, MetaWorld
- [x] End-to-end smoke run (Breakout RAM, DeepSeek): dev 2.1 → 13.0 in one generation

## Phase 1: Games

<span class="badge running">Running</span>

- [ ] Breakout, Pong, Montezuma (RAM and image) with all three improvers (Breakout RAM running); compare against *Learning Beyond Gradients*
- [ ] VizDoom D1/D3, MuJoCo Ant/HalfCheetah
- [ ] Atari57 sweep with a fixed env-step budget, reporting human-normalized scores against PPO curves
- [ ] Ablations: single improver vs. mixed population; with and without shared history; with and without simplification

## Phase 2: Embodied robotics

<span class="badge wip">In progress</span>

- [x] LIBERO adapter (state and vision modes), all four suites
- [ ] LIBERO-Spatial (state) self-improvement run (running)
- [x] ManiSkill3 adapter (PickCube, StackCube, PegInsertionSide, …)
- [ ] SimplerEnv (Google Robot, WidowX)
- [ ] RoboTwin 2.0 (bimanual)
- [ ] L2: a cross-task skill library distilled from train tasks and reused on held-out tasks

## Phase 3: Computer use

<span class="badge planned">Planned</span>

- [ ] OSWorld adapter with parallel VMs, split by application
- [ ] App-level skill library

## Phase 4: Deeper recursion

<span class="badge planned">Planned</span>

- [ ] L3: self-improving improver (prompts, feedback format, search strategy), selected by meta-evaluation
- [ ] Learned pre-filter ("world model over program edits") for expensive domains
- [ ] Container isolation for coding agents
- [ ] Optional L4: fine-tune an open model on its own successful edits

## Open questions

- Does a mixed population of coding agents improve faster than the best single agent at equal cost?
- How much of the gain transfers across tasks through skills and notes (L2) instead of per-task patching?
- Can programs reach VLA-level success on LIBERO from state alone? From vision alone?
- How should env steps be traded against LLM cost when comparing with RL?
