---
title: "Breakout 864 on all test seeds; Montezuma, Ms. Pac-Man and Pong; programs that learn their own memory"
summary: Breakout's final program scores the maximum, 864, on all 64 unseen test seeds. LIBERO-10 (state) reaches 99.0% on test. Three new Atari games pass human level on hidden dev in their first generation. Programs can now learn a frozen memory from their own train episodes, and OSWorld runs with a typed small-model decision function.
date: 2026-11-03 18:10:00 +0800
tags: [Framework, Games, Embodied robotics, OSWorld]
---

## Test results

| Experiment | Seed program | Final program (test) |
|---|---|---|
| Breakout (RAM), 64 test seeds | 2.2 | **864.0**: the maximum on every seed |
| LIBERO-10 (state), 400 test episodes | 0% | **99.0%** |
| LIBERO-Spatial (state), 400 test episodes | 0% | **99.0%** |

Breakout took four generations: 702.8, 849.9, a rejected candidate, then 864.0 on dev. The rejected
candidate is instructive: it scored 864 on all 8 train seeds but 714 on dev, and the paired gate
refused it. The next generation's program reached 864 on dev and then on all 64 test seeds, which
no improver ever saw.

## More games

| Game | Seed program (dev) | Generation 1 (dev, 32 seeds) | Human |
|---|---|---|---|
| Pong | −19.9 | **21.0** (maximum) | 14.6 |
| Ms. Pac-Man | 276.9 | **17,207** | 6,952 |
| Montezuma's Revenge | 0 | **9,700** | 4,753 |

All three promotions won on 32 of 32 dev seeds. Codex wrote the Ms. Pac-Man and Montezuma programs, and
Claude Code wrote Pong. The Ms. Pac-Man program decodes the maze, dots and ghost states from RAM and
plans over a maze graph. The Montezuma program follows a room-by-room route, reacting to the skull, the
spiders and a laser countdown it found in RAM.

These runs use no sticky actions. In Montezuma, seeds then differ mostly by start-up timing, so a high
dev score shows robustness to timing, not to stochastic dynamics. We will report sticky-action
evaluations separately. Space Invaders and Seaquest are queued.

## Programs that learn

Programs had working memory within an episode and knowledge written by the improvers between
generations. They can now also **learn by themselves**: after every train evaluation, a program that
defines a learning step receives its own train episodes (observations, actions and the outcome) and
writes a memory directory. That memory is frozen for dev and test, which never write to it, so scores
stay reproducible and do not depend on task order. Improvers can therefore improve how the program
learns, not only how it acts. It is enabled for the new games, LIBERO-Spatial vision and OSWorld.

## Loop changes

- **Ties go to dev.** Candidates that only match the incumbent on train now reach the dev gate.
  Without this, LIBERO-Spatial vision was stuck: train was 100% while dev was 95%.
- **Stop rule.** A run stops after three generations without a promotion, then runs its test
  evaluation. LIBERO-10 had spent five generations with nothing left to gain.

## OSWorld

OSWorld runs with LibreOffice Calc and OS tasks, comparing two settings. In both, the program decides
every action in code; it can also run code inside the desktop and read the output.

- **Pure code**, with no model at all.
- **Code plus a typed decision function.** The program may ask one fixed small model, Qwen3.5-2B,
  multiple-choice questions and get a probability per option, in the style of TypeSafe's Jev. The model
  never writes text or actions.

Generation 1 is running.
