"""The port-to-port distance matrix: what the route search actually plans over.

Distances come from the shortest path over open water, not over the lattice,
so the lattice's remaining slack does not leak into any number here.  The
lattice keeps its job of drawing routes and being a compact graph.

That path is then pulled straight.  A grid search can only step in eight
directions, so it renders a heading of, say, 22 degrees as a staircase and
charges for every step of it - up to 8.2% more than sailing the line, and by
an amount that varies with the heading, which would quietly distort one route
option against another.  Pulling the slack out of the path removes that: each
point is dropped whenever the ship can see past it to a later one.

Ports are the only decision points in the routing problem: there is nothing to
do in the middle of the ocean, and anywhere worth stopping is already a port.
So once this matrix exists the sea chart has done its work, and what is left
is combinatorial over 30 nodes.

    python3 -m porttasks.routing.world.survey.measure
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import csgraph

from porttasks.paths import MATRIX
from porttasks.paths import PORT_ROUTES as ROUTES
from porttasks.routing.errors import SurveyError

from ..catalogue import Catalogue
from ..distances import Distances
from ..routes import Routes
from . import exact, watermask
from .seagraph import SeaGraph, _clear_line

STRIDE = 8  # path is thinned to this before pulling, in game tiles


def _length(points: list[tuple[int, int]]) -> float:
    array = np.array(points, float)
    return float(np.hypot(*(array[1:] - array[:-1]).T).sum())


def _pull_once(mask: watermask.WaterMask,
               track: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = [track[0]]
    i = 0
    while i < len(track) - 1:
        j = len(track) - 1
        while j > i + 1 and not _clear_line(mask, track[i], track[j]):
            j -= 1
        out.append(track[j])
        i = j
    return out


def pull_straight(mask: watermask.WaterMask, track: list[tuple[int, int]],
                  passes: int = 4) -> list[tuple[int, int]]:
    """Drop every point the ship can see past, leaving the corners it must round.

    One pass is greedy from whichever end it starts, so it settles on a
    different set of corners depending on direction.  Alternating the
    direction and keeping whatever is shorter converges within a few passes
    and takes most of that arbitrariness back out.
    """
    best = _pull_once(mask, track)
    for _ in range(passes):
        candidate = _pull_once(mask, best[::-1])[::-1]
        if _length(candidate) >= _length(best) - 0.01:
            break
        best = candidate
    return best


def build(mask: watermask.WaterMask, graph: SeaGraph
          ) -> tuple[Distances, dict[str, dict[str, list[tuple[int, int]]]]]:
    """-> the matrix, and the water each pair's shortest path actually follows."""
    water, index = exact.water_graph(mask)
    berths = {name: tuple(graph.nodes[i]) for name, i in graph.berths.items()}
    nodes = {name: int(index[rc]) for name, rc in berths.items()}
    stranded = [name for name, node in nodes.items() if node < 0]
    if stranded:
        raise SurveyError(f'berths not on open sea: {stranded}')

    pixels = np.argwhere(index >= 0)
    legs: dict[str, dict[str, float]] = {}
    routes: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for name, source in nodes.items():
        dist, prev = csgraph.dijkstra(water, indices=source, return_predecessors=True)
        legs[name] = {}
        routes[name] = {}
        for other, target in nodes.items():
            if not np.isfinite(dist[target]):
                raise SurveyError(f'no water route {name} -> {other}')
            if other == name:
                legs[name][other] = 0.0
                continue
            track, node = [target], target
            while node != source:
                node = int(prev[node])
                track.append(node)
            track.reverse()
            thinned = track[::STRIDE] + [track[-1]]
            course = pull_straight(mask, [(int(r), int(c)) for r, c in pixels[thinned]])
            legs[name][other] = round(_length(course), 1)
            routes[name][other] = course
    return Distances(legs), routes


def main() -> None:
    mask = watermask.build()
    graph = SeaGraph.load()
    world = Catalogue.load()
    matrix, routes = build(mask, graph)

    ports, table = matrix.as_array()
    # Both directions are real sailable paths, so where they disagree the
    # shorter one is simply the better answer - not something to average.
    asymmetry = float(np.abs(table - table.T).max())
    flip = table.T < table
    table = np.minimum(table, table.T)
    for i, a in enumerate(ports):
        for j, b in enumerate(ports):
            if a != b and flip[i, j]:
                routes[a][b] = routes[b][a][::-1]

    # a shortest-path matrix must obey the triangle inequality; if it does not,
    # something is wrong with the graph rather than with the route search
    worst = 0.0
    for k in range(len(ports)):
        slack = table[:, k, None] + table[None, k, :] - table
        worst = min(worst, float(slack.min()))
    # Pulling is greedy per pair, so A->C can come out slightly longer than
    # A->B->C.  Closing the matrix under the triangle inequality takes that
    # back out, and is sound here because a ship may sail past a port without
    # stopping - the shorter figure is a real distance, not a fiction.
    before = -worst
    for k in range(len(ports)):
        table = np.minimum(table, table[:, k, None] + table[None, k, :])
    for i, a in enumerate(ports):
        for j, b in enumerate(ports):
            matrix.legs[a][b] = round(float(table[i, j]), 1)

    # Closing a symmetric matrix keeps it symmetric, and rounding is symmetric
    # too, so both properties are cheap to assert rather than merely intend.
    ports, table = matrix.as_array()
    residual = float(np.abs(table - table.T).max())
    if residual > 0.0:
        raise SurveyError(f'matrix still asymmetric by {residual:.2f} tiles')
    closed = 0.0
    for k in range(len(ports)):
        closed = min(closed, float((table[:, k, None] + table[None, k, :] - table).min()))
    if closed < -0.05:
        raise SurveyError(f'triangle inequality still violated by {-closed:.2f} tiles')

    matrix.save()
    # The two directions are now the same water sailed backwards, so keep one
    # of each, in game coordinates: the map draws in those, and storing them
    # here means nothing downstream has to carry the mask around to convert.
    courses = {}
    for a, b in ((a, b) for a in ports for b in ports if a < b):
        courses.setdefault(a, {})[b] = [list(mask.to_xy(r, c)) for r, c in routes[a][b]]
    Routes(courses).save(ROUTES)

    off = table[~np.eye(len(ports), dtype=bool)]
    straight = np.array([[float(np.hypot(*np.subtract(world.ports[a].coords,
                                                      world.ports[b].coords)))
                          for b in ports] for a in ports])
    detour = off / straight[~np.eye(len(ports), dtype=bool)]
    print(f'{MATRIX}: {len(ports)} ports, {len(off) // 2} pairs')
    print(f'  symmetrised (worst disagreement {asymmetry:.1f} tiles); '
          f'closed triangle inequality (was off by {before:.0f}); '
          f'symmetry and closure verified')
    print(f'  shortest {off.min():.0f} tiles, longest {off.max():.0f}, median {np.median(off):.0f}')
    print(f'  vs straight lines: median x{np.median(detour):.2f}, worst x{detour.max():.2f}')
    points = sum(len(c) for row in courses.values() for c in row.values())
    print(f'{ROUTES}: {points} corner points over {len(off) // 2} pairs, for drawing')


if __name__ == '__main__':
    main()
