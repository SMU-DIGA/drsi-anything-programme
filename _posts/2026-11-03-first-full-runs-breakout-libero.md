---
title: "First full runs: Breakout 850 on unseen seeds, LIBERO 99% on test"
summary: With three improvers per generation, Breakout rose from 2.5 to 702.8 to 849.9 on hidden dev seeds over two generations. LIBERO-Spatial (state) reached 99.0% on 400 test episodes, LIBERO-Spatial (vision) reached 95.0% on dev, and LIBERO-10 (state) reached 100% on dev after one generation.
date: 2026-11-03 15:30:00 +0800
tags: [Games, Embodied robotics]
---

## Setup

Every run uses the same loop. Each generation starts three candidates from the current incumbent, one per
improver: Codex CLI, Claude Code, and DeepSeek through its API with no tools. Each candidate is re-evaluated
on the train seeds, the best go to the hidden dev seeds, and a candidate is promoted only if it wins a paired
bootstrap test against the incumbent. After a promotion, one simplification pass tries to shorten the code at
the same score. Test seeds are run once, after the loop.

## Breakout (RAM)

| Generation | Promoted from | Dev mean (32 seeds) | Episodes at 864 |
|---|---|---|---|
| 0 (seed) | — | 2.5 | 0 |
| 1 | Claude Code | 702.8 | 0 |
| 2 | Codex | 849.9 | 10 |

Generation 1 already plays well, but 11 of 32 dev episodes end at exactly 428: the ball gets trapped in a
loop late in the first wall. Generation 2 started from that program, and no episode now ends below 827. The
promoted candidate won 21 seeds and lost 11, for a mean gain of 147 points. The DeepSeek candidate also
reached 849.8 on train in generation 2, after scoring 0.4 in generation 1. Once the program was good, even the
improver without tools could refine it.

The program's notes show how it got there. It found an exact rule for paddle motion and a hit rule that fits
about 6,000 observed paddle contacts with no errors. The policy uses them to simulate the ball and plan each
catch.

## LIBERO

| Setting | Gen 1 (dev, 80 episodes) | Gen 2 (dev) | Test (400 episodes) |
|---|---|---|---|
| LIBERO-Spatial, state | 100% | stopped (saturated) | **99.0%** |
| LIBERO-Spatial, vision | 86.3% | **95.0%** | after the run |
| LIBERO-10, state | **100%** | running | after the run |

All three seed programs scored 0%. In vision mode the policy sees only RGB-D images, camera parameters and
proprioception. It segments bowls and plates by colour, back-projects them to 3-D with depth, and checks its
estimate with the wrist camera before grasping. The simplified LIBERO-Spatial (state) program is 189 lines,
down from 254, and has the same test score.

The published VLA numbers are 84.7% (OpenVLA) and 97.6% (OpenVLA-OFT) on LIBERO-Spatial. They are context,
not a head-to-head comparison: those models learn from demonstrations and see RGB only, while our programs use
no demonstrations but do use depth and camera calibration. State mode is easier still.

## Observations

- **The improvers differ.** Claude Code produced 4 of the 6 promotions and Codex 2. In generation 1 Claude
  tends to study the environment at length before acting. On Breakout it spent over an hour on analysis and
  produced the strongest program. Codex iterates faster and was the one that pushed both generation-2 gains.
- **Recursion shows up where there is headroom.** Breakout and LIBERO-Spatial vision both improved in
  generation 2 from the previous generation's program. LIBERO-Spatial state saturated in generation 1, so we
  stopped it.
- **Interaction is not cheap yet.** Breakout used 8.6 M environment steps over two generations, counting
  every evaluation by every improver. Reducing this is on the roadmap.

## Next

More generations on Breakout and LIBERO-10, LIBERO test evaluations, ManiSkill3, and OSWorld. In OSWorld the
program wraps a fixed 2B model, and only the code around the model is improved.
