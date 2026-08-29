"""The water each charted leg actually follows, for drawing it on a map.

`distances.py` says how far apart two ports are; this says which way round the
coast that number goes.  Nothing in the search needs it - a route's cost is
its length - so it is kept apart from the matrix and read only by things that
draw.

Stored in game coordinates, one direction per pair (`a < b`), because the two
directions are the same water sailed backwards.  The points are the corners a
ship must round, not a dense track: `survey.measure` pulls each path taut
against the water mask, so a straight run across open sea is two points.

A caveat the drawings inherit: these are the *direct* paths, measured before
the matrix was closed under the triangle inequality.  For 99 of the 435 pairs
the matrix is up to 2.4% shorter than the line drawn here, because it is
allowed to route through a third port and this is not.
"""
from __future__ import annotations

import json
from pathlib import Path

from ...paths import PORT_ROUTES
from ..errors import SurveyError

Point = tuple[int, int]


class Routes:
    """Sailing paths between ports, in game (x, y), as corner points."""

    def __init__(self, legs: dict[str, dict[str, list[Point]]]) -> None:
        self.legs = legs

    @staticmethod
    def _key(origin: str, destination: str) -> tuple[str, str, bool]:
        """-> the stored pair, plus whether the caller wants it reversed."""
        return (origin, destination, False) if origin < destination \
            else (destination, origin, True)

    def between(self, origin: str, destination: str) -> list[Point]:
        """The path from origin to destination, oriented that way round."""
        a, b, flip = self._key(origin, destination)
        try:
            course = self.legs[a][b]
        except KeyError as exc:
            raise SurveyError(f'no charted course {origin!r} -> {destination!r}') from exc
        return [tuple(p) for p in (reversed(course) if flip else course)]

    def pairs(self) -> list[tuple[str, str, list[Point]]]:
        """Every stored pair once, as (a, b, course)."""
        return [(a, b, [tuple(p) for p in course])
                for a, row in sorted(self.legs.items()) for b, course in sorted(row.items())]

    @classmethod
    def load(cls, path: Path | str = PORT_ROUTES) -> Routes:
        try:
            with open(path) as f:
                return cls(json.load(f)['legs'])
        except FileNotFoundError as exc:
            raise SurveyError(f'{path} not found; build it with '
                              '`python3 -m porttasks.routing.world.survey.measure`') from exc

    def save(self, path: Path | str = PORT_ROUTES) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump({'units': 'game tiles', 'source': 'shortest path over the water mask, '
                       'pulled taut; one direction per pair', 'legs': self.legs},
                      f, sort_keys=True, separators=(',', ':'))
