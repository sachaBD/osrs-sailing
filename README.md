# OSRS Port Tasks

A filterable browser for Sailing port tasks, with an interactive map and a
route builder — and, under `routing/`, the same tasks treated as an
optimisation problem. The web app has no runtime dependencies: it is plain ES
modules, served statically.

Hosted at <https://sachabd.github.io/osrs-sailing/>, rebuilt from `main` by
`.github/workflows/pages.yml`.

    make install    # editable install of the porttasks package + dev tools
    make serve      # http://localhost:8000
    make check      # every test that does not need a browser
    make test       # all of it, including the end-to-end browser run

## Layout

    tables/         hand-edited. The source of truth.
    derived/        computed from tables/. Never edit.
    porttasks/      the Python package: pipeline, tiles, wiki, routing
    web/            what the browser is served, and nothing else
    tests/          pytest; `browser`-marked tests drive a real Chromium
    tools/          one-off scripts that are not part of the package
    docs/           what the routing problem is, and what we found
    out/            generated: chart caches, renders, screenshots. Ignored.

Nothing is found relative to the working directory: `porttasks.paths` names
every file the project reads or writes, anchored to the repo.

## Data

**`tables/` is hand-edited and is the source of truth; `derived/` is
generated and must never be edited.**

| `tables/` | what it is |
| --- | --- |
| `port_tasks.list` | the task table, pasted from the wiki |
| `locations.tsv` | per-port region, oceans, amenities, coordinates |
| `map_config.json` | map tile source and zoom levels |
| `params.tsv` | cost constants for the routing model |
| `transport.tsv` | charter ships and teleports, per port |
| `waypoints.tsv` | hand-placed sea waypoints for narrow straits |
| `boards.tsv` | notice boards as actually seen in game |

| generated | built by |
| --- | --- |
| `derived/port_tasks.{json,csv}` | `make data` |
| `derived/port_distances.json` | `make survey` (committed: rebuilding needs the tiles) |
| `web/js/generated.js` | `make data` |
| `web/tiles/` | `make tiles` (~11MB, so the map works offline) |

`make refresh` re-checks `locations.tsv` and the tile version against the wiki;
it fills blanks and reports differences but never overwrites your edits unless
run with `--apply`.

## The Python package

`porttasks/` holds the data pipeline (tables in, `web/js/generated.js` out),
the wiki refresh, the tile grid, and `routing/`. It has its own README, and so
does `routing/`; the short version is that `world/` is the ground truth,
`problem/` is the search space over it, and `search/` — still to be
written — will decide what to do.

## The web app

    web/index.html      the page
    web/style.css
    web/js/ports.js     reading the generated port tables
    web/js/cost.js      pricing a leg and a route: distance, time, xp/hr
    web/js/course.js    the charted sea route between two ports
    web/js/dom.js       selectors, HTML escaping, safe localStorage
    web/js/state.js     the view's state, URL and storage serialisation
    web/js/filters.js   state -> the rows on screen
    web/js/multiselect.js  the checkbox dropdown widget
    web/js/table.js     results table and CSV export
    web/js/trip.js      route builder: sequencing, pricing and its panel
    web/js/boards.js    what a notice board is worth stopping at
    web/js/map/viewer.js   pan/zoom tile viewer
    web/js/map/overlay.js  markers and routes drawn over the tiles
    web/js/main.js      wiring; the only module that knows all the others

Modules mutate `state` then call `update()`; `main.js` subscribes the renderer.
Going through a subscription rather than importing the renderer keeps the
module graph acyclic.

## Tests

`pytest` runs everything. Tests that need a browser are marked `browser`, so
`make check` (`-m 'not browser'`) is the fast suite and `make test` is all of
it.

    tests/test_pipeline.py    parsing the tables, and the tile grid
    tests/routing/            the simulator
    tests/browser/unit.js     the pure JS logic, run in a real browser
    tests/browser/test_smoke.py   the wiring, end to end

`tests/conftest.py` owns the static server the browser tests point at. It
serves two roots: `web/` for the app, exactly as `make serve` does, and the
repo root only so the JS unit page can import the modules it tests.

## Known limits

Distances in the *web app* are straight lines between ports; `routing/` has the
real ones. Seven tasks have unknown XP and are excluded by any XP filter. The
routing cost constants in `params.tsv` are mostly eyeball guesses — read policy
rankings as findings and absolute xp/hr as provisional.
