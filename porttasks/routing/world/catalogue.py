"""Ports and tasks, loaded from the repo's hand-edited source files.

This is the read-only substrate every other module sits on: it knows what
exists, not what it costs or what order to do it in.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property

from ...tables import locations, tasks
from ..errors import CatalogueError

# Sailing XP needed for each level, from the standard OSRS experience table.
_XP_TABLE: list[int] = [0]
_points = 0
for _lvl in range(1, 99):
    _points += int(_lvl + 300 * 2 ** (_lvl / 7))
    _XP_TABLE.append(_points // 4)


def level_at(xp: int) -> int:
    """Sailing level for a total XP, capped at 99."""
    if xp < 0:
        raise CatalogueError(f'negative xp: {xp}')
    level = 1
    while level < 99 and xp >= _XP_TABLE[level]:
        level += 1
    return level


def xp_for_level(level: int) -> int:
    if not 1 <= level <= 99:
        raise CatalogueError(f'level out of range: {level}')
    return _XP_TABLE[level - 1]


@dataclass(frozen=True)
class Port:
    name: str
    region: str
    oceans: tuple[str, ...]
    dock_level: int
    shipwright: bool
    notice_board: bool
    coords: tuple[int, int]


@dataclass(frozen=True)
class Task:
    id: int
    level: int
    xp: int | None
    board: str
    origin: str
    destination: str
    cargo: str
    qty: int

    @property
    def direction(self) -> str:
        return 'outbound' if self.board == self.origin else 'inbound'


@dataclass(frozen=True)
class Catalogue:
    ports: dict[str, Port]
    tasks: dict[int, Task]

    @classmethod
    def load(cls, tasks_path: str = tasks.JSON_OUT,
             locations_path: str = locations.PATH) -> Catalogue:
        ports = {}
        for name, record in locations.load(locations_path).items():
            if not record.get('coords'):
                raise CatalogueError(f'{name} has no coords; the sea chart needs them')
            x, y = (int(v) for v in str(record['coords']).split(','))
            ports[name] = Port(
                name=name,
                region=str(record['region']),
                oceans=tuple(record['oceans']),  # type: ignore[arg-type]
                dock_level=int(str(record['dock_level']) or 0),
                shipwright=record['shipwright'] == 'yes',
                notice_board=record['notice_board'] == 'yes',
                coords=(x, y),
            )

        with open(tasks_path) as f:
            rows = json.load(f)
        tasks = {}
        for row in rows:
            for key in ('noticeBoard', 'from', 'to'):
                if row[key] not in ports:
                    raise CatalogueError(f'task {row["id"]} names unknown port {row[key]!r}')
            tasks[row['id']] = Task(
                id=row['id'], level=row['level'], xp=row['xp'], board=row['noticeBoard'],
                origin=row['from'], destination=row['to'], cargo=row['cargo'], qty=row['qty'])
        return cls(ports=ports, tasks=tasks)

    @cached_property
    def boards(self) -> tuple[str, ...]:
        """Ports that advertise tasks, in a fixed order."""
        return tuple(sorted(p.name for p in self.ports.values() if p.notice_board))

    @cached_property
    def tasks_by_board(self) -> dict[str, tuple[Task, ...]]:
        out: dict[str, list[Task]] = {name: [] for name in self.ports}
        for task in self.tasks.values():
            out[task.board].append(task)
        return {name: tuple(sorted(ts, key=lambda t: t.id)) for name, ts in out.items()}

    def dockable(self, level: int) -> frozenset[str]:
        return frozenset(p.name for p in self.ports.values() if p.dock_level <= level)

    def is_doable(self, task: Task, level: int) -> bool:
        """A task needs the level itself and the ability to dock at both ends."""
        return (task.level <= level
                and self.ports[task.origin].dock_level <= level
                and self.ports[task.destination].dock_level <= level)
