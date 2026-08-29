"""Read tables/waypoints.tsv, the hand-placed additions to the lattice."""
from __future__ import annotations

from pathlib import Path

from porttasks.paths import WAYPOINTS as PATH
from porttasks.routing.errors import SurveyError

FIELDS = ['x', 'y', 'note']


def load(path: Path | str = PATH) -> list[tuple[int, int, str]]:
    """-> [(x, y, note)] in world coordinates, in file order."""
    try:
        with open(path) as f:
            lines = [ln.rstrip('\n') for ln in f if ln.strip() and not ln.startswith('#')]
    except FileNotFoundError:
        return []
    if not lines:
        return []

    header = lines[0].split('\t')
    if header != FIELDS:
        raise SurveyError(f'unexpected header in {path}\n  found:    {header}\n'
                         f'  expected: {FIELDS}')

    points = []
    for line in lines[1:]:
        cells = (line.split('\t') + ['', '', ''])[:3]
        try:
            x, y = int(cells[0].strip()), int(cells[1].strip())
        except ValueError as exc:
            raise SurveyError(f'{path}: row is not "x<tab>y<tab>note": {line!r}') from exc
        points.append((x, y, cells[2].strip()))
    return points
