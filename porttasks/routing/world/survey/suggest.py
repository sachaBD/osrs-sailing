"""Trace the water a ship could actually take, as rows for tables/waypoints.tsv.

    python3 -m porttasks.routing.world.survey.suggest Entrana "Musa Point"

check_graph.py says which pairs route the long way round; this says where to
put the waypoints that fix them.  It walks the pixel-exact path between two
ports and samples it, keeping only the points the lattice cannot already see,
so the output is the minimum you need to paste in.
"""
from __future__ import annotations

import sys

import numpy as np
from scipy.sparse import csgraph

from porttasks.routing.errors import SurveyError

from . import exact, watermask
from .seagraph import SeaGraph
from .watermask import WaterMask

STRIDE = 24  # game tiles between sampled waypoints


def path_between(mask: WaterMask, start: tuple[int, int],
                 goal: tuple[int, int]) -> list[tuple[int, int]]:
    graph, index = exact.water_graph(mask)
    src, dst = int(index[start]), int(index[goal])
    if src < 0 or dst < 0:
        raise SurveyError('a berth is not on open water')
    _, predecessors = csgraph.dijkstra(graph, indices=src, return_predecessors=True)
    if predecessors[dst] < 0 and src != dst:
        raise SurveyError('no water path between those ports')

    lookup = np.argwhere(index >= 0)
    track, node = [dst], dst
    while node != src:
        node = int(predecessors[node])
        track.append(node)
    return [tuple(lookup[n]) for n in reversed(track)]


def useful(graph: SeaGraph, track: list[tuple[int, int]],
           stride: int) -> list[tuple[int, int]]:
    """The path, sampled, minus points that just duplicate an existing node.

    Being *visible* from a lattice node is not enough to drop a point: the
    whole failure being fixed is a lattice whose nodes can see the channel but
    cannot chain through it.  So the bar is only that a point is somewhere new.
    """
    known = [graph.nodes[i] for i in graph.edges]
    out = []
    for point in track[stride // 2::stride]:
        if any(abs(n[0] - point[0]) < stride // 2 and abs(n[1] - point[1]) < stride // 2
               for n in known):
            continue
        out.append(point)
    return out


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit('usage: python3 -m porttasks.routing.world.survey.suggest <port> <port>')
    origin, destination = argv
    graph = SeaGraph.load()
    mask = watermask.build()
    for name in (origin, destination):
        if name not in graph.berths:
            raise SystemExit(f'unknown port {name!r}')

    track = path_between(mask, tuple(graph.nodes[graph.berths[origin]]),
                         tuple(graph.nodes[graph.berths[destination]]))
    points = useful(graph, track, STRIDE)
    print(f'# {origin} -> {destination}: {len(track)} tiles of water, '
          f'{len(points)} waypoints')
    for row, col in points:
        x, y = mask.to_xy(row, col)
        print(f'{x}\t{y}\t{origin} - {destination}')


if __name__ == '__main__':
    main(sys.argv[1:])
