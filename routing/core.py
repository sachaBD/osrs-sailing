"""The search's inner loop, in plain Python scalars.

`sim.py` is the definition of the dynamics and stays in numpy, which is right
for a definition and for the static tables. It is the wrong tool inside a tree
search: the per-node state here is three held tasks and two port indices, and
at that size numpy's call overhead swamps the arithmetic by more than an order
of magnitude.

So this is the same dynamics again over ints and tuples. Two implementations
of one thing is a real cost, paid deliberately and guarded by a test that
walks both and asserts they agree.

A search state is `(player, boat, held, seen, k)` where `held` is a sorted
tuple of `(task, loaded)` and `seen` is a bitmask of boards read. Immutable
throughout, so states are hashable and nothing needs copying.
"""
from __future__ import annotations

from dataclasses import dataclass

from .instance import NONE, Instance

Held = tuple[tuple[int, bool], ...]
# player, boat, held, boards read (bitmask), completions, tasks finished (bitmask)
SearchState = tuple[int, int, Held, int, int, int]


@dataclass(frozen=True)
class Core:
    """An `Instance` flattened to Python scalars, plus one determinisation."""
    n_ports: int
    capacity: int
    reroll: int
    sail: tuple[tuple[int, ...], ...]
    charter: tuple[int, ...]
    recall: tuple[int, ...]
    has_board: tuple[bool, ...]
    origin: tuple[int, ...]
    dest: tuple[int, ...]
    board_of: tuple[int, ...]
    xp: tuple[int, ...]
    offers: tuple[tuple[int, ...], ...]   # what each board holds, if visited
    t_board: int
    t_drop: int
    to_board: tuple[int, ...] = ()   # ticks from each port to its nearest board

    @classmethod
    def build(cls, instance: Instance, offers: tuple[tuple[int, ...], ...]) -> Core:
        params = instance.params
        sail = tuple(tuple(int(v) for v in row) for row in instance.sail)  # t_dock is in it
        return cls(
            n_ports=instance.n_ports, capacity=instance.capacity,
            reroll=params.reroll_completions,
            sail=sail,
            charter=tuple(int(v) for v in instance.charter),
            recall=tuple(int(v) for v in instance.recall),
            has_board=tuple(bool(v) for v in instance.has_board),
            origin=tuple(int(v) for v in instance.task_origin),
            board_of=tuple(int(v) for v in instance.task_board),
            dest=tuple(int(v) for v in instance.task_dest),
            xp=tuple(int(v) for v in instance.task_xp),
            offers=offers, t_board=params.t_board, t_drop=params.t_drop,
            to_board=tuple(min((sail[p][q] for q in range(instance.n_ports)
                                if q != p and instance.has_board[q]), default=0)
                           for p in range(instance.n_ports)))

    # ---- dynamics -------------------------------------------------------

    def settle(self, state: SearchState) -> tuple[SearchState, int]:
        """Load, deliver, reroll, reveal. Returns the new state and XP won."""
        player, boat, held, seen, k, gone = state
        gained = 0
        if boat == player and held:
            kept: list[tuple[int, bool]] = []
            for task, loaded in held:
                if not loaded and self.origin[task] == player:
                    loaded = True
                if loaded and self.dest[task] == player:
                    gained += self.xp[task]
                    k += 1
                    if k >= self.reroll:
                        k, seen, gone = 0, 0, 0   # every board redraws at once
                else:
                    kept.append((task, loaded))
            held = tuple(sorted(kept))
        if self.has_board[player]:
            seen |= 1 << player
        return (player, boat, held, seen, k, gone), gained

    def moves(self, state: SearchState, explore: bool) -> list[tuple[int, int]]:
        """Legal moves worth trying, cheapest first. Kinds match sim.py."""
        player, boat, held, seen, _, gone = state
        taken = {task for task, _ in held}
        out: list[tuple[int, int]] = []

        def live(port: int) -> tuple[int, ...]:
            return tuple(t for t in self.offers[port] if not gone >> t & 1)

        if len(held) < self.capacity and seen >> player & 1:
            out += [(0, t) for t in live(player) if t not in taken]

        # only sail somewhere that has cargo to drop, work to pick up, or news
        useful = {self.dest[t] if loaded else self.origin[t] for t, loaded in held}
        if len(held) < self.capacity:
            useful |= {p for p in range(self.n_ports)
                       if self.has_board[p] and not seen >> p & 1}
            useful |= {self.origin[t] for t in (live(player) if seen >> player & 1 else ())
                       if t not in taken}
        useful.discard(player)
        if boat == player:
            out += sorted(((2, p) for p in useful), key=lambda m: self.sail[player][m[1]])

        if explore:
            # Chartering never touches the boat, so cargo is no reason not to
            # go and look: you read a board, accept, and charter back to the
            # hull. Only recall destroys cargo, so only recall is gated on it.
            if len(held) < self.capacity:
                out += [(3, p) for p in range(self.n_ports)
                        if self.charter[p] != NONE and p != player
                        and self.has_board[p] and not seen >> p & 1]
            if boat != player:
                if self.recall[player] != NONE and not any(l for _, l in held):
                    out.append((4, 0))
                if self.charter[boat] != NONE:
                    out.append((3, boat))
        return out

    def apply(self, state: SearchState, move: tuple[int, int]) -> tuple[SearchState, int, int]:
        """-> new state, XP won, ticks spent."""
        player, boat, held, seen, k, gone = state
        kind, arg = move
        if kind == 0:
            held, cost = tuple(sorted(held + ((arg, False),))), self.t_board
        elif kind == 1:
            held = tuple((t, l) for t, l in held if t != arg)
            cost = self.t_drop
        elif kind == 2:
            cost = self.sail[player][arg]
            player = boat = arg
        elif kind == 3:
            cost = self.charter[arg]
            player = arg
        else:
            cost = self.recall[player]
            boat = player
            held = tuple((t, False) for t, l in held)
        state, gained = self.settle((player, boat, held, seen, k, gone))
        return state, gained, cost
