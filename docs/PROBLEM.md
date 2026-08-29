# The routing problem

What we are optimising, what the agent may do, and what it knows when it
decides. This file is the specification the solver will be written against;
`README.md` covers the sea chart that feeds it.

Settled in conversation on 2026-08-28. Anything marked **[measure]** is a
number nobody has yet taken from the game, and is symbolic until they do.


## 1. Objective

Maximise **XP per hour**: the long-run average reward per unit time of a
*continuing* process.

    g = lim (T -> inf)  E[ total xp earned by T ] / T

This is a **gain-optimal semi-Markov decision process**. Actions have
durations, decisions are only made in port, and there are no episodes (see
S6). The standard handle is the rho-parametrisation: for a candidate rate rho,
maximise the undiscounted sum of `xp_i - rho * dt_i`; the rho at which that
optimum is exactly zero is the optimal gain. Bisect on rho.

Units: **time in ticks** (0.6 s, the game's own quantum - integer arithmetic,
no rounding drift), **reward in xp**, reported as xp/hour. Distance in game
tiles is an *input to the time model*, never a state variable.

### Level is fixed, and levelling is out of scope

XP raises Sailing level, which would change both the task capacity `C` and
which tasks and ports are legal. We do not model that. A solve is always of one
**level slice**: `C` and the legal sets are read off the level once, when the
instance is built, and never change again. So `g` is a function of level rather
than a single number, and each slice is solved on its own. Level moves slowly
next to a task cycle, so nothing is lost by it.


## 2. Static model

Fixed for a solve. Thirty ports, indexed `p`.

| symbol | shape | meaning | status |
| --- | --- | --- | --- |
| `D` | 30x30 | sail time between ports | tiles from `../data/port_distances.json`; **[measure]** tiles -> ticks |
| `tp` | 30 | player-travel time, `inf` where unavailable | destinations known (charter ships); **[measure]** times |
| `rec` | 30 | boat-recall time, `inf` where no shipwright | flags known; **[measure]** times |
| `t_dock` | scalar | docking overhead per port entry | **[measure]** |
| `t_board` | scalar | reading and accepting at a board | **[measure]** |
| `t_drop` | scalar | the displacement half of a `Take` swap | **[measure]** |
| `board` | 30 bool | has a notice board - **23 of 30** | known |
| `charter` | 30 bool | charter ship serves this port - **21 destinations** | known, `../model/transport.tsv` |
| `ship` | 30 bool | has a shipwright - **16 of 30, all of them boards** | known |
| `dock_lvl` | 30 | Sailing level to dock | known, range 1-76 |
| `quest` | 30 bool | quest-gated - **14 of 30** | known; player config |
| `C(level)` | 99 | concurrent **task** capacity | **known**: 1 at lvl 1, 2 at 7, 3 at 28, 4 at 56, 5 at 84 |
| `pool[p]` | ~20 each | tasks a board can offer | known, 439 total |

Each task `t` carries `(board, origin, destination, xp, level, qty)`.
`board` is always either `origin` (outbound, 273 of 439) or `destination`
(inbound, 166). XP runs 69 to 13,143, median 1,574 - a 190x spread, so which
tasks you take dominates how efficiently you sail between them.

Seven tasks have unknown XP. **[decide]** exclude, or impute from level and qty.
All seven are above level 30, so a level-30 slice avoids the question entirely.

Boards also carry **bounty tasks** (unlocked at level 30), which occupy board
slots but are not courier tasks. We ignore them; the consequence is that a
board shows **4** courier tasks, not 8.


## 3. State

The player and the boat are separate. That is the crux of the problem.

| symbol | domain | meaning |
| --- | --- | --- |
| `loc_plr` | 1..30 | which port the player is in |
| `loc_boat` | 1..30 | which port the boat is in |
| `A` | set, `|A| <= C` | accepted tasks |
| `L` | subset of `A` | tasks whose cargo is aboard |
| `O` | 30 x 8 | offers read this epoch; unread entries are unknown |
| `k` | 0..7 | completions since the last reroll |

Initial state: `k = 0`, `A` and `L` empty, `O` entirely unread.

`D`, `tp`, `rec` and the rest are **not state**. They are the environment.

Neither are `xp` and `ticks`, which the simulator carries but nothing in the
dynamics ever reads back. Because a solve is of one fixed level (S1), capacity
and eligibility are frozen when the instance is built, so earned XP feeds
nothing: it is the reward being totalled, and ticks are the clock it is
divided by.


## 4. Actions

Preconditions are hard - an action not listed as legal cannot be taken.

| action | precondition | duration | effect |
| --- | --- | --- | --- |
| `Take(t, v)` | `t` in `O[loc_plr]`, level and dock requirements met; `v` in `A` or `none`, and `v = none` requires `|A| < C` | `t_board` if `v = none`, else `t_board + t_drop` | `A += t`; if `v != none`, `A -= v` and `L -= v`. **Does not** advance `k`. |
| `Sail(p)` | `loc_boat == loc_plr`, `p` dockable | `D[loc_plr][p] + t_dock + t_cargo` | both move to `p` |
| `Charter(p)` | `charter[p]` | `tp[p]` | player only; boat stays |
| `Recall()` | `ship[loc_plr]` | `rec[loc_plr]` | `loc_boat = loc_plr`; `L = {}` - **cargo lost, tasks survive** |

Sailing requires the boat to be with you. Taking work does not - and that is the
whole point (S6).

### Why acquisition is one action, not three

An earlier draft had `Accept(t)` and a free-standing `Abandon(t)`. Both are
folded into `Take`, where `v` names the held task displaced, or `none` when a
slot is free. `Take(t, none)` is the old `Accept`; `Take(t, v)` is a swap.

The reason is that **abandoning alone is unusable by a depth-limited search.**
At one ply it is strictly negative - a task lost, nothing gained, `t_drop`
paid - and the payoff only appears after a later `Accept`. Any branch and
bound with a short horizon and an optimistic bound prunes that branch every
time, so the swap is never discovered. Fusing the two halves puts the whole
trade at a single node, where its value is immediately legible. (The search
core had in fact already stopped generating `Abandon` at all; this makes that
silent omission a deliberate part of the model.)

Folding it in also moves the capacity rule to one place: `|A| < C` stops being
a gate on the action and becomes a constraint on the argument - when the hold
is full, `none` is simply not a legal `v`.

**What this gives up** is dropping a task with nothing to replace it. That
looks dominated: a held task costs nothing but a slot, and a slot only binds
at the moment of acquisition, so freeing one early just pays `t_drop` sooner
for the same outcome. Recorded as a claim rather than a proof - no
counterexample has been constructed, and none is obvious.

**[measure]** whether a swap is one board interaction or two. The wiki says
tasks "can be cancelled at any time at a port master or via the captain's
log". If the port master is not the notice board, dropping and accepting may
not even be co-located, and `t_board + t_drop` is the wrong composition.


## 5. Transitions

### Automatic effects, in this order

Whenever the player is in port `p`, on arrival and after any `Take`:

1. **Load** - every `t` in `A` with `origin(t) == p` and boat present joins `L`.
2. **Deliver** - every `t` in `L` with `destination(t) == p`: award `xp(t)`,
   `k += 1`, remove from `A` and `L`.
3. **Reroll** - if `k == 8`: redraw every board's 8 offers, clear all of `O`,
   set `k = 0`. `A` and `L` are untouched.
4. **Reveal** - if `board[p]`, write the true offers into `O[p]`.

Reveal comes last so that a delivery which triggers a reroll leaves you
looking at the *fresh* board. **[open]** Confirm that is what the game does.

Loading is checked after `Take` as well as on arrival, so accepting an
outbound task while the boat is already in port loads it immediately.

### The reroll

Global - the wiki confirms a new set of tasks "appears on all notice boards
simultaneously". Every observation made this epoch becomes stale; accepted
tasks are unaffected. Displacing a task inside a `Take` does not advance `k`;
only deliveries do.

There are **two** triggers, not one:

1. **8 completions**, as specified. The wiki carries a *[confirmation needed]*
   on this, so it is worth verifying in game.
2. **A daily reset at 00:00 UTC**, which rerolls every board and sets the
   streak back to 0 whatever your progress.

The daily reset is exogenous and on a wall clock, so it breaks the otherwise
self-contained dynamics. Over a session of a few hours it is a rare boundary
event and can reasonably be ignored; a model of a full day cannot ignore it.
**[open]** what the "streak" affects - if it scales rewards, it belongs in the
objective.


## 6. What makes this hard

### It does not decompose into episodes

The obvious move is to treat one reroll cycle as an episode. It fails: `A`
persists through the reroll, so the boundary is not a regeneration point. You
can sit at `k = 7`, fill every slot from the offers you have already scouted,
then complete them across the boundary and begin the next cycle several
completions in with tasks the new offer set never contained.

So "8 completions per reroll" is an accounting invariant, not a planning
budget, and there is no renewal structure to exploit. The gain-optimal SMDP
framing in S1 does not need one.

### Scouting information is perishable; accepted tasks are not

A reroll destroys every board you read. Accepting is the only way to carry
what you learned across the boundary - and it needs no boat, which is exactly
why `Charter` and `Take` pair up. The rhythm is: charter between boards
reading offers, accept the good ones where you stand, rejoin the boat, sail
the route.

Near `k = 7` this creates real pressure to fill every slot before the reroll
burns your scouting. Against that, banking spends slots that the fresh offers
might have filled better. That trade-off is the interesting decision in the
problem and should be *discovered*, not hand-coded.

### Partial observability, and nothing else

The only hidden information is the content of boards not yet read this epoch.
The only stochasticity in the entire process is the reroll draw. Between
rerolls, given full information, this is a **deterministic** prize-collecting
pickup-and-delivery problem with a capacity constraint.

The prior is small and fully specified by data we already hold: an unread
board is a uniform 8-subset of its known pool of about 20 tasks. Every board's
pool has at least 8, so a full draw is always possible. **[open]** How the
guaranteed-per-port tasks modify that draw.

### No deadlocks

There is always a legal teleport, so the agent can never be stranded without
its boat. Worth verifying against the teleport table once we have it: from
every port there must be a teleport to some port with a shipwright, since all
16 shipwrights are boards this should come out comfortably.

### No failure

Voyages cannot capsize. Transitions are deterministic apart from the reroll.


## 7. What the solver has to be

- Exact dynamic programming is out. `O` alone is 23 boards drawing 8 from ~20,
  times the read/unread flags, times positions, times `A` and `L`.
- Between rerolls the deterministic core is a real combinatorial problem -
  branch and bound, beam search or CP over task selection and sequencing.
- Across rerolls, plan against sampled beliefs: determinise the unread boards,
  solve, act, re-plan. Sampling a fresh `O` is precisely what the environment
  does at a reroll, so the simulator and the planner share machinery.
- The ratio objective goes through the rho-parametrisation of S1 rather than
  being optimised directly.


## 8. Still to settle

**[measure]** in the game: **tiles per tick** - this one blocks every XP/hour
number and nothing else will do; docking, board and displacement overheads; charter
and recall times; whether ship tier (Raft / Skiff / Sloop) changes speed.

**[decide]** with a rule: which quests to assume complete. (The unknown-XP
tasks and the quest-gated ports are all above level 30, so a level-30 slice
sidesteps both.)

**[open]** whether reveal really comes after reroll; what the daily streak
affects; whether the 8-completion trigger is right, which the wiki flags as
unconfirmed.

Parameter tables live in `../model/params.tsv` and `../model/transport.tsv`, both hand-editable,
both currently full of placeholders marked `guess`.
