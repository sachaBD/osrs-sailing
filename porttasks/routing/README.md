# routing

The port tasks as a routing problem: a simulator of the notice boards, and
(next) policies that decide which tasks to run and in what order.

Three layers, in order, and they are kept apart on purpose.

| | what it is | state |
| --- | --- | --- |
| `world/` | the ground truth: what the game and the map *are* | **done** |
| `problem/` | the search space over it: the SMDP | **done**, on guessed constants |
| `search/` | policies over that problem | **not written yet** |

The line between the first two is the one that matters: `world/` holds what
nobody disputes - a port's coordinates, a task's XP, the 2,181 tiles round
Kandarin - and `problem/` holds what we *assume*, starting with what any of it
costs. When a result looks wrong, that is the first place to look.

`world/survey/` is the odd one out: a one-off job that measured those
distances off the map tiles, whose 24KB of JSON is committed. It needs scipy
and 11MB of tiles; nothing imports it, and nothing has to run it.

    make sim            # walk the simulator one action at a time, in marimo
    make survey         # re-measure the distances        (needs `make tiles`)
    make survey-check   # port pairs the lattice still routes the long way
    make survey-render  # the graph, the sea lanes, a sample of routes

## Where to look

The prose lives in the repo's `docs/`: `PROBLEM.md` (what is being optimised,
and what the agent knows), `INSTANCE.md` (the level-30 slice, small enough to
reason about), `APPROACH.md` (the plan of attack, in layers) and `RESULTS.md`
(what happened when we ran it). `problem.html` is a snapshot of `PROBLEM.md`
for reading, and is not canonical.

    errors.py             typed errors

    world/catalogue.py    what exists: ports, tasks, and the xp table
    world/distances.py    how far apart the ports are
    world/survey/         the one-off that measured those distances

    problem/params.py     what things cost, from tables/params.tsv
    problem/instance.py   world + params fused: names in, arrays out
    problem/sim.py        the SMDP; integer ticks only, states as values

    ../../tools/sim_walkthrough.marimo.py   one state, one action, the next

`world/survey/` has its own README.

## The tables you may want to edit

All of them live in `tables/`, alongside the rest of the project's
hand-edited truth. Nothing in `routing/` is a source of truth on its own.

`params.tsv` holds the cost constants. Most are eyeball guesses, so read any
future ranking of policies as the finding and absolute xp/hr as provisional
until someone measures those numbers in game.

`waypoints.tsv` is hand-placed sea waypoints for straits the lattice cannot
thread. See `world/survey/README.md` for the loop that maintains it.

`boards.tsv` is field notes: notice boards as actually seen in game, one row
per entry. It is the only file here that records what the game does rather
than what we assume, so it is where the open questions in `docs/PROBLEM.md`
get settled.

## Running it from elsewhere

`porttasks` is an installed package (`make install`) and every path it uses is
anchored to the repo by `porttasks.paths`, so `import porttasks.routing` works
from any directory.
