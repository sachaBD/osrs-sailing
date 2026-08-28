"""A sailing graph laid over the ocean: waypoints, legs, and port berths.

A lattice of waypoints is dropped on the open sea and joined wherever the
straight line between two of them stays on water, so a leg never crosses land.
Ports attach to the lattice at a berth: the sea pixel a docked ship sits on.

The lattice is deliberately coarse - it exists so route search has a few
thousand edges to plan over rather than four million pixels.  `clearance`
keeps waypoints off the coastline so legs do not scrape headlands, which is
also why the lattice cannot thread a narrow strait: waypoints.tsv is where
those are filled in by hand.
"""
from __future__ import annotations

import heapq
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import handpoints
from .errors import ChartError
from .watermask import NEIGHBOURS, WaterMask
from .world import World

CACHE = 'routing/cache/sea_graph.json'
SPACING = 32       # game tiles between lattice waypoints
CLEARANCE = 6      # a waypoint must be this far from the nearest land
BERTH_LINKS = 6    # waypoints each port connects to
HAND_REACH = 48    # how far a hand-placed waypoint will look for a neighbour


@dataclass(frozen=True)
class SeaGraph:
    """Waypoints in game coordinates and the legs between them.

    Node ids are lattice indices; ports are keyed by name in `berths`.
    """
    nodes: list[tuple[int, int]]
    edges: dict[int, dict[int, float]]
    berths: dict[str, int]
    # the water each harbour approach actually follows, for drawing and for
    # turning a waypoint route back into a track on the map
    approaches: dict[int, dict[int, list[tuple[int, int]]]]

    @property
    def leg_count(self) -> int:
        return sum(len(v) for v in self.edges.values()) // 2

    def save(self, path: str = CACHE) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump({
                'spacing': SPACING,
                'nodes': self.nodes,
                'edges': {str(k): {str(j): round(d, 2) for j, d in v.items()}
                          for k, v in self.edges.items()},
                'berths': self.berths,
                'approaches': {str(b): {str(w): p for w, p in links.items()}
                               for b, links in self.approaches.items()},
            }, f)

    @classmethod
    def load(cls, path: str = CACHE) -> SeaGraph:
        try:
            with open(path) as f:
                raw = json.load(f)
        except FileNotFoundError as exc:
            raise ChartError(
                f'{path} not found; build it with `python3 -m routing.build_graph`') from exc
        return cls(
            nodes=[tuple(n) for n in raw['nodes']],
            edges={int(k): {int(j): d for j, d in v.items()} for k, v in raw['edges'].items()},
            berths=raw['berths'],
            approaches={int(b): {int(w): [tuple(p) for p in path] for w, path in links.items()}
                        for b, links in raw.get('approaches', {}).items()})


def _clearance(mask: WaterMask) -> np.ndarray:
    """Distance from every sea pixel to the nearest thing that is not sea."""
    return ndimage.distance_transform_edt(mask.sea)


def _clear_line(mask: WaterMask, a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Does the straight line from a to b stay on open sea the whole way?"""
    (r0, c0), (r1, c1) = a, b
    steps = int(max(abs(r1 - r0), abs(c1 - c0)))
    if steps == 0:
        return mask.sea_at(r0, c0)
    for i in range(steps + 1):
        t = i / steps
        if not mask.sea_at(round(r0 + t * (r1 - r0)), round(c0 + t * (c1 - c0))):
            return False
    return True


def _lattice(mask: WaterMask, clearance: np.ndarray, spacing: int,
             min_clearance: int) -> list[tuple[int, int]]:
    height, width = mask.shape
    nodes = []
    for row in range(spacing // 2, height, spacing):
        for col in range(spacing // 2, width, spacing):
            if clearance[row, col] >= min_clearance:
                nodes.append((row, col))
    return nodes


def _berth(mask: WaterMask, x: int, y: int, name: str, limit: int = 60) -> tuple[int, int]:
    """Where a ship sits when docked here: the nearest open-sea pixel.

    Nearest *sea*, not nearest water - several ports front onto a harbour pool
    or river mouth that the colour mask leaves disconnected from the ocean.
    """
    r0, c0 = mask.to_rc(x, y)
    for radius in range(limit):
        ring = [(r0 + dr, c0 + dc)
                for dr in range(-radius, radius + 1)
                for dc in range(-radius, radius + 1)
                if max(abs(dr), abs(dc)) == radius and mask.sea_at(r0 + dr, c0 + dc)]
        if ring:
            return min(ring, key=lambda p: (p[0] - r0) ** 2 + (p[1] - c0) ** 2)
    raise ChartError(f'{name} is more than {limit} tiles from open sea')


def _links_from_berth(mask: WaterMask, berth: tuple[int, int],
                      waypoints: dict[tuple[int, int], int],
                      wanted: int) -> dict[int, tuple[float, list[tuple[int, int]]]]:
    """Reach out from a berth through the water to the nearest waypoints.

    A straight line out of a harbour usually clips the headland that makes it a
    harbour, so the approach is measured by sailing it: an octile Dijkstra over
    sea pixels, stopping once enough waypoints are in hand.
    """
    dist = {berth: 0.0}
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    queue = [(0.0, berth)]
    found: dict[int, tuple[float, list[tuple[int, int]]]] = {}
    while queue and len(found) < wanted:
        d, node = heapq.heappop(queue)
        if d > dist.get(node, float('inf')):
            continue
        if node in waypoints:
            track, step_back = [node], node
            while step_back != berth:
                step_back = prev[step_back]
                track.append(step_back)
            found[waypoints[node]] = (d, track[::-1])
        row, col = node
        for dr, dc in NEIGHBOURS:
            nxt = (row + dr, col + dc)
            if not mask.sea_at(*nxt):
                continue
            step = d + (1.4142135 if dr and dc else 1.0)
            if step < dist.get(nxt, float('inf')):
                dist[nxt] = step
                prev[nxt] = node
                heapq.heappush(queue, (step, nxt))
    return found


def _thin(track: list[tuple[int, int]], stride: int = 4) -> list[tuple[int, int]]:
    """Every few pixels is enough to draw the shape of an approach."""
    return track[::stride] + [track[-1]]


def _components(edges: dict[int, dict[int, float]], count: int) -> list[int]:
    label = [-1] * count
    current = 0
    for start in range(count):
        if label[start] >= 0:
            continue
        stack = [start]
        label[start] = current
        while stack:
            node = stack.pop()
            for other in edges.get(node, ()):
                if label[other] < 0:
                    label[other] = current
                    stack.append(other)
        current += 1
    return label


def build(mask: WaterMask, world: World, spacing: int = SPACING,
          min_clearance: int = CLEARANCE, berth_links: int = BERTH_LINKS) -> SeaGraph:
    clearance = _clearance(mask)
    nodes = _lattice(mask, clearance, spacing, min_clearance)
    generated = len(nodes)

    hand = []
    for x, y, note in handpoints.load():
        row, col = mask.to_rc(x, y)
        if not mask.sea_at(row, col):
            where = f'{x},{y}' + (f' ({note})' if note else '')
            raise ChartError(f'{handpoints.PATH}: waypoint {where} is not on open water')
        hand.append((row, col))
    nodes.extend(hand)

    berths = {}
    for name, port in sorted(world.ports.items()):
        nodes.append(_berth(mask, *port.coords, name))
        berths[name] = len(nodes) - 1

    index = {node: i for i, node in enumerate(nodes)}
    edges: dict[int, dict[int, float]] = {i: {} for i in range(len(nodes))}

    def link(i: int, j: int, length: float | None = None) -> None:
        if length is None:
            (r0, c0), (r1, c1) = nodes[i], nodes[j]
            length = float(np.hypot(r1 - r0, c1 - c0))
        edges[i][j] = edges[j][i] = length

    # lattice legs: to the east, south, and both diagonals, so each pair once
    for i in range(generated):
        row, col = nodes[i]
        for dr, dc in ((0, spacing), (spacing, 0), (spacing, spacing), (spacing, -spacing)):
            j = index.get((row + dr, col + dc))
            if j is not None and j < generated and _clear_line(mask, nodes[i], nodes[j]):
                link(i, j)

    # hand-placed legs: to anything in reach with clear water between, which is
    # how a run of them threads a strait and picks up the lattice at both ends
    hand_ids = range(generated, generated + len(hand))
    for i in hand_ids:
        row, col = nodes[i]
        for j in range(generated + len(hand)):
            if j == i:
                continue
            other_row, other_col = nodes[j]
            if abs(other_row - row) > HAND_REACH or abs(other_col - col) > HAND_REACH:
                continue
            if _clear_line(mask, nodes[i], nodes[j]):
                link(i, j)

    # berth legs: sailed out of the harbour rather than drawn through it
    waypoints = {node: i for i, node in enumerate(nodes) if i not in berths.values()}
    approaches: dict[int, dict[int, list[tuple[int, int]]]] = {}
    for name, berth in berths.items():
        found = _links_from_berth(mask, nodes[berth], waypoints, berth_links)
        if not found:
            raise ChartError(f'{name} cannot reach any waypoint by sea')
        for i, (length, track) in found.items():
            link(berth, i, length)
        approaches[berth] = {i: _thin(track) for i, (_, track) in found.items()}

    # checked only now: a hand waypoint parked in a harbour mouth may have no
    # clear line to another waypoint and still be perfectly reachable by berth
    for i in hand_ids:
        if not edges[i]:
            x, y = mask.to_xy(*nodes[i])
            raise ChartError(f'{handpoints.PATH}: waypoint {x},{y} connects to nothing - '
                             f'no clear water within {HAND_REACH} tiles and no berth reaches it')

    label = _components(edges, len(nodes))
    port_labels = {name: label[i] for name, i in berths.items()}
    if len(set(port_labels.values())) > 1:
        groups: dict[int, list[str]] = {}
        for name, component in port_labels.items():
            groups.setdefault(component, []).append(name)
        raise ChartError('ports fall in separate components: '
                         + ' | '.join(', '.join(sorted(g)) for g in groups.values()))

    # waypoints in a pocket of their own are unreachable; drop them, keeping ids
    main = port_labels[next(iter(port_labels))]
    return SeaGraph(
        nodes=nodes,
        edges={i: v for i, v in edges.items() if label[i] == main and v},
        berths=berths,
        approaches=approaches)
