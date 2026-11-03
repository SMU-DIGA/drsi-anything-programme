---
title: Choosing embodied environments; LIBERO and ManiSkill3 running
summary: Robotics work will focus on widely recognized benchmarks, in the order LIBERO → ManiSkill3 → SimplerEnv → RoboTwin 2.0. LIBERO and ManiSkill3 now run headless on our servers.
tags: [robotics, environments]
---

## Selection principle

Results should be directly comparable with the robot-learning literature, so the robotics track uses the
benchmarks the community reports on most often rather than the newest ones:

1. **LIBERO**: the most widely reported simulation benchmark for VLA policies.
2. **ManiSkill3**: the standard GPU-parallel manipulation platform; SimplerEnv builds on it.
3. **SimplerEnv**: real-to-sim evaluation correlated with real Google Robot and WidowX results.
4. **RoboTwin 2.0**: bimanual manipulation.

MetaWorld and MuJoCo locomotion are already supported through EnvPool. CALVIN, RLBench, BEHAVIOR-1K and
Habitat are deferred because they are heavier to set up.

Recent code-as-policy studies (e.g. CaP-X) find that frontier models struggle once hand-designed
abstractions are removed, and that iterative feedback and skill synthesis recover much of the gap. That
is exactly the mechanism our loop tests, so programs get only the simulator's standard controller and must
build their own skills.

## Status

- **LIBERO** runs headless with EGL rendering. Observations include the pose of every object in the scene, which makes a state-based mode straightforward. It runs at about 27 steps/s
  with two cameras.
- **ManiSkill3** runs in both state and RGB modes.

Next: task adapters exposing two observation modes, **state** (object poses) and **vision** (RGB-D and
camera parameters only).
