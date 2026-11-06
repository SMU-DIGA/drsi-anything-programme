---
title: "Sticky actions: what broke, and what the loop fixed"
summary: "Under sticky actions the no-sticky Atari champions lost between 25% and 95% of their scores. Restarted with sticky actions in the loop, the improvers made them robust: Ms. Pac-Man scored 38,306 and Breakout 788 on sticky test seeds, and Montezuma's Revenge climbed from 3,441 to 80,184 on dev. Leduc finished ten generations, all promoted. A correction on OSWorld."
date: 2026-11-04 07:31:00 +0800
tags: [Games, OSWorld]
---

## The no-sticky scores were partly memorised

Without sticky actions an Atari game is nearly deterministic, and many dev seeds replay the same game. We played each
champion on 64 fresh seeds with and without sticky actions (each step repeats the previous action with probability
0.25). Pong kept 75%, Breakout 53%, Space Invaders 47%, Ms. Pac-Man 18% and Montezuma's Revenge 5%. Programs that
re-plan from the live state at every step held up best; programs built on exact timing did not.

## Sticky actions in the loop

We restarted each game from its no-sticky champion with sticky actions in train, dev and test, and new seeds
throughout.

| Game | Start (sticky dev) | Best dev | Sticky test |
|---|---|---|---|
| Ms. Pac-Man | 10,029 | 44,257 | **38,306** |
| Breakout | 479 | 766 | **788** |
| Montezuma's Revenge | 3,441 | 80,184 | running |
| Space Invaders | 28,219 | 43,351 | running |

The fixes are readable. Ms. Pac-Man now treats a junction exit as safe only if it keeps a two-step lead over every
ghost until open corridor. Breakout scores each move plan under nine sticky-delay scenarios and avoids unnecessary
action changes. Montezuma's Revenge jumps from standing inside measured windows, because a repeated input only delays
a standing jump, and retries a section after a death instead of following a fixed script. Dev seeds also stopped
tying, so the paired gate now tests generalization.

## Leduc: ten promotions in ten generations

NashConv divided by the largest raise fell from 1.381 (uniform play) to 0.109 on dev and 0.106 on test; on the
standard Leduc game it is 0.087. The policy is still a readable rule set with no search.

## A correction on OSWorld

The run in which programs may ask a small model typed multiple-choice questions reached 5 of 24 dev tasks, ahead of
the pure-code run at 2 of 24. Its champion, however, never calls the model: it is a larger pure-code skill library.
Only unpromoted candidates used the model. We had read the result as evidence for the model; it is not.
