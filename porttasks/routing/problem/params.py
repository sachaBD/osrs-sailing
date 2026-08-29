"""Read tables/params.tsv and tables/transport.tsv."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...paths import PARAMS, TRANSPORT
from ..errors import ProblemError

TICK = 0.6  # seconds; the game's own quantum, so all durations are integers


def _rows(path: Path | str, fields: list[str]) -> list[dict[str, str]]:
    with open(path) as f:
        lines = [ln.rstrip('\n') for ln in f if ln.strip() and not ln.startswith('#')]
    if not lines:
        raise ProblemError(f'{path} has no rows')
    header = lines[0].split('\t')
    if header[:len(fields)] != fields:
        raise ProblemError(f'unexpected header in {path}\n  found:    {header}\n'
                         f'  expected: {fields}')
    out = []
    for line in lines[1:]:
        cells = (line.split('\t') + [''] * len(header))[:len(header)]
        out.append(dict(zip(header, (c.strip() for c in cells))))
    return out


@dataclass(frozen=True)
class Params:
    """Scalar costs, in ticks, plus the capacity ladder.

    `t_dock` and `t_cargo` are both charged on arriving at a port: the first
    for handling the boat, the second for moving the cargo. They are separate
    because only one of them has been measured.

    Every field except `capacity` and `courier_per_board` is a duration; see
    params.tsv for which of them anyone has actually measured.
    """
    sail_speed: float          # game tiles per tick
    courier_per_board: int
    reroll_completions: int
    t_dock: int
    t_cargo: int
    t_board: int
    t_drop: int
    t_charter: int
    t_recall: int
    capacity: tuple[tuple[int, int], ...]  # (level, tasks), ascending

    def capacity_at(self, level: int) -> int:
        held = 0
        for threshold, tasks in self.capacity:
            if level >= threshold:
                held = tasks
        if not held:
            raise ProblemError(f'no task capacity defined at level {level}')
        return held

    @classmethod
    def load(cls, path: Path | str = PARAMS) -> Params:
        raw = {r['name']: r['value'] for r in _rows(path, ['name', 'value', 'unit', 'source'])}
        ladder = tuple(sorted((int(k.removeprefix('capacity_at_')), int(v))
                              for k, v in raw.items() if k.startswith('capacity_at_')))
        if not ladder:
            raise ProblemError(f'{path} defines no capacity_at_* rows')

        def ticks(name: str) -> int:
            value = raw.get(name, '?')
            if value == '?':
                raise ProblemError(f'{path}: {name} is still unmeasured; give it a placeholder')
            return int(value)

        return cls(
            sail_speed=float(raw['sail_speed']),
            courier_per_board=int(raw['courier_per_board']),
            reroll_completions=int(raw['reroll_completions']),
            t_dock=ticks('t_dock'), t_cargo=ticks('t_cargo'),
            t_board=ticks('t_board'), t_drop=ticks('t_drop'),
            t_charter=ticks('t_charter'), t_recall=ticks('t_recall'),
            capacity=ladder)


def charter_ports(path: Path | str = TRANSPORT) -> set[str]:
    """Ports a charter ship serves, so the player can reach them without the boat."""
    fields = ['port', 'charter', 'charter_req', 'teleport']
    return {r['port'] for r in _rows(path, fields) if r['charter'] == 'y'}
