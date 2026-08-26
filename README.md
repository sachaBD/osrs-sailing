# OSRS Port Tasks

A filterable browser for Sailing port tasks, with an interactive map and a route
builder. No runtime dependencies: the app is plain ES modules, served statically.

    make serve      # http://localhost:8000
    make test       # unit tests + end-to-end browser run

## Data

Two hand-editable files are the source of truth. Everything else is generated.

| file | what it is |
| --- | --- |
| `port_tasks.list` | the task table, pasted from the wiki |
| `locations.tsv` | per-port region, oceans, amenities, coordinates |
| `map_config.json` | map tile source and zoom levels |

`make data` folds them into `src/generated.js`. `make refresh` re-checks
`locations.tsv` and the tile version against the wiki; it fills blanks and
reports differences but never overwrites your edits unless run with `--apply`.
`make tiles` caches the map tiles locally (~11MB) so the map works offline.

## Layout

    src/ports.js        reading the generated port tables
    src/geometry.js     straight-line distance helpers
    src/dom.js          selectors, HTML escaping, safe localStorage
    src/state.js        the view's state, URL and storage serialisation
    src/filters.js      state -> the rows on screen
    src/multiselect.js  the checkbox dropdown widget
    src/table.js        results table and CSV export
    src/trip.js         route builder: sequencing and its panel
    src/map/viewer.js   pan/zoom tile viewer
    src/map/overlay.js  markers and routes drawn over the tiles
    src/main.js         wiring; the only module that knows all the others

Modules mutate `state` then call `update()`; `main.js` subscribes the renderer.
Going through a subscription rather than importing the renderer keeps the module
graph acyclic.

## Tests

`test_pipeline.py` covers the Python data pipeline. `tests/unit.js` covers the
pure JS logic and runs in a real browser via `js_test.py`. `smoke_test.py`
drives the page end to end: every filter must change the row count, state must
survive a reload through the URL, the map must render and pan, and trips must
sequence legally.

## Known limits

Distances are straight lines between ports. Real sailing goes around land, so
the tiles-sailed figure and the "sailing past" list compare options rather than
predict travel. Seven tasks have unknown XP and are excluded by any XP filter.
