"""Build the sea graph from the cached tiles and write it to disk."""
from __future__ import annotations

import time

from ..catalogue import Catalogue
from . import seagraph, watermask


def main() -> None:
    start = time.time()
    mask = watermask.build()
    world = Catalogue.load()
    graph = seagraph.build(mask, world)
    graph.save()
    live = len(graph.edges)
    print(f'{seagraph.CACHE}: {live} reachable waypoints of {len(graph.nodes)}, '
          f'{graph.leg_count} legs, {len(graph.berths)} berths, {time.time() - start:.0f}s')


if __name__ == '__main__':
    main()
