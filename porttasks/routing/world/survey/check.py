"""Does the lattice route ships the way the water actually allows?

Compares every port pair's lattice route against the pixel-exact shortest path.
The lattice can only ever be longer, so a big overhead means a strait it could
not thread - and the fix is a few rows in tables/waypoints.tsv.

    python3 -m porttasks.routing.world.survey.check
"""
from __future__ import annotations

import heapq

import numpy as np

from ..catalogue import Catalogue
from . import exact, watermask
from .seagraph import SeaGraph

TOLERANCE = 5.0  # percent over the exact path before a pair is worth reporting


def lattice_distances(graph: SeaGraph) -> dict[str, dict[str, float]]:
    out = {}
    for name, start in graph.berths.items():
        dist = {start: 0.0}
        queue = [(0.0, start)]
        while queue:
            cost, node = heapq.heappop(queue)
            if cost > dist.get(node, float('inf')):
                continue
            for other, length in graph.edges.get(node, {}).items():
                step = cost + length
                if step < dist.get(other, float('inf')):
                    dist[other] = step
                    heapq.heappush(queue, (step, other))
        out[name] = {other: dist.get(berth, float('inf'))
                     for other, berth in graph.berths.items()}
    return out


def main() -> None:
    graph = SeaGraph.load()
    mask = watermask.build()
    world = Catalogue.load()

    berths = {name: tuple(graph.nodes[i]) for name, i in graph.berths.items()}
    true = exact.port_distances(mask, berths)
    lattice = lattice_distances(graph)

    names = sorted(graph.berths)
    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            straight = float(np.hypot(*np.subtract(world.ports[a].coords, world.ports[b].coords)))
            rows.append((a, b, straight, lattice[a][b], true[a][b]))

    over = np.array([(lat / ex - 1) * 100 for *_, lat, ex in rows])
    detour = np.array([ex / st for _, _, st, _, ex in rows])
    print(f'{len(rows)} port pairs\n')
    print(f'lattice over exact:  median +{np.median(over):.1f}%   '
          f'mean +{over.mean():.1f}%   p95 +{np.percentile(over, 95):.1f}%   '
          f'max +{over.max():.1f}%')
    print(f'exact over straight: median x{np.median(detour):.2f}   max x{detour.max():.2f}'
          '   <- how much a straight line lies\n')

    bad = sorted((r for r, o in zip(rows, over) if o > TOLERANCE),
                 key=lambda r: -(r[3] / r[4]))
    if not bad:
        print(f'no pair is more than {TOLERANCE:.0f}% over the exact path.')
        return
    print(f'{len(bad)} pairs over {TOLERANCE:.0f}% - add waypoints between these:')
    for a, b, _, lat, ex in bad[:15]:
        print(f'  {a:22s} {b:22s} lattice {lat:6.0f}  exact {ex:6.0f}  +{(lat / ex - 1) * 100:5.1f}%')


if __name__ == '__main__':
    main()
