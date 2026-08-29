# porttasks

Everything the project does that is not the page itself. Two jobs:

1. **Keep the data honest** — read the tables you maintain by hand, re-check
   them against the wiki, and fold them into the one file the app reads.
2. **Solve the routing problem** — `routing/`, which has its own README.

## The flow

    tables/port_tasks.list        you edit these, by hand
    tables/locations.tsv
    tables/map_config.json
             |
             |  tasks.py     the wiki copy-paste -> derived/port_tasks.{json,csv}
             |  grid.py      which map tiles cover the ports, and where
             |  generate.py  all of it -> one JS module
             v
    web/js/generated.js           the app's only data source

`routing/` sits alongside this, not downstream of it: it reads the same tables
plus `derived/port_distances.json`, the chart it builds from the map tiles.

## The modules

    paths.py      every file the project reads or writes. Nothing else builds
                  a path, so nothing depends on the working directory.
    tables/       readers for `tables/`: locations.py (the port reference
                  table, read and written) and tasks.py (the pasted task list)
    tiles/        grid.py, the tile-grid maths the map is drawn on;
                  fetch.py, which caches the tiles into web/tiles
    generate.py   folds the tables into web/js/generated.js
    wiki.py       re-checks locations.tsv and the tile version against the
                  OSRS wiki. Fills blanks and reports differences; never
                  overwrites a value you edited unless run with --apply
    routing/      the sea chart and the simulator over it

## Running it

    make data       tasks.py, then generate.py
    make tiles      fetch.py: the map, once (~11MB)
    make refresh    wiki.py
    make sim        routing: walk the simulator in marimo

Anything here also runs as `python3 -m porttasks.<module>`, from any directory.

## Three rules

**`tables/` is the truth.** `derived/`, `web/js/generated.js` and `web/tiles/`
can all be deleted and rebuilt. Nothing reads a value out of them that did not
come from `tables/` first.

**Paths come from `paths.py`.** One file names them all, anchored to the repo,
so moving a directory is a one-line change and no script cares where it was
started from.

**Only `routing/world/survey/` costs anything.** It needs scipy, Pillow and
the 11MB of downloaded tiles. It is a one-off job whose output is committed, so
nothing else — the simulator, the app — pays for that.
