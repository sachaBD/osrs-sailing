"""Pixel-exact sailing distances, straight off the water mask.

The lattice is an approximation built for search; this is the thing it is an
approximation *of*.  Every sea pixel is a node and its eight neighbours are
edges, so a shortest path here is the best a ship could possibly do given the
mask.  Too big to search over task orderings with, but the right yardstick for
checking that the lattice has not sent a route the long way round.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph

from .watermask import WaterMask

_STEPS = ((-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
          (-1, -1, 1.4142135), (-1, 1, 1.4142135), (1, -1, 1.4142135), (1, 1, 1.4142135))


def water_graph(mask: WaterMask) -> tuple[sparse.csr_matrix, np.ndarray]:
    """The open sea as a sparse pixel graph, plus pixel index -> node id."""
    height, width = mask.shape
    index = np.full((height, width), -1, np.int32)
    index[mask.sea] = np.arange(mask.sea.sum(), dtype=np.int32)

    rows, cols, data = [], [], []
    for dr, dc, step in _STEPS:
        src = index[max(0, -dr):height - max(0, dr), max(0, -dc):width - max(0, dc)]
        dst = index[max(0, dr):height - max(0, -dr), max(0, dc):width - max(0, -dc)]
        both = (src >= 0) & (dst >= 0)
        rows.append(src[both])
        cols.append(dst[both])
        data.append(np.full(both.sum(), step, np.float32))
    size = int(mask.sea.sum())
    graph = sparse.csr_matrix(
        (np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
        shape=(size, size))
    return graph, index


def port_distances(mask: WaterMask, berths: dict[str, tuple[int, int]]
                   ) -> dict[str, dict[str, float]]:
    """Exact port-to-port sailing distance, in game tiles."""
    graph, index = water_graph(mask)
    nodes = {name: int(index[row, col]) for name, (row, col) in berths.items()}
    missing = [name for name, node in nodes.items() if node < 0]
    if missing:
        raise ValueError(f'berths not on open sea: {missing}')

    out = {}
    for name, node in nodes.items():
        dist = csgraph.dijkstra(graph, indices=node, min_only=True)
        out[name] = {other: float(dist[target]) for other, target in nodes.items()}
    return out
