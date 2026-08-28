# How to solve it

`PROBLEM.md` says what the problem is; `INSTANCE.md` gives a small one to work
on. This says how to attack it, and in what order.

The short version: **build the simulator, solve the deterministic core exactly,
then add uncertainty, and only then reach for learning.** Each layer is
validated against the one below it, and the layer below is a thing we can
trust because it is exact.


## The shape we are exploiting

Two facts from `PROBLEM.md` do the work:

1. **The only stochasticity is the reroll draw.** Between rerolls, given the
   offers, the problem is completely deterministic.
2. **The only hidden state is boards not yet read**, and the prior is small
   and explicit: an unread board is a uniform 4-subset of its known ~19 pool.

So this is not a general POMDP. It is a deterministic combinatorial problem
wrapped in a simple, samplable uncertainty. That is a much better thing to
attack, and it dictates the layering below.


## Layer 0 - the simulator

A faithful implementation of `PROBLEM.md`: integer tick arithmetic, seeded
reroll draws, hard preconditions, and the automatic load/deliver/reroll/reveal
ordering. Everything else in this document is measured against it, so it is
the one component that has to be right rather than good.

It should refuse illegal actions loudly rather than silently no-op, because
every layer above will be generating actions programmatically and a silent
no-op turns a planner bug into a mysterious performance result.

Parameters come from `params.tsv` so the guessed constants stay swappable.


## Layer 1 - baselines

Cheap policies, run first, for two reasons: they establish the floor, and they
catch simulator bugs that a clever planner would hide.

- random legal action
- greedy by XP
- greedy by xp per tick to complete
- scout the nearest boards, then greedy

`INSTANCE.md` predicts the honest floor at roughly 6,600-7,000 xp/hr - the rate
of doing tasks one at a time. Anything that cannot beat that is not batching,
and batching is most of the problem.


## Layer 2 - the deterministic core

**Given a fully known offer set and a state, what is the best sequence?**

This is a prize-collecting pickup-and-delivery problem: choose a subset of the
offered tasks, respect origin-before-destination, respect capacity, and
maximise `XP - rho * time` (see the outer loop below).

Solve it by branch and bound over a horizon of a handful of completions, with
the tail beyond the horizon covered by a value estimate. Pruning needs an
admissible bound, and this is exactly why the distance matrix was made a
proper metric: with the triangle inequality holding, standard relaxations
(nearest-neighbour, minimum spanning tree over the remaining required ports)
are valid lower bounds on remaining travel, and the XP side bounds trivially
by taking the best remaining tasks with routing ignored.

At the level-30 scale - 9 boards times 4 offers, capacity 3, 10 ports - a short
horizon is exactly solvable. **That is the point of the toy instance:** it
gives ground truth. No later result should be believed if it does not match or
beat exact search on instances small enough to solve exactly.


### What it measured

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

### The thing that is still wrong

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

## Layer 3 - the uncertainty

Now the offers are not all known. Two approaches, and the difference between
them is itself the interesting measurement.

**A. Determinised sampling (hindsight optimisation).** Sample N possible
completions of the unread boards, solve each with Layer 2, and take the action
that does best in expectation. Simple, strong, and reuses Layer 2 whole.

Its known flaw matters here: it assumes the future will be known, so it
systematically **under-values scouting**. It will tell you to sail when it
should tell you to go and look.

**B. Belief-space search (POMCP / PO-UCT).** Monte Carlo tree search over
information sets, using the simulator as a black box. It respects what the
agent actually knows at each point, so it prices information correctly. Slower
and fiddlier.

**Do both, and measure the gap.** The A-to-B difference *is* the value of
information in this problem - which settles empirically the question we have
so far only guessed at: how much scouting is worth. Charter ships make looking
nearly free, so the answer is not obvious in either direction.


## Layer 4 - the objective's outer loop

Maximising a *ratio* is not the same as maximising a sum. For a candidate rate
`rho`, have the planner maximise `sum(xp_i - rho * dt_i)`. The `rho` at which
the achievable optimum is exactly zero is the optimal xp/hr.

In practice this bootstraps: start `rho` at the best rate any policy has
achieved so far, re-plan, measure the new achieved rate, update `rho`, repeat.
It converges quickly and every iteration produces a usable policy.

Note that for *comparing* two policies you do not need `rho` at all - simulate
both for a long time and compare xp/hr directly. `rho` is needed inside the
planner, to trade XP against time consistently within a single decision.


## Layer 5 - learning, last

Only once there is a search baseline worth beating. The state is relational -
tasks and ports, not a fixed-length vector - so a learned policy needs either
hand-built features (distance to origin, XP, whether the board is on the way,
slots free, completions to reroll) or a graph/attention model over the port
and task sets.

The honest case for doing it at all: search must re-plan from scratch at every
decision, and a learned policy is fast at inference. If search is fast enough,
learning buys nothing here and should be skipped. Decide that with a
measurement, not in advance.


## What to watch out for

- **Guessed constants.** `sail_speed`, `t_dock`, `t_board` and friends are
  eyeball figures. Run every conclusion across a plausible range of them and
  report only what survives. If policy *ranking* is stable, the finding stands
  even though the absolute xp/hr does not.
- **Hindsight bias.** Layer 3A will under-scout. Do not read its behaviour as
  evidence that scouting is not worth it - that is the one thing it cannot
  tell you.
- **A wrong simulator invalidates everything above it.** Check its dynamics
  against the game before trusting a single number, particularly the reroll
  trigger, which the wiki itself flags as unconfirmed.
- **The daily reset is ignored.** Fine for a session of a few hours, wrong for
  a day.
- **Level 30 is not level 99.** Capacity 3 vs 5, a 6.6x spread in task rates
  vs wider, and no quest-gated ports. Conclusions about *policy shape* should
  be re-checked at the full map before being believed generally.


## Order of work

1. Simulator (Layer 0) and baselines (Layer 1). Establishes the floor and
   shakes out the dynamics.
2. Exact search on the deterministic core (Layer 2). Establishes ground truth.
3. Determinised sampling (Layer 3A) with the `rho` loop (Layer 4). First real
   policy.
4. Belief search (Layer 3B). Measure the value of information.
5. Learning (Layer 5), only if inference speed turns out to matter.

The first three answer the actual question - what is the best achievable xp/hr
at this level, and what does the route look like. Four and five are about
doing it better and faster.
