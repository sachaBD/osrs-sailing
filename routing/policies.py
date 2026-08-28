"""Baseline policies. Each maps a `Sim` to one legal action.

These exist to floor the problem and to shake out the dynamics: a planner that
cannot beat `greedy_rate` is not batching, and batching is most of the problem.
None of them scout deliberately - they read whatever board they happen to be
standing at.
"""
from __future__ import annotations

import numpy as np

from .instance import NONE
from .sim import ACCEPT, CHARTER, RECALL, SAIL, Sim

Action = np.ndarray


def _pick(actions: np.ndarray, scores: np.ndarray) -> Action:
    return actions[int(np.argmax(scores))]


def _or_wander(errand: Action | None, sim: Sim, actions: np.ndarray) -> Action:
    # an explicit None test: `errand or ...` asks a numpy array for a truth value
    return errand if errand is not None else _wander(sim, actions)


def random_legal(sim: Sim, rng: np.random.Generator | None = None) -> Action:
    actions = sim.legal_actions()
    rng = rng or sim.rng
    return actions[rng.integers(len(actions))]


def _errand(sim: Sim) -> Action | None:
    """Sail toward whatever a held task needs next: a pickup, then a delivery.

    Shared by the greedy policies - they differ only in what they accept, not
    in how they discharge what they hold.
    """
    inst, st = sim.instance, sim.state
    held = st.held[st.held != NONE]
    if not len(held) or st.port_boat != st.port_player:
        return None

    wanted = np.where(st.loaded[st.held != NONE],
                      inst.task_dest[held], inst.task_origin[held])
    wanted = wanted[wanted != st.port_player]
    if not len(wanted):
        return None
    nearest = wanted[int(np.argmin(inst.sail[st.port_player, wanted]))]
    return np.array([SAIL, nearest], np.int32)


def _accepts(sim: Sim) -> tuple[np.ndarray, np.ndarray]:
    actions = sim.legal_actions()
    return actions, actions[actions[:, 0] == ACCEPT]


def greedy_xp(sim: Sim) -> Action:
    """Take the highest-XP task on offer here, otherwise get on with the job."""
    inst = sim.instance
    actions, accepts = _accepts(sim)
    if len(accepts):
        return _pick(accepts, inst.task_xp[accepts[:, 1]])
    return _or_wander(_errand(sim), sim, actions)


def greedy_rate(sim: Sim) -> Action:
    """Take the best XP per tick of the work the task implies, from here."""
    inst, st = sim.instance, sim.state
    actions, accepts = _accepts(sim)
    if len(accepts):
        task = accepts[:, 1]
        # what it costs from here: reach the origin, then run the cargo over
        cost = (inst.sail[st.port_player, inst.task_origin[task]]
                + inst.sail[inst.task_origin[task], inst.task_dest[task]])
        return _pick(accepts, inst.task_xp[task] / np.maximum(cost, 1))
    return _or_wander(_errand(sim), sim, actions)


def scout_then_greedy(sim: Sim) -> Action:
    """Fill every slot before sailing, chartering to unread boards to do it.

    The cheapest thing resembling deliberate scouting: it uses the fact that
    charter moves the player without the boat, so reading a board costs only
    the charter and never strands the cargo.
    """
    inst, st = sim.instance, sim.state
    actions, accepts = _accepts(sim)
    if len(accepts):
        return greedy_rate(sim)

    # only scout with an empty hold: rejoining the boat means recalling it,
    # and a recall destroys whatever cargo is aboard
    if st.free_slots and st.port_boat == st.port_player and not st.loaded.any():
        unread = np.flatnonzero(inst.has_board & ~st.seen & (inst.charter != NONE))
        if len(unread):
            nearest = unread[int(np.argmin(inst.charter[unread]))]
            return np.array([CHARTER, nearest], np.int32)

    if st.port_boat != st.port_player:
        recall = actions[actions[:, 0] == RECALL]
        if len(recall):
            return recall[0]
        return _pick(actions[actions[:, 0] == CHARTER],
                     -inst.charter[actions[actions[:, 0] == CHARTER][:, 1]])
    return _or_wander(_errand(sim), sim, actions)


def _wander(sim: Sim, actions: np.ndarray) -> Action:
    """Nothing to do here: go to the nearest board we have not read."""
    inst, st = sim.instance, sim.state
    sails = actions[actions[:, 0] == SAIL]
    if not len(sails):
        return actions[0]
    port = sails[:, 1]
    cost = inst.sail[st.port_player, port].astype(float)
    cost[~(inst.has_board[port] & ~st.seen[port])] += 10_000  # prefer unread boards
    return _pick(sails, -cost)


ALL = {
    'random': random_legal,
    'greedy_xp': greedy_xp,
    'greedy_rate': greedy_rate,
    'scout_then_greedy': scout_then_greedy,
}
