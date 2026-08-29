# survey

**A one-off job, not a library.** Map tiles in, `derived/port_distances.json`
out. Nothing imports this directory, and its output is committed, so you run
it only when the map itself changes: a new port, or a strait it routes badly.
Everything else in the project reads the JSON.

    watermask.py    the cached map tiles -> a boolean ocean, in game coords
    seagraph.py     a waypoint lattice over that ocean, plus port berths
    handpoints.py   reads tables/waypoints.tsv: hand-placed waypoints
                    for straits the lattice cannot thread
    exact.py        the ocean as a sparse pixel graph: the yardstick
    measure.py      builds the 30x30 matrix  (~60s)
    build.py        builds and caches sea_graph.json  (~3s)
    check.py        which port pairs the lattice still routes the long way
    suggest.py      traces real water into rows for waypoints.tsv
    render.py       draws the graph so it can be eyeballed
    sample.py       a contact sheet of sampled routes, one per panel

    make survey          # sea graph + distance matrix   (needs `make tiles`)
    make survey-check
    make survey-render

    python3 -m porttasks.routing.world.survey.render Catherby Aldarin   # draw one route
    python3 -m porttasks.routing.world.survey.sample 25 3               # another 25, seed 3

## Why a chart at all

`web/js/trip.js` sequences a chosen set of tasks by straight-line distance.
Straight lines are fine for comparing two options that both go the same way
round Kandarin; they are useless for an optimiser, which will happily
"discover" a route that sails through Karamja.

Catherby to Rellekka is 2,181 tiles, **6.5x its straight line**: the two share
a coastline, but a ship must round the whole of Kandarin. That pair is the
argument for this directory.

## How it is built

Zoom-0 wiki tiles are one pixel per game tile, so `make tiles` already gives a
navigable raster. Pixels are classified as water by colour, the largest
connected body is taken as the ocean, a lattice of waypoints is dropped on it
every 32 tiles, and two waypoints are joined when the straight line between
them stays on water. Ports attach at a *berth*: the sea pixel a docked ship
sits on. Berth links are measured by sailing out of the harbour rather than
drawing a chord, because a chord out of a harbour clips the headland that
makes it a harbour.

Consequence worth remembering: **no leg crosses land, by construction.** The
failure mode is the opposite one - a strait too narrow for the lattice to
bridge, which shows up as a detour rather than a shortcut.

Matrix distances come from the pixel-exact water path, not the lattice, then
pulled straight: a grid search steps in only eight directions, so it bills a
22-degree heading as a staircase, up to 8.2% over sailing the line. Measured
here: median 3.7% over, worst 7.7%. The matrix is symmetrised by keeping the
shorter of the two directions and closed under the triangle inequality - both
only ever shorten a leg, and both are sound because a ship may sail past a
port without stopping. The triangle inequality holding is what makes the
planner's admissible bounds valid, so it is asserted, not assumed.

Sanity: Musa Point to Port Sarim is 167 tiles - the Karamja ferry.

## Fixing a strait

The lattice is coarse on purpose and cannot thread a channel narrower than it.
The loop is:

    python3 -m porttasks.routing.world.survey.check      # which pairs, and by how much
    python3 -m porttasks.routing.world.survey.suggest Entrana "Musa Point" >> tables/waypoints.tsv
    python3 -m porttasks.routing.world.survey.build      # refuses bad waypoints

`waypoints.tsv` is hand-editable and reviewed; `suggest` only prints rows.

Both renders are worth having. `graph.png` shows what the router *believes*;
the `--tiles` render shows what is actually there. Disagreements are the bugs.

## Assumptions, and where they will bite

- **Shallows are sailable.** The teal, kelp-speckled water in the south is
  treated as ocean. If a ship cannot enter it, the southern routes are wrong.
- **Everything on the water is passable.** No account of docking levels,
  quest-gated seas, weather, or obstacles.
- **Distance is not time.** The matrix measures tiles. Turning tiles into
  ticks is `../model/params.tsv`'s job, and `sail_speed` is a guess.
- **The map is the world.** The raster is only as wide as the downloaded
  tiles, so a route that would leave the frame cannot be found.
