---
title: Environments
permalink: /environments/
---

# Environments

The selection favors **widely adopted, community-recognized benchmarks**, so that results are comparable
with published RL and VLA numbers.

## Games

Following *Learning Beyond Gradients*, all games run through [EnvPool](https://github.com/sail-sg/envpool) (1.2.5).

| Family | Tasks | Observation | Score |
|---|---|---|---|
| Atari (ALE) | Breakout, Pong, Montezuma's Revenge, … Atari57 | RAM (128 bytes), RGB image, or both | episode return (unclipped, no sticky actions, full game) |
| VizDoom | D1 Basic, D3 Battle | stacked screen + game variables | episode return |

## Embodied robotics (simulation)

| Benchmark | Why it matters | Integration |
|---|---|---|
| **LIBERO** (Spatial / Object / Goal / Long, LIBERO-90) | The most widely reported simulation benchmark for VLA policies (OpenVLA, OpenVLA-OFT, π0, π0.5, …) | Verified (robosuite 1.4 + MuJoCo 2.3.7, EGL rendering); adapter in progress |
| **ManiSkill3** | The standard GPU-parallel manipulation platform for RL and imitation learning; SimplerEnv is built on it | Verified (state and RGB); adapter in progress |
| **SimplerEnv** | Real-to-sim evaluation that correlates with real Google Robot and WidowX/Bridge results | Planned (on top of ManiSkill) |
| **RoboTwin 2.0** | Main bimanual manipulation benchmark | Planned |
| **MetaWorld** (50 tasks) | Classic multi-task RL benchmark | Done (EnvPool) |
| **MuJoCo locomotion** (Ant, HalfCheetah, …) | Classic continuous control | Done (EnvPool) |
| CALVIN, RLBench, BEHAVIOR-1K, Habitat | Long-horizon, household and navigation settings | Later; heavier to set up |

Each embodied task will offer two observation modes:

- **state**: object poses and proprioception, for example LIBERO's `*_pos` / `*_quat` keys. This tests
  the self-improvement loop itself.
- **vision**: RGB-D, camera intrinsics and extrinsics, and proprioception only, without privileged scene
  state. This is the setting comparable to VLA results.

The program API exposes the simulator's standard controller, for example end-effector delta pose plus
gripper. Motion-primitive libraries are **not** given up front. Whether the loop can discover and
accumulate such skills by itself (L2) is one of the research questions. Recent code-as-policy studies such
as CaP-X report that removing hand-designed abstractions hurts frontier models, and that iterative
feedback and skill synthesis recover much of the gap.

## Computer use

| Benchmark | Plan |
|---|---|
| **OSWorld** | The program is a desktop agent: screenshot and accessibility-tree parsing, plus pyautogui actions and an app-level skill library. Scored by OSWorld's own task checkers. Tasks are split by application to prevent overfitting. Many VMs run in parallel. |
