# routing

Turning the port tasks into a routing problem: a world, a chart of the sea, and
(eventually) a solver that picks *which* tasks to run and in *what order*.

Status: **the chart and the distance matrix.** Nothing here plans a route yet.

## Why a chart first

`src/trip.js` sequences a chosen set of tasks by straight-line distance, which
the top-level README already flags as a known limit. Straight lines are fine
for comparing two options that both go the same way round Kandarin; they are
useless for an optimiser, which will happily "discover" a route that sails
through Karamja.

So: measure the water first, decide what to optimise second.

## What is here

    watermask.py     the cached map tiles -> a boolean ocean, in game coords
    seagraph.py      a waypoint lattice over that ocean, plus port berths
    waypoints.tsv    hand-placed waypoints for straits the lattice cannot thread
    handpoints.py    reads that file
    build_graph.py   builds and caches sea_graph.json  (~3s)
    exact.py         the ocean as a sparse pixel graph: the yardstick
    portmatrix.py    builds port_distances.json, the 30x30 matrix  (~60s)
    check_graph.py   which port pairs the lattice still routes the long way
    suggest.py       traces real water into rows for waypoints.tsv
    render_graph.py  draws the graph so it can be eyeballed
    render_sample.py a contact sheet of sampled routes, one per panel
    world.py         ports and tasks as typed records, plus the OSRS xp table
    errors.py        typed errors

    make chart          # sea graph + distance matrix   (needs `make tiles`)
    make chart-check    # pairs the lattice still routes the long way round
    make chart-render   # the graph, the sea lanes, a sample of routes

    python3 -m routing.render_graph Catherby Aldarin    # draw one route
    python3 -m routing.render_sample 25 3               # another 25, seed 3

Committed: the modules, `waypoints.tsv`, and `port_distances.json` - so the
matrix is usable without downloading the 11MB of tiles. Everything under
`cache/` and `renders/` is regenerable and ignored.

## Fixing a strait

The lattice is coarse on purpose and cannot thread a channel narrower than it,
which shows up as a route going the long way round rather than as anything
crossing land.  The loop is:

    python3 -m routing.check_graph              # which pairs, and by how much
    python3 -m routing.suggest Entrana "Musa Point" >> routing/waypoints.tsv
    python3 -m routing.build_graph              # refuses bad waypoints

`waypoints.tsv` is hand-editable and reviewed; `suggest` only prints rows.

Both renders are worth having. `graph.png` shows what the router *believes*;
`graph_tiles.png` shows what is actually there. Disagreements are the bugs.

## How the chart is built

Zoom-0 wiki tiles are one pixel per game tile, so `make tiles` already gives a
navigable raster. Pixels are classified as water by colour, the largest
connected body is taken as the ocean, a lattice of waypoints is dropped on it
every 32 tiles, and two waypoints are joined when the straight line between
them stays on water. Ports attach at a *berth*: the sea pixel a docked ship
sits on. Berth links are measured by sailing out of the harbour rather than
drawing a chord, because a chord out of a harbour clips the headland that
makes it a harbour.

Consequence worth remembering: no leg in the graph crosses land, by
construction. The failure mode is the opposite one - a strait too narrow for
the lattice to bridge, which shows up as a detour rather than a shortcut.

## The matrix

`port_distances.json` is the thing route search actually plans over: 30 ports,
435 pairs, in game tiles. Ports are the only decision points - there is
nothing to do in the middle of the ocean, and anywhere worth stopping is
already a port - so once it exists the chart has done its work.

Distances come from the pixel-exact water path, not the lattice, then pulled
straight: a grid search steps in only eight directions, so it bills a 22-degree
heading as a staircase, up to 8.2% over sailing the line and varying with the
heading. Measured here: median 3.7% over, worst 7.7%. The matrix is
symmetrised by keeping the shorter of the two directions and closed under the
triangle inequality, both of which only ever shorten a leg, and both sound
because a ship may sail past a port without stopping.

Sanity: Musa Point to Port Sarim is 167 tiles - the Karamja ferry. Catherby to
Rellekka is 2,181, which is **6.5x its straight line**: they share a coastline
but a ship must round the whole of Kandarin. That pair is the argument for
this whole directory.

## Assumptions, and where they will bite

- **Shallows are sailable.** The teal, kelp-speckled water in the south is
  treated as ocean. If a ship cannot actually enter it, the southern routes
  are all wrong.
- **Everything on the water is passable.** No account of docking levels,
  quest-gated seas, weather, or obstacles.
- **Distance is not time.** The matrix measures tiles. Nothing here knows how
  many tiles per second a ship makes, or what a dock-and-load costs, and
  XP/hour cannot be answered until it does. This is the next real unknown.
- **The map is the world.** The raster is only as wide as the downloaded
  tiles, so a route that would leave the frame cannot be found.

## Not decided yet

The interesting choices are still open: what the objective is exactly, how
notice boards refill, how many tasks can be held at once, and whether this
ends as an offline optimiser or something that answers "what next" while you
play. See the conversation, not this file.
