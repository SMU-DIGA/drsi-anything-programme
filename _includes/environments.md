### Games

Following *Learning Beyond Gradients*, all games run through [EnvPool](https://github.com/sail-sg/envpool) (1.2.5).

| Family | Tasks | Observation | Score | Status |
|---|---|---|---|---|
| Atari (ALE) | Breakout, Pong, Ms. Pac-Man, Montezuma's Revenge, Space Invaders, Seaquest, … Atari57 | RAM (128 bytes), RGB image, or both | episode return (unclipped, no sticky actions, full game) | <span class="badge running">Running</span> |
| VizDoom | D1 Basic, D3 Battle | stacked screen + game variables | episode return | <span class="badge done">Done</span> |

### Embodied robotics

All embodied work currently runs in simulation.

| Benchmark | Why it matters | Status |
|---|---|---|
| **LIBERO** (Spatial / Object / Goal / Long, LIBERO-90) | The most widely reported simulation benchmark for VLA policies (OpenVLA, OpenVLA-OFT, π0, π0.5, …) | <span class="badge done">Done</span> |
| **ManiSkill3** | The standard GPU-parallel manipulation platform for RL and imitation learning; SimplerEnv is built on it | <span class="badge done">Done</span> |
| **SimplerEnv** | Real-to-sim evaluation that correlates with real Google Robot and WidowX/Bridge results; built on ManiSkill | <span class="badge planned">Planned</span> |
| **RoboTwin 2.0** | Main bimanual manipulation benchmark | <span class="badge planned">Planned</span> |
| **MetaWorld** (50 tasks) | Classic multi-task RL benchmark | <span class="badge done">Done</span> |
| **MuJoCo locomotion** (Ant, HalfCheetah, …) | Classic continuous control | <span class="badge done">Done</span> |
| CALVIN, RLBench, BEHAVIOR-1K, Habitat | Long-horizon, household and navigation settings; heavier to set up | <span class="badge planned">Planned</span> |

Each embodied task will offer two observation modes:

- **state**: object poses and proprioception, for example LIBERO's per-object position and orientation. This tests
  the self-improvement loop itself.
- **vision**: RGB-D, camera intrinsics and extrinsics, and proprioception only, without privileged scene
  state. This is the setting comparable to VLA results.

The program API exposes the simulator's standard controller, for example end-effector delta pose plus
gripper. Motion-primitive libraries are **not** given up front. Whether the loop can discover and
accumulate such skills by itself (L2) is one of the research questions. Recent code-as-policy studies such
as CaP-X report that removing hand-designed abstractions hurts frontier models, and that iterative
feedback and skill synthesis recover much of the gap.

### OSWorld

| Benchmark | Plan | Status |
|---|---|---|
| **OSWorld** | The program decides every action in code: it parses the screenshot, the accessibility tree and the output of code it runs inside the desktop. Two settings: pure code, or code that may also ask one fixed small model (Qwen3.5-2B) typed multiple-choice questions, never free text. Scored by OSWorld's own task checkers. First apps: LibreOffice Calc and OS, with tasks split into train, dev and test. | <span class="badge running">Running</span> |

### Abstract reasoning

| Benchmark | Plan | Status |
|---|---|---|
| **ARC-AGI-1, 2 and 3** | One program for all three: static puzzles (pass@2, exact match) and interactive ARC-AGI-3 games (official engine offline, level-weighted score). Dev uses only puzzles new in ARC-AGI-2 and unseen games; test is the official public evaluation sets and 8 held-out public games. | <span class="badge running">Running</span> |
