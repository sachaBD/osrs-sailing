"""Search over what the agent can see: which tasks to take, and in what order.

The greedy policies commit to one task at a time, so they never discover that
two tasks share a leg. This plans a short sequence instead, which is where the
gain from batching lives.

Scope is deliberately narrow. The planner accepts tasks and sails the boat; it
does not charter, recall or abandon, and it plans only over boards it has
already read. Deciding when to go *looking* for offers is Layer 3.

Objective is `xp - rho * ticks`, the rho-parametrisation from PROBLEM.md: a
plain sum of XP would sail across the map for a big number, and a plain ratio
cannot be summed over a sequence. `rho` is the exchange rate between the two,
in XP per tick, and is the rate the agent believes it can otherwise sustain.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .instance import NONE, Instance
from .sim import ACCEPT, SAIL, Sim

# xp per tick. 1.5 is roughly the best rate the baselines reach, so the
# planner starts out believing it can do about as well as greedy.
RHO = 1.5


@dataclass
class Plan:
    value: float
    actions: list[tuple[int, int]]


def _state_key(sim: Sim) -> tuple:
    state = sim.state
    held = tuple(sorted(zip(state.held.tolist(), state.loaded.tolist())))
    return state.port_player, state.port_boat, held, state.completions


def _optimistic(sim: Sim, deliveries_left: int, rho: float) -> float:
    """An upper bound on what the rest of the plan can add. Must never undershoot.

    XP side: the best `deliveries_left` prizes still reachable, routing ignored.
    Time side: the ship must at least reach the nearest thing it still needs,
    which the metric matrix makes a valid lower bound on remaining travel.
    """
    inst, state = sim.instance, sim.state
    held = state.held[state.held != NONE]

    prizes = list(inst.task_xp[held]) if len(held) else []
    offered = state.offers[state.seen]
    if offered.size:
        live = offered[(offered != NONE) & inst.task_eligible[offered]]
        prizes += list(inst.task_xp[live])
    best_xp = sum(sorted(prizes, reverse=True)[:deliveries_left])

    if len(held):
        wanted = np.where(state.loaded[state.held != NONE],
                          inst.task_dest[held], inst.task_origin[held])
        wanted = wanted[wanted != state.port_boat]
        travel = int(inst.sail[state.port_boat, wanted].min()) if wanted.size else 0
    else:
        travel = 0
    return best_xp - rho * travel


def _worth_trying(sim: Sim) -> list[np.ndarray]:
    """Legal accepts, plus only the sails that could possibly matter.

    Sailing somewhere with no cargo to drop, nothing to pick up and no unread
    board is never part of a good plan, and letting the search consider all
    nine ports at every node is most of its cost. Cheapest moves come first,
    because a good incumbent found early prunes everything after it.
    """
    inst, state = sim.instance, sim.state
    legal = sim.legal_actions()
    accepts = [a for a in legal if a[0] == ACCEPT]

    held = state.held[state.held != NONE]
    useful: set[int] = set()
    if len(held):
        useful.update(np.where(state.loaded[state.held != NONE],
                               inst.task_dest[held], inst.task_origin[held]).tolist())
    if state.free_slots:
        offered = state.offers[state.seen]
        if offered.size:
            live = offered[(offered != NONE) & inst.task_eligible[offered]]
            useful.update(inst.task_origin[live].tolist())
        useful.update(np.flatnonzero(inst.has_board & ~state.seen).tolist())
    useful.discard(state.port_player)

    sails = [a for a in legal if a[0] == SAIL and int(a[1]) in useful]
    sails.sort(key=lambda a: inst.sail[state.port_player, a[1]])
    return accepts + sails


def plan(sim: Sim, rho: float = RHO, deliveries: int = 3,
         node_budget: int = 20_000) -> Plan:
    """Best sequence of accepts and sails, out to `deliveries` completions."""
    inst = sim.instance
    best = Plan(-np.inf, [])
    seen: dict[tuple, float] = {}
    budget = [node_budget]

    def descend(node: Sim, done: int, gained: int, spent: int,
                trail: list[tuple[int, int]]) -> None:
        value = gained - rho * spent
        if value > best.value:
            best.value, best.actions = value, list(trail)
        if done >= deliveries or budget[0] <= 0:
            return
        if value + _optimistic(node, deliveries - done, rho) <= best.value:
            return

        key = (_state_key(node), done)
        if seen.get(key, -np.inf) >= value:
            return
        seen[key] = value

        actions = _worth_trying(node)
        for action in actions:
            budget[0] -= 1
            if budget[0] <= 0:
                return
            child = node.clone()
            xp, cost = child.step_unchecked(action)
            trail.append((int(action[0]), int(action[1])))
            descend(child, done + (xp > 0), gained + xp, spent + cost, trail)
            trail.pop()

    descend(sim.clone(), 0, 0, 0, [])
    return best


class Planner:
    """Plays out a plan, and re-plans only when what it knows has changed.

    Re-planning every step would be honest and far too slow. Nothing can
    invalidate a plan except learning something, so the trigger is a change in
    the set of boards read - which is also exactly when a reroll has happened,
    since a reroll clears them all.
    """

    def __init__(self, rho: float = RHO, deliveries: int = 3,
                 node_budget: int = 4_000) -> None:
        self.rho = rho
        self.deliveries = deliveries
        self.node_budget = node_budget
        self._queued: list[tuple[int, int]] = []
        self._knowledge: bytes = b''
        self.plans = 0

    def __call__(self, sim: Sim) -> np.ndarray:
        knowledge = sim.state.seen.tobytes()
        if not self._queued or knowledge != self._knowledge:
            self._queued = plan(sim, self.rho, self.deliveries, self.node_budget).actions
            self._knowledge = knowledge
            self.plans += 1

        legal = sim.legal_actions()
        while self._queued:
            action = np.array(self._queued.pop(0), np.int32)
            if ((legal[:, 0] == action[0]) & (legal[:, 1] == action[1])).any():
                return action
        return _fallback(sim, legal)


def _fallback(sim: Sim, legal: np.ndarray) -> np.ndarray:
    """Nothing worth doing here: sail to the nearest board not yet read."""
    inst, state = sim.instance, sim.state
    sails = legal[legal[:, 0] == SAIL]
    if not len(sails):
        return legal[0]
    cost = inst.sail[state.port_player, sails[:, 1]].astype(float)
    cost[~(inst.has_board[sails[:, 1]] & ~state.seen[sails[:, 1]])] += 10_000
    return sails[int(np.argmin(cost))]


def planner(rho: float = RHO, deliveries: int = 3, node_budget: int = 4_000) -> Planner:
    return Planner(rho, deliveries, node_budget)
