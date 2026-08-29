"""Where the project's files live, anchored to the repo rather than the CWD.

Four directories, and the split between them is the whole rule:

    tables/        hand-edited, the source of truth. Edit these.
    derived/       produced by `make data` and `make survey`. Never edit these.
    web/           what the browser is served. Generated JS and tiles land here.
    out/           generated: caches, renders, screenshots. Never committed.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TABLES = ROOT / 'tables'
DERIVED = ROOT / 'derived'
WEB = ROOT / 'web'
OUT = ROOT / 'out'

# tables - hand-edited
PORT_TASKS = TABLES / 'port_tasks.list'
LOCATIONS = TABLES / 'locations.tsv'
MAP_CONFIG = TABLES / 'map_config.json'
PARAMS = TABLES / 'params.tsv'
TRANSPORT = TABLES / 'transport.tsv'
WAYPOINTS = TABLES / 'waypoints.tsv'
BOARDS = TABLES / 'boards.tsv'

# derived - generated. port_distances.json is committed because rebuilding it
# needs the 11MB tile download; the rest is cheap and is ignored.
TASKS_JSON = DERIVED / 'port_tasks.json'
TASKS_CSV = DERIVED / 'port_tasks.csv'
MATRIX = DERIVED / 'port_distances.json'
PORT_ROUTES = DERIVED / 'port_routes.json'

# web - served to the browser, and generated into
GENERATED_JS = WEB / 'js' / 'generated.js'
TILES = WEB / 'tiles'
TILE_URL_DIR = 'tiles'  # what the page asks for, relative to web/

# out - regenerable output, gitignored
CACHE = OUT / 'cache'
RENDERS = OUT / 'renders'
SHOTS = OUT / 'shots'
SEA_GRAPH = CACHE / 'sea_graph.json'
