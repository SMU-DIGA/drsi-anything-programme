---
title: "Poker joins; Ms. Pac-Man promoted five generations in a row; a run we threw away"
summary: Ms. Pac-Man rose from 277 to 29,688 on hidden dev over five consecutive promotions. Space Invaders reached 35,493 and Pong scored 21 on all 64 test seeds. Poker joined, with Leduc variants scored by NashConv and heads-up no-limit hold'em in duplicate matches. The first HUNL run was discarded after its program exploited a hole in our harness.
date: 2026-11-03 20:54:00 +0800
tags: [Games, OSWorld]
---

## Recursive improvement you can see

| Generation | Ms. Pac-Man, hidden dev (32 seeds) |
|---|---|
| 0 (seed program) | 277 |
| 1 | 17,207 |
| 2 | 19,173 |
| 3 | 20,031 |
| 4 | 25,663 |
| 5 | **29,688** |

Each generation starts from the previous winner, and each promotion won a paired test on seeds that no
improver has seen. The program's changelog shows what accumulated: a maze graph decoded from RAM, then
escapes at junctions, fruit detours and more cautious routing after quick life losses. It also lists the
ideas that were tried and discarded.

## More games

- **Pong:** 21 on all 64 test seeds; the run stopped after three generations without a possible gain.
- **Space Invaders:** 112 → 35,493 on dev in one generation (human reference 1,669). The program aims with
  a lead computed from the invader grid's motion and dodges bullets it reads from RAM.
- **Montezuma's Revenge:** 9,700 → 14,144 on dev in generation 2.

## Poker

Poker is a different kind of problem from the single-agent games: good play must mix actions, bluff
and balance its ranges, and the opponent adapts.

- **Leduc variants, scored by NashConv.** There are 72 Leduc-like limit games, varying ranks, suits,
  raise sizes and raise caps, split 24 / 24 / 24; the standard Leduc game is a test variant. The program is
  asked for an action distribution at every information set, and OpenSpiel computes NashConv exactly.
  Programs must be readable rules: no search or equilibrium computation at run time, and at most 8 KB of
  data. Improvers may solve variants offline to learn principles, but not ship tables. In generation 1,
  normalised NashConv fell from 1.381 (uniform) to **0.154** with about 6 KB of rules.
- **Heads-up no-limit hold'em.** Duplicate matches against three rule bots and the three most recent
  champions, scored in mbb/hand. Before a promotion, the incumbent is re-scored against the same pool.

## A run we threw away

The first HUNL run reported +62,790 mbb/hand: 63 big blinds per hand, far too good. The program's own
notes explained why. Each duplicate pair was replayed immediately in the same process, so on the replay
it knew the board, and it knew that its opponent now held the cards it had just played. Now each seat
is played by a separate, fresh process that shares nothing, each deal is seen once per process, and temp
files, sockets, subprocesses and native code are rejected. A probe program that remembers every board
confirms no repeats. The run was restarted from scratch and its numbers will be reported once it has some.

## OSWorld

In the pure-code OSWorld setting, generation 1 promoted a program that solves 2 of 24 dev tasks, up from
0. It scored 56.5% on train. It is a skill library: instruction parsers dispatch to generic LibreOffice
skills that run through the UNO scripting interface. Most dev tasks need skills that no train task
exercised.
