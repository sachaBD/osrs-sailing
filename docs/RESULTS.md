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


## The rules baseline, in Rust (2026-09-08)

The search was deleted and rebuilt in Rust behind a JSON seam: Python exports
an `Instance`, the crate reads it, and a differential test replays five
thousand steps of random legal play through `sim.py` to prove the two
simulators agree. An episode now costs about a millisecond, so 300 seeds is
routine and every number below has an interval worth reading.

The policy is a player's rule, stated as one. Rank the work, charter out to
look at the best of it, take it if it is there, stop when nothing more would
improve the trip - then charter to the far end of the longest run, recall the
boat to *that* pickup, and sail home laden.

Level 67, 300 seeds of 3.3 hours:

| | xp/hr | |
| --- | --- | --- |
| baseline | **87,874 +/- 701** | |
| ...before pricing agreed with execution | 74,242 +/- 713 | |
| ...before the teleports were modelled | 72,132 +/- 643 | |
| one task at a time | ~15,000 | the floor |
| best hold-filling bundle | 147,566 | Etceteria -> Rellekka, if it could always be filled |

### Three bugs, and two of them were the same bug

Twice the policy oscillated: a score that depended on **where the player was
standing**, so two ports each looked better from the other and it chartered
between them until the horizon. First the route was priced from the player
rather than the boat, which cost a third of the rate. Then the rendezvous fell
back to `nearest_shipwright`, which skips the port you are on - so Port
Khazard's nearest was Brimhaven and Brimhaven's was Port Khazard, and one seed
spent 92% of its clock on the loop. It widened the interval elevenfold and was
invisible in the mean.

Neither ever crashed, so the regression test watches the clock rather than the
score: no episode may spend more than a quarter of its ticks off the boat.

### The score has to price what the policy actually does

The third was worth 18% on its own. The rendezvous rule charters out to the
longest run's origin and recalls the boat there, so the outbound leg is never
sailed - but the *score* was still charging for it, from wherever the boat
happened to sit. A 106-tick shuttle priced at 49,189 xp/hr when the policy
went on to run it at 98,377.

Pricing each candidate set from where its own boat would meet it took the
baseline from 74,242 to 87,874, and changed the shape of play more than the
rate: the mean hold fell from 2.78 slots to 1.99, legs sailed full from 34% to
11%, and the tasks it will touch at all from 208 to 141. Correctly priced, the
rule refuses far more work than it accepts.

### What the hold occupancy says

The stopping rule is "no task has a positive delta", and it does the work it
was supposed to: on a state holding one leg of the Etceteria-Rellekka shuttle,
**3 of 337 eligible tasks price positive** - the three co-directional ones,
each adding zero extra ticks. Everything else is negative, a long-haul task at
-9,749 xp/hr for +1,663 ticks among them. The hold sits at 2 of 4 slots
because the corridor has only three companions in the pool and a board shows
five of about twenty, so they are rarely all on offer at once.

So the gap to the 147k bundle ceiling is not the rule failing to refuse
filler. It is that the good corridor cannot often be filled.


## The lab: what beats the baseline, and what does not (2026-09-08)

Three attempts on the rules baseline, every one measured **paired** - the same
seeds for every policy, and the interval quoted on the *difference*. Level 67,
100 seeds of 3.3 hours. `search/src/lab.rs` holds all of it; the baseline in
`policy.rs` is untouched and still scores 87,874 to the digit.

| policy | xp/hr | vs baseline, paired | cost |
| --- | --- | --- | --- |
| baseline | 87,724 +/- 1,154 | - | 1 ms |
| exact routing | 86,976 +/- 1,300 | **-749 +/- 531** | 6 ms |
| rho = 86,656 | 82,778 +/- 1,091 | **-4,946 +/- 1,383** | 1 ms |
| rho + exact | 82,481 +/- 1,118 | -5,243 +/- 1,396 | 5 ms |
| rollout, 8 futures x 1,800 ticks | 94,376 +/- 1,351 | +6,652 +/- 1,571 | 2.7 s |
| rollout, 16 x 1,800 | 96,958 +/- 1,390 | +9,233 +/- 1,702 | 5.0 s |
| rollout, 8 x 3,600 | 98,228 +/- 1,243 | +10,504 +/- 1,575 | 6.2 s |
| rollout, 16 x 3,600 | **101,410 +/- 1,207** | **+13,686 +/- 1,513** | 11.5 s |

### The gain-optimal acceptance rule loses, and the reason is worth keeping

`PROBLEM.md` and `APPROACH.md` both prescribe the rho-parametrisation: accept
when `xp - rho * dt > 0`, with rho the long-run rate. Applied to this policy it
is **5,000 xp/hr worse**, and the first version of it scored 4,068 - barely
above zero.

The rule is right for choosing a *cycle* and wrong for a greedy sequential
acceptance, because the anchor task bears the whole trip's travel. At level 67
exactly three tasks in the game clear rho = 86,656 on their delivery leg alone,
so a policy that gates its first pick on rho stands still waiting for one.
Ungating the anchor - the alternative to starting a trip is not "earn rho", it
is "earn zero" - recovers most of it and still loses.

What the baseline does instead is better than the textbook: **"does this raise
the trip's own rate" is a state-dependent rho.** On a hot trip it demands more,
on a cold one less, which tracks opportunity cost the way a relative-value
function does and a scalar cannot. The constant is the standard answer and the
hand-written rule is closer to the right object.

### Exact routing does not pay either

Nearest-neighbour ordering replaced by exact Held-Karp over (picked, delivered,
here) - a few thousand cells at capacity four. It is **-749 +/- 531** at six
times the cost. A better tour changes the ranking slightly without improving
it; nearest neighbour's error was apparently harmless and possibly a mild
regulariser. Kept in `route.rs` as `ticks_exact` because it is the honest
reference for what the heuristic costs, which turns out to be nothing.

### Rollout works, and has not saturated

One step of policy iteration over the baseline: try each candidate move, let
the baseline finish, play whichever led somewhere best. **+13,686 +/- 1,513,
about 16%**, and the first policy in this project to cross 100k.

The first attempt scored 409 xp/hr. Three defects, and all three are the same
ones `RESULTS.md` recorded the last time this project built a rollout:

- **The sampled worlds were rebuilt for every candidate.** So candidates were
  not compared against identical futures, and since drawing 21 boards costs
  more than the rollout it pays for, it was also 3.5x slower than it needed to
  be. Build the worlds once per decision and share them.
- **No incumbent.** Every candidate converges back to base behaviour within a
  few hundred ticks, so they score alike, the argmax picks whichever noise
  favoured, and the policy chartered in circles. The base's own move is now the
  incumbent and only loses to a strict improvement.
- **Twenty candidates that could not matter** - chartering to boards already
  read this epoch, which tells you nothing you do not know.

### The horizon saturates at the reroll, as predicted

Swept at 8 futures, 60 seeds, against a measured reroll period of **1,981
ticks**:

| horizon | vs baseline, paired | |
| --- | --- | --- |
| 900 | **-12,712 +/- 2,594** | worse than not searching at all |
| 1,800 | +5,722 +/- 2,105 | |
| **2,700** | **+10,711 +/- 1,961** | the knee, about 1.4 rerolls |
| 3,600 | +9,472 +/- 2,059 | flat |
| 5,400 | +9,952 +/- 2,062 | flat |

The prediction was the user's and it is right: every board redraws at a reroll,
so sampled offers beyond one are a fresh uniform draw carrying no information
about the real one, and looking further buys nothing. It saturates slightly
*past* one reroll rather than exactly at it, which is what accepted tasks
surviving a reroll predicts - the offers stop mattering at the boundary but the
consequences of having taken one do not.

Too short is much worse than too long: at 900 ticks rollout is 12,700 xp/hr
**below the baseline**, because it cannot see far enough to know a long haul
pays off and refuses everything that does not pay at once. This is the same
myopia the Layer 2 planner had, and it is why the fixed-delivery-count horizon
there was the wrong shape.

Note this corrects the row above. Reading "16 x 3,600 beats 8 x 1,800" as *the
horizon* not having saturated was wrong - the futures were doing that work.
More sampled futures still helps; more horizon, past 2,700, does not.

Read the uplift as a **bound on what the hand-written rule leaves on the
table** - about 16% - rather than as a policy anyone would run. It needs a
simulator, and it needs eleven seconds to plan what the baseline plans in one
millisecond.
