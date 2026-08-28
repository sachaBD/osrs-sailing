"""The port-task SMDP, over arrays.

Implements `PROBLEM.md`. Everything is an integer index into an `Instance`;
no names, no dicts, no lookups by string. Actions are `(kind, arg)` pairs so a
whole legal set is one `(n, 2)` array.

The simulator holds the true offers and reveals them only where the player has
been since the last reroll, which is the entire partial observability of the
problem. A policy must read `seen` and `offers`, never `_true_offers`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .errors import ModelError
from .instance import NONE, Instance

ACCEPT, ABANDON, SAIL, CHARTER, RECALL = range(5)
KIND_NAMES = ('accept', 'abandon', 'sail', 'charter', 'recall')


@dataclass
class State:
    """Everything that changes. Slot arrays are capacity-length, NONE-padded."""
    port_player: int
    port_boat: int
    held: np.ndarray        # (C,) int32 task ids
    loaded: np.ndarray      # (C,) bool
    offers: np.ndarray      # (P, K) int32, NONE where unread or not a board
    seen: np.ndarray        # (P,) bool, reset by a reroll
    completions: int = 0    # k, toward the reroll
    xp: int = 0
    ticks: int = 0

    def copy(self) -> State:
        return State(self.port_player, self.port_boat, self.held.copy(), self.loaded.copy(),
                     self.offers.copy(), self.seen.copy(), self.completions, self.xp, self.ticks)

    @property
    def free_slots(self) -> int:
        return int((self.held == NONE).sum())


@dataclass
class Sim:
    """One episode. `step` returns the XP and the ticks that the action cost."""
    instance: Instance
    rng: np.random.Generator = field(default_factory=np.random.default_rng)
    state: State = field(init=False)
    _true_offers: np.ndarray = field(init=False)

    def reset(self, start_port: int = 0) -> State:
        inst = self.instance
        capacity = inst.capacity
        self.state = State(
            port_player=start_port, port_boat=start_port,
            held=np.full(capacity, NONE, np.int32), loaded=np.zeros(capacity, bool),
            offers=np.full((inst.n_ports, inst.params.courier_per_board), NONE, np.int32),
            seen=np.zeros(inst.n_ports, bool))
        self._true_offers = np.full_like(self.state.offers, NONE)
        self._reroll()
        self._settle()
        return self.state

    # ---- dynamics -------------------------------------------------------

    def _reroll(self) -> None:
        """Redraw every board from its own pool. All observations go stale."""
        inst = self.instance
        offers = np.full_like(self._true_offers, NONE)
        for port in np.flatnonzero(inst.has_board):
            pool = inst.board_pool(port)
            offers[port] = self.rng.choice(pool, size=inst.params.courier_per_board,
                                           replace=False)
        self._true_offers = offers
        self.state.seen[:] = False
        self.state.offers[:] = NONE
        self.state.completions = 0

    def _settle(self) -> None:
        """Load, deliver, reroll and reveal - in that order. Not an action."""
        inst, st = self.instance, self.state
        port = st.port_player

        if st.port_boat == port:
            filled = st.held != NONE
            st.loaded |= filled & (inst.task_origin[st.held] == port)

            arriving = np.flatnonzero(filled & st.loaded & (inst.task_dest[st.held] == port))
            for slot in arriving:
                st.xp += int(inst.task_xp[st.held[slot]])
                st.held[slot] = NONE
                st.loaded[slot] = False
                st.completions += 1
                if st.completions >= inst.params.reroll_completions:
                    self._reroll()

        # reveal last, so a delivery that triggered a reroll shows the new board
        if inst.has_board[port]:
            st.seen[port] = True
            st.offers[port] = self._true_offers[port]

    # ---- actions --------------------------------------------------------

    def legal_actions(self) -> np.ndarray:
        """-> (n, 2) int32 of (kind, arg). Never empty: charter always exists."""
        inst, st = self.instance, self.state
        here = st.port_player
        out: list[tuple[int, int]] = []

        if st.free_slots:
            offered = st.offers[here]
            usable = offered[(offered != NONE) & inst.task_eligible[offered]]
            out += [(ACCEPT, int(t)) for t in usable if not (st.held == t).any()]

        out += [(ABANDON, int(t)) for t in st.held[st.held != NONE]]

        if st.port_boat == here:
            out += [(SAIL, p) for p in range(inst.n_ports) if p != here]

        out += [(CHARTER, p) for p in np.flatnonzero(inst.charter != NONE) if p != here]

        if inst.recall[here] != NONE and st.port_boat != here:
            out.append((RECALL, 0))

        return np.array(out, np.int32).reshape(-1, 2)

    def step(self, action: tuple[int, int] | np.ndarray) -> tuple[int, int]:
        kind, arg = int(action[0]), int(action[1])
        legal = self.legal_actions()
        if not ((legal[:, 0] == kind) & (legal[:, 1] == arg)).any():
            raise ModelError(f'illegal action {KIND_NAMES[kind]}({arg}) '
                             f'at port {self.state.port_player}')
        return self.step_unchecked(action)

    def step_unchecked(self, action: tuple[int, int] | np.ndarray) -> tuple[int, int]:
        """`step` without re-deriving the legal set, for search.

        Only safe with an action that came from `legal_actions` on this same
        state; anything else corrupts the state silently rather than raising.
        """
        inst, st = self.instance, self.state
        kind, arg = int(action[0]), int(action[1])
        before_xp = st.xp
        if kind == ACCEPT:
            st.held[np.flatnonzero(st.held == NONE)[0]] = arg
            cost = inst.params.t_board
        elif kind == ABANDON:
            slot = int(np.flatnonzero(st.held == arg)[0])
            st.held[slot], st.loaded[slot] = NONE, False
            cost = inst.params.t_drop
        elif kind == SAIL:
            cost = int(inst.sail[st.port_player, arg])
            st.port_player = st.port_boat = arg
        elif kind == CHARTER:
            cost = int(inst.charter[arg])
            st.port_player = arg
        else:
            cost = int(inst.recall[st.port_player])
            st.port_boat = st.port_player
            st.loaded[:] = False  # cargo is destroyed; the tasks survive

        st.ticks += cost
        self._settle()
        return st.xp - before_xp, cost

    def clone(self, offers: str = 'blind',
              rng: np.random.Generator | None = None) -> Sim:
        """A detached copy, for search to play forward without consequence.

        Search steps clones, so it can never disagree with the real dynamics -
        there is only one implementation of them. What it may *see* is the
        choice here, and it is the whole difference between the layers:

        `blind`   unread boards hold nothing, so sailing to one reveals
                  nothing. Plans only over what the agent has actually read.
        `sample`  unread boards are drawn from their own pools. One guess at
                  the world, which is how the explorer prices going to look.
        `oracle`  the real offers everywhere. Not playable; a ceiling.
        """
        twin = Sim(self.instance, self.rng)
        twin.state = self.state.copy()
        if offers == 'oracle':
            twin._true_offers = self._true_offers
            return twin

        twin._true_offers = self._true_offers.copy()
        unread = ~self.state.seen
        if offers == 'blind':
            twin._true_offers[unread] = NONE
        elif offers == 'sample':
            draw = rng or self.rng
            inst = self.instance
            for port in np.flatnonzero(unread & inst.has_board):
                twin._true_offers[port] = draw.choice(
                    inst.board_pool(port), size=inst.params.courier_per_board, replace=False)
        else:
            raise ModelError(f'unknown offer view {offers!r}')
        return twin

    def run(self, policy, horizon: int) -> State:
        """Drive `policy(sim) -> action` until `horizon` ticks have passed."""
        while self.state.ticks < horizon:
            self.step(policy(self))
        return self.state
