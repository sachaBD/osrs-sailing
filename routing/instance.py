"""Names in, arrays out.

Everything downstream of this module works in integers: a port is an index
into 0..n_ports, a task is an index into 0..n_tasks, and every cost is an
int32 tick count in an array. This is the only place that knows a port has a
name, that a level gates anything, or that any of it came off a TSV.

Build one with `Instance.at_level(30)`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import params as params_mod
from .errors import ModelError
from .params import Params
from .portmatrix import PortMatrix
from .world import World

NONE = -1  # the empty slot, used for absent ports, tasks and offers alike


@dataclass(frozen=True)
class Instance:
    """The static problem, as arrays. Nothing here changes during an episode.

    Ragged per-board task pools are held CSR-style: the pool of board `p` is
    `pool[pool_ptr[p]:pool_ptr[p + 1]]`.
    """
    level: int
    params: Params

    # ports
    sail: np.ndarray        # (P, P) int32, ticks, diagonal 0
    charter: np.ndarray     # (P,)   int32, ticks, NONE where no charter ship
    recall: np.ndarray      # (P,)   int32, ticks, NONE where no shipwright
    has_board: np.ndarray   # (P,)   bool

    # tasks
    task_board: np.ndarray     # (T,) int32
    task_origin: np.ndarray    # (T,) int32
    task_dest: np.ndarray      # (T,) int32
    task_xp: np.ndarray        # (T,) int32
    task_eligible: np.ndarray  # (T,) bool - may be accepted at this level

    # per-board pools, CSR
    pool_ptr: np.ndarray    # (P + 1,) int32
    pool: np.ndarray        # (sum,)   int32

    # names, for reporting only - the simulator never reads these
    port_names: tuple[str, ...]
    task_names: tuple[str, ...]

    @property
    def n_ports(self) -> int:
        return len(self.port_names)

    @property
    def n_tasks(self) -> int:
        return len(self.task_names)

    @property
    def capacity(self) -> int:
        return self.params.capacity_at(self.level)

    def board_pool(self, port: int) -> np.ndarray:
        return self.pool[self.pool_ptr[port]:self.pool_ptr[port + 1]]

    @classmethod
    def at_level(cls, level: int, world: World | None = None,
                 matrix: PortMatrix | None = None, params: Params | None = None) -> Instance:
        world = world or World.load()
        matrix = matrix or PortMatrix.load()
        params = params or Params.load()
        charter = params_mod.charter_ports()

        names = tuple(sorted(n for n, p in world.ports.items() if p.dock_level <= level))
        index = {name: i for i, name in enumerate(names)}
        size = len(names)
        if not size:
            raise ModelError(f'no port is dockable at level {level}')

        sail = np.zeros((size, size), np.int32)
        for i, a in enumerate(names):
            for j, b in enumerate(names):
                if i != j:
                    sail[i, j] = round(matrix.between(a, b) / params.sail_speed) + params.t_dock

        charter_ticks = np.full(size, NONE, np.int32)
        recall_ticks = np.full(size, NONE, np.int32)
        has_board = np.zeros(size, bool)
        for name, i in index.items():
            port = world.ports[name]
            has_board[i] = port.notice_board
            if port.shipwright:
                recall_ticks[i] = params.t_recall
            if name in charter:
                charter_ticks[i] = params.t_charter

        # A board offers from its whole pool regardless of level, so tasks that
        # cannot be done still occupy an offer slot. Keeping them is the point:
        # dropping them would quietly inflate how much choice a board gives.
        chosen = [t for t in world.tasks.values() if t.board in index]
        chosen.sort(key=lambda t: t.id)
        task_index = {t.id: i for i, t in enumerate(chosen)}

        def port_or_none(name: str) -> int:
            return index.get(name, NONE)

        board = np.array([index[t.board] for t in chosen], np.int32)
        origin = np.array([port_or_none(t.origin) for t in chosen], np.int32)
        dest = np.array([port_or_none(t.destination) for t in chosen], np.int32)
        xp = np.array([t.xp or 0 for t in chosen], np.int32)
        eligible = np.array([t.level <= level and t.origin in index and t.destination in index
                             and t.xp is not None for t in chosen], bool)

        order = np.argsort(board, kind='stable')
        pool = order.astype(np.int32)
        pool_ptr = np.zeros(size + 1, np.int32)
        np.cumsum(np.bincount(board, minlength=size), out=pool_ptr[1:])

        return cls(
            level=level, params=params,
            sail=sail, charter=charter_ticks, recall=recall_ticks, has_board=has_board,
            task_board=board, task_origin=origin, task_dest=dest, task_xp=xp,
            task_eligible=eligible, pool_ptr=pool_ptr, pool=pool,
            port_names=names,
            task_names=tuple(f'{t.cargo} x{t.qty} {t.origin}->{t.destination}' for t in chosen))

    def describe(self) -> str:
        boards = int(self.has_board.sum())
        live = int(self.task_eligible.sum())
        pools = np.diff(self.pool_ptr)[self.has_board]
        return (f'level {self.level}: {self.n_ports} ports, {boards} boards, '
                f'{self.n_tasks} tasks ({live} eligible), capacity {self.capacity}, '
                f'{self.params.courier_per_board} offers from pools of '
                f'{pools.min()}-{pools.max()}')
