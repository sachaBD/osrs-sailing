# What we have measured

The lab notebook. `APPROACH.md` says what we intend to build and why;
this says what happened when we ran it, in the order it happened.

Every number here is xp/hour with a 95% interval, from the simulator in
`../porttasks/routing/problem/`, and every one of them rests on the guessed
cost constants in `../tables/params.tsv`. Treat the *rankings* as the findings and the absolute
rates as provisional until those constants are measured in game.

## Layer 2, measured

Built and measured at level 30, 8 seeds of 2 hours each, against the greedy
baseline:

| policy | xp/hr | |
| --- | --- | --- |
| greedy_xp_per_tick | 10,331 +/- 797 | |
| planner, 2 deliveries | **10,417 +/- 275** | parity on the mean, a third the variance |
| planner, 3 deliveries | 9,628 +/- 985 | longer plans are *worse* |

So search reaches parity with greedy and no more, at about 8 seconds of
planning per simulated episode against greedy's nothing. The plans themselves
are clearly better - it finds chains that deliver two tasks on one leg, which
greedy cannot see - but the episode rate does not move.

The reason is in the third row. A longer plan is worse, and higher `rho`
(which biases toward short, quick tasks) is better; both say the same thing.
Committing to a route ahead of time costs more than the leg-sharing gains,
because the agent keeps learning things - a new board, a reroll - that the
plan did not know about.

An oracle variant that reads every board scored *identically*, to the digit.
That is not a bug: at a two-delivery horizon the search finds a plan out of the
offers underfoot before it ever simulates sailing to an unread board, so the
extra information is unreachable. The comparison is vacuous at this horizon
rather than informative, and measuring the value of information properly needs
the deeper search that Layer 2 has just shown does not pay on its own.

Rewritten since, over a scalar core rather than numpy (`core.py`): at three
held tasks and two port indices, numpy's per-call overhead swamps the
arithmetic, and moving to plain ints and tuples was worth 12x. An episode now
plans in 0.4 seconds rather than 8.

    greedy_xp_per_tick     9,983 +/- 652     17 ms/episode
    planner, 2 deliveries  10,589 +/- 306   410 ms/episode

So search does beat greedy, by about 6%, once it is fast enough to measure
properly.

## What is still wrong

Giving the planner *more true information* makes it worse. An oracle that
reads every board plans strictly better sequences - its plan value beats the
blind planner's in every state tested, often several times over - and then
scores lower over an episode. That ordering is impossible for a sound
planner, so something in how plans are executed is wrong, not in how they are
found.

Two causes found and fixed, neither sufficient. The bound only counted prizes
on boards already read, which is admissible when unread boards hold nothing
but not when the search can sail to one and collect, so it was pruning the
branches that used the extra information. And a fixed delivery count with no
terminal value is myopic: the plan reaches further for its two deliveries and
strands the ship somewhere with nothing to do, which better information makes
worse rather than better. Charging for the distance from where a plan ends to
the nearest board recovered part of the gap and not all of it.

What is left is the missing piece the layering predicted: receding-horizon
control needs a value function for what happens after the horizon, and a
distance proxy is a poor one. That is Layer 5's job, and it is now the
argument for Layer 5 rather than a curiosity.

### Policy rollout, which should have come first

Added afterwards, and it is the standard baseline this project should have
started from: take each legal action, let a base policy finish, score the
result, play whichever led somewhere best. Forty lines, no bound to get wrong,
and it supplies from the base policy the value estimate that a truncated
search otherwise has to invent.

Three things had to be right before it worked, all of them textbook and all of
them things we got wrong first:

- **The base policy has to be the good one.** Rollout is its base plus roughly
  one improvement step, so a weakened base caps it. Ours sailed to boards while
  cargo sat aboard, and scored below greedy until it discharged first.
- **The rolled-out future cannot be blind.** With unread boards empty, every
  future is a world where no new work appears, every action scores alike, and
  rollout collapses back to its base.
- **One sampled future is worse than none.** It chases whichever board drew the
  luckiest hand and re-draws every step. Averaging several futures, with the
  same futures scoring every action so the comparison carries no sampling noise
  of its own, is what makes it work.

Level 58, 21 ports, capacity 4, thirty seeds:

| policy | xp/hr |
| --- | --- |
| planner, 2 deliveries | 25,345 +/- 1,331 |
| rollout, 8 futures | 24,746 +/- 1,020 |
| greedy / rollout's base | 21,443 +/- 1,353 |
| best repeatable shuttle | 20,646 +/- 1,340 |

The two searches agree within their error bars while working completely
differently, which is the useful part: an independent method landing in the
same place is evidence that about 25k is real and that neither is leaving much
on the table. Rollout is the slower of the two, so the branch and bound earns
its keep - but it had to be checked against something standard to know that.


## The Layer 2 numbers above do not reproduce (2026-08-28)

Rerun at level 58 on current code and current `params.tsv`, 30 seeds:

    rollout                23,592 +/- 1,040
    greedy_xp_per_tick     23,493 +/- 1,101
    planner                23,089 +/- 1,645
    best_shuttle           22,632 +/- 1,371
    oracle (cheats)        18,963 +/- 1,232

The 18% planner win recorded above is gone: greedy, rollout and the planner
were indistinguishable. A paired per-seed test (same 30 seeds) agreed -
rollout minus greedy was +99 +/- 1,541 - and note that pairing did not tighten
the interval, so per-seed outcomes barely correlate across policies. The
earlier table most likely predates the 20s cargo-handling change and the rho
recalibration, both of which lift the greedy baseline.

Conclusion drawn: the branch and bound had not earned its 400 lines, and the
rollout of the day was collapsing onto its base. Both were replaced by one
rollout, rewritten (below). `plan.py`, `explorer`, `oracle` and
`scout_then_greedy` are deleted; the oracle soundness bug documented above
went with them and is *not* fixed, only removed.

## One rollout, rebuilt

Three changes from the rollout that tied with greedy: 12 sampled futures
rather than 8, a 900-tick rollout horizon rather than 400, and exploring moves
(charter to an unread board, recall) offered as candidates at the top level
rather than only inside the base policy. Beliefs are cached per (epoch, boards
read), so the sampled worlds move only when the real one does.

Level 58, 8-10 seeds - fewer than the 30 used elsewhere, so read these as a
sighting shot rather than a measurement:

| policy | xp/hr | cost |
| --- | --- | --- |
| rollout, 12 futures, 900 ticks | **31,600 +/- 2,400** | 2.1 s/episode |
| greedy_xp_per_tick | 23,143 +/- 1,889 | 18 ms/episode |

About 37% over greedy, well outside the intervals - the first time in this
project that a search has beaten the baseline by more than noise.

Sensitivity, same seeds: 4 futures / 600 ticks gives 27,873; 8 / 900 gives
30,031; 12 / 900 gives 32,366; 16 / 1200 gives 32,978 at 3.3 s/episode. More
sampled futures is what buys the improvement, and the knee is at 12.

Candidates are then raced - every move scored on the first 6 futures, the best
6 kept, only those paying for the rest - which holds the score (31,748 vs
31,648 unraced) at 70% of the cost.
