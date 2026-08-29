"""The port-task SMDP, over arrays.

Implements `docs/PROBLEM.md`. Everything is an integer index into an
`Instance`: no names, no dicts, no lookups by string.

The dynamics are a pure function, `Sim.step(state, action) -> Step`. `State`
is frozen and its arrays are read-only, so a state is a value: cloning it is
free, holding on to one is safe, and search can branch by keeping the parent
around rather than by undoing anything.

The one thing a state does not store is the true content of the boards. It
does not have to: a board's offers are a deterministic draw from `(seed,
epoch)`, so `Sim.true_offers` can rebuild any epoch from two integers. That is
what makes `to_dict` a handful of scalars and short lists. What a *policy* may
read is `Sim.observed(state)`, which is NONE everywhere the player has not
stood since the last reroll - that masking is the whole partial observability
of the problem.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

import numpy as np

from ..errors import ProblemError
from .instance import NONE, Instance

TAKE, SAIL, CHARTER, RECALL = range(4)
KIND_NAMES = ('take', 'sail', 'charter', 'recall')


def _frozen(array: np.ndarray) -> np.ndarray:
    array.flags.writeable = False
    return array


@dataclass(frozen=True, slots=True)
class Action:
    """`kind` plus at most two integer arguments; NONE where one is unused.

    `Take(task, victim)` is the only compound one: `victim` names the held
    task it displaces, or NONE to fill a free slot. Accepting and abandoning
    are deliberately not separate actions - see PROBLEM.md S4.
    """
    kind: int
    arg: int = NONE
    victim: int = NONE

    def as_tuple(self) -> tuple[int, int, int]:
        return self.kind, self.arg, self.victim

    def describe(self, instance: Instance) -> str:
        name = KIND_NAMES[self.kind]
        if self.kind == TAKE:
            swap = '' if self.victim == NONE else f' over {instance.task_names[self.victim]}'
            return f'{name} {instance.task_names[self.arg]}{swap}'
        if self.kind == RECALL:
            return name
        return f'{name} to {instance.port_names[self.arg]}'


@dataclass(frozen=True, slots=True, eq=False)
class State:
    """Everything that changes. Slot arrays are capacity-length, NONE-padded.

    `seed` and `epoch` together name the current draw of every board, so the
    hidden half of the world is reconstructible rather than carried.
    """
    port_player: int
    port_boat: int
    held: np.ndarray        # (C,) int32 task ids, NONE where the slot is free
    loaded: np.ndarray      # (C,) bool, cargo aboard for that task
    seen: np.ndarray        # (P,) bool, boards read this epoch; cleared by a reroll
    seed: int               # names the board draws, with `epoch`
    epoch: int = 0          # rerolls so far
    completions: int = 0    # k, toward the next reroll
    xp: int = 0
    ticks: int = 0

    @property
    def free_slots(self) -> int:
        return int((self.held == NONE).sum())

    def key(self) -> tuple:
        """A hashable summary, for transposition tables and equality.

        Deliberately not `xp` or `ticks`: nothing in the dynamics reads either
        back (PROBLEM.md S3), so two states differing only in them face the
        same decision problem.
        """
        return (self.port_player, self.port_boat, self.held.tobytes(),
                self.loaded.tobytes(), self.seen.tobytes(), self.seed, self.epoch,
                self.completions)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, State) and self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())

    @property
    def tasks(self) -> np.ndarray:
        """The held task ids, without the padding."""
        return self.held[self.held != NONE]

    def clone(self) -> State:
        """A detached copy. States are immutable, so this is never needed."""
        return replace(self, held=_frozen(self.held.copy()),
                       loaded=_frozen(self.loaded.copy()), seen=_frozen(self.seen.copy()))

    def to_dict(self) -> dict:
        return {'port_player': self.port_player, 'port_boat': self.port_boat,
                'held': self.held.tolist(), 'loaded': self.loaded.tolist(),
                'seen': self.seen.tolist(), 'seed': self.seed, 'epoch': self.epoch,
                'completions': self.completions, 'xp': self.xp, 'ticks': self.ticks}

    @classmethod
    def from_dict(cls, raw: dict) -> State:
        return cls(port_player=int(raw['port_player']), port_boat=int(raw['port_boat']),
                   held=_frozen(np.array(raw['held'], np.int32)),
                   loaded=_frozen(np.array(raw['loaded'], bool)),
                   seen=_frozen(np.array(raw['seen'], bool)),
                   seed=int(raw['seed']), epoch=int(raw['epoch']),
                   completions=int(raw['completions']),
                   xp=int(raw['xp']), ticks=int(raw['ticks']))


@dataclass(frozen=True, slots=True)
class Step:
    """What one action did: the state after it, and what it paid for."""
    state: State
    xp: int
    ticks: int


@dataclass(frozen=True, slots=True)
class Sim:
    """The dynamics of one `Instance`. Stateless; every method takes a `State`.

    Held only for the cache of drawn boards, which is a memo of a pure
    function of `(seed, epoch)` and so changes nothing observable.
    """
    instance: Instance
    _draws: dict[tuple[int, int], np.ndarray] = field(default_factory=dict, repr=False)

    # ---- the hidden world ------------------------------------------------

    def true_offers(self, state: State) -> np.ndarray:
        """-> (P, K) int32 of what every board really holds this epoch.

        Not for policies: this is the answer sheet. Read `observed` instead.
        """
        inst = self.instance
        key = (state.seed, state.epoch)
        if key not in self._draws:
            rng = np.random.default_rng(key)
            offers = np.full((inst.n_ports, inst.params.courier_per_board), NONE, np.int32)
            for port in np.flatnonzero(inst.has_board):
                offers[port] = rng.choice(inst.board_pool(port),
                                          size=inst.params.courier_per_board, replace=False)
            self._draws[key] = _frozen(offers)
        return self._draws[key]

    def observed(self, state: State) -> np.ndarray:
        """-> (P, K) int32, the true offers where `seen`, NONE everywhere else."""
        return np.where(state.seen[:, None], self.true_offers(state), NONE).astype(np.int32)

    def sample_offers(self, state: State, rng: np.random.Generator) -> np.ndarray:
        """One guess at the world, consistent with what has been read.

        Boards already seen keep their true content; the rest are redrawn from
        their own pools. This is how a planner prices going to look at a board
        - and it is the same draw the environment makes at a reroll, so the
        planner and the simulator cannot disagree about the prior.
        """
        inst = self.instance
        guess = np.array(self.true_offers(state), np.int32)
        for port in np.flatnonzero(~state.seen & inst.has_board):
            guess[port] = rng.choice(inst.board_pool(port),
                                     size=inst.params.courier_per_board, replace=False)
        return guess

    # ---- dynamics --------------------------------------------------------

    def reset(self, seed: int = 0, start_port: int = 0) -> State:
        inst = self.instance
        state = State(port_player=start_port, port_boat=start_port,
                      held=_frozen(np.full(inst.capacity, NONE, np.int32)),
                      loaded=_frozen(np.zeros(inst.capacity, bool)),
                      seen=_frozen(np.zeros(inst.n_ports, bool)),
                      seed=seed, epoch=0)
        return self._settle(state)[0]

    def _settle(self, state: State) -> tuple[State, int]:
        """Load, deliver, reroll and reveal - in that order. -> (state, xp).

        Not an action: it runs on arrival and after every take, and costs
        nothing. See PROBLEM.md S5.
        """
        inst = self.instance
        port = state.port_player
        held, loaded, seen = state.held.copy(), state.loaded.copy(), state.seen.copy()
        epoch, completions, gained = state.epoch, state.completions, 0

        if state.port_boat == port:
            filled = held != NONE
            loaded |= filled & (inst.task_origin[held] == port)

            for slot in np.flatnonzero(filled & loaded & (inst.task_dest[held] == port)):
                gained += int(inst.task_xp[held[slot]])
                held[slot], loaded[slot] = NONE, False
                # the task stays in its board's pool and may be drawn again;
                # repeating one short profitable route is legal play
                completions += 1
                if completions >= inst.params.reroll_completions:
                    epoch, completions = epoch + 1, 0
                    seen[:] = False  # every board redrawn; all observations stale

        # reveal last, so a delivery that triggered a reroll shows the new board
        if inst.has_board[port]:
            seen[port] = True

        settled = replace(state, held=_frozen(held), loaded=_frozen(loaded), seen=_frozen(seen),
                          epoch=epoch, completions=completions, xp=state.xp + gained)
        return settled, gained

    def legal(self, state: State) -> tuple[Action, ...]:
        """Every action allowed here. Never empty: charter always exists."""
        inst = self.instance
        here = state.port_player
        held = state.tasks
        out: list[Action] = []

        offered = self.observed(state)[here]
        usable = offered[(offered != NONE) & inst.task_eligible[offered]]
        for task in usable:
            if (held == task).any():
                continue
            if state.free_slots:
                out.append(Action(TAKE, int(task)))
            out += [Action(TAKE, int(task), int(victim)) for victim in held]

        if state.port_boat == here:
            out += [Action(SAIL, p) for p in range(inst.n_ports) if p != here]

        out += [Action(CHARTER, int(p)) for p in np.flatnonzero(inst.charter != NONE) if p != here]

        if inst.recall[here] != NONE and state.port_boat != here:
            out.append(Action(RECALL))

        return tuple(out)

    def step(self, state: State, action: Action) -> Step:
        if action not in self.legal(state):
            raise ProblemError(f'illegal action: {action.describe(self.instance)} '
                               f'at {self.instance.port_names[state.port_player]}')
        return self.step_unchecked(state, action)

    def step_unchecked(self, state: State, action: Action) -> Step:
        """`step` without re-deriving the legal set, for search.

        Only safe with an action `legal` returned for this same state; anything
        else corrupts the state silently rather than raising.
        """
        inst = self.instance
        kind, arg, victim = action.as_tuple()

        if kind == TAKE:
            held, loaded = state.held.copy(), state.loaded.copy()
            slot = (np.flatnonzero(held == NONE) if victim == NONE
                    else np.flatnonzero(held == victim))[0]
            held[slot], loaded[slot] = arg, False
            moved = replace(state, held=_frozen(held), loaded=_frozen(loaded))
            cost = inst.params.t_board + (0 if victim == NONE else inst.params.t_drop)
        elif kind == SAIL:
            moved = replace(state, port_player=arg, port_boat=arg)
            cost = int(inst.sail[state.port_player, arg])
        elif kind == CHARTER:
            moved = replace(state, port_player=arg)  # the boat stays behind
            cost = int(inst.charter[arg])
        else:
            moved = replace(state, port_boat=state.port_player,
                            loaded=_frozen(np.zeros_like(state.loaded)))
            cost = int(inst.recall[state.port_player])  # cargo destroyed, tasks survive

        settled, gained = self._settle(replace(moved, ticks=state.ticks + cost))
        return Step(settled, gained, cost)

    def run(self, state: State, policy, horizon: int) -> State:
        """Drive `policy(sim, state) -> Action` until `horizon` ticks have passed."""
        while state.ticks < horizon:
            state = self.step(state, policy(self, state)).state
        return state

    # ---- serialisation ---------------------------------------------------

    def to_dict(self, state: State) -> dict:
        """A sim and a state, as JSON-safe scalars and lists."""
        return {'level': self.instance.level, 'state': state.to_dict()}

    @classmethod
    def from_dict(cls, raw: dict, instance: Instance | None = None) -> tuple[Sim, State]:
        """The inverse. Pass `instance` to reuse one already built at that level."""
        level = int(raw['level'])
        instance = instance or Instance.at_level(level)
        if instance.level != level:
            raise ProblemError(f'instance is level {instance.level}, not {level}')
        return cls(instance), State.from_dict(raw['state'])

    def to_json(self, state: State) -> str:
        return json.dumps(self.to_dict(state))

    @classmethod
    def from_json(cls, text: str, instance: Instance | None = None) -> tuple[Sim, State]:
        return cls.from_dict(json.loads(text), instance)

    # ---- reporting -------------------------------------------------------

    def describe(self, state: State) -> str:
        """The state as text, for notebooks and traces. Reads only what a policy may."""
        inst = self.instance
        boat = ('with you' if state.port_boat == state.port_player
                else f'at {inst.port_names[state.port_boat]}')
        lines = [f'{inst.port_names[state.port_player]}, boat {boat}',
                 f'  t={state.ticks} ticks   xp={state.xp:,}   '
                 f'epoch {state.epoch}, {state.completions}/'
                 f'{inst.params.reroll_completions} to reroll']

        lines.append(f'  held {len(state.tasks)}/{inst.capacity}:')
        for task in state.tasks:
            where = 'aboard' if state.loaded[state.held == task][0] else 'cargo not collected'
            lines.append(f'    {inst.task_names[task]}  {inst.task_xp[task]:,} xp  ({where})')
        if not len(state.tasks):
            lines[-1] += ' none'

        offered = self.observed(state)[state.port_player]
        if inst.has_board[state.port_player]:
            lines.append('  board here:')
            for task in offered[offered != NONE]:
                gate = '' if inst.task_eligible[task] else '  [ineligible]'
                lines.append(f'    {inst.task_names[task]}  {inst.task_xp[task]:,} xp{gate}')
        else:
            lines.append('  board here: none')
        lines.append(f'  boards read this epoch: {int(state.seen.sum())}/'
                     f'{int(inst.has_board.sum())}')
        return '\n'.join(lines)
