"""How far apart the ports are, in game tiles: what the search plans over.

Ports are the only decision points in the routing problem - there is nothing
to do in the middle of the ocean, and anywhere worth stopping is already a
port - so once these distances exist the measuring is done, and what is left
is combinatorial over 30 nodes.

This module only *reads* them. Measuring them off the map is `survey/`, kept
apart so that using the distances costs a JSON read rather than scipy and 11MB
of tiles. `derived/port_distances.json` is committed for exactly that reason.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ...paths import MATRIX
from ..errors import SurveyError


class Distances:
    """Symmetric sailing distances between every pair of ports, in game tiles."""

    def __init__(self, legs: dict[str, dict[str, float]]) -> None:
        self.legs = legs
        self.ports = sorted(legs)

    def between(self, origin: str, destination: str) -> float:
        try:
            return self.legs[origin][destination]
        except KeyError as exc:
            raise SurveyError(f'no charted leg {origin!r} -> {destination!r}') from exc

    def as_array(self) -> tuple[list[str], np.ndarray]:
        return self.ports, np.array([[self.legs[a][b] for b in self.ports] for a in self.ports])

    @classmethod
    def load(cls, path: Path | str = MATRIX) -> Distances:
        try:
            with open(path) as f:
                return cls(json.load(f)['legs'])
        except FileNotFoundError as exc:
            raise SurveyError(
                f'{path} not found; build it with `python3 -m porttasks.routing.world.survey.measure`') from exc

    def save(self, path: Path | str = MATRIX) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump({'units': 'game tiles', 'source': 'pixel-exact over the water mask',
                       'legs': self.legs}, f, indent=1, sort_keys=True)
