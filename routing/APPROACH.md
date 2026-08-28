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
