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

Plans are only compared once they have made the *same* number of deliveries.
That matters more than it sounds: with rho set near the rate the agent already
achieves, a typical task scores barely above zero, so an "up to N deliveries"
objective makes the empty plan competitive and the planner sits in port. Fixing
the work and choosing the cheapest way to do it removes that degenerate option
and is the honest comparison anyway.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .core import Core, SearchState
from .sim import SAIL, Sim

# xp per tick. 1.5 is roughly the best rate the baselines reach, so the
# planner starts out believing it can do about as well as greedy.
RHO = 1.5


@dataclass
class Plan:
    value: float
    actions: list[tuple[int, int]]


def _view(sim: Sim, offers: str, rng: np.random.Generator) -> Core:
    """Flatten the instance plus one guess at the boards not yet read."""
    inst, state = sim.instance, sim.state
    rows = []
    for port in range(inst.n_ports):
        if not inst.has_board[port]:
            rows.append(())
            continue
        if state.seen[port] or offers == 'oracle':
            drawn = sim._true_offers[port]
        elif offers == 'sample':
            drawn = rng.choice(inst.board_pool(port),
                               size=inst.params.courier_per_board, replace=False)
        else:
            drawn = []
        rows.append(tuple(int(t) for t in drawn
                          if t != -1 and inst.task_eligible[t]))
    return Core.build(inst, tuple(rows))


def _start(sim: Sim) -> SearchState:
    state = sim.state
    held = tuple(sorted((int(t), bool(l)) for t, l in zip(state.held, state.loaded)
                        if t != -1))
    seen = sum(1 << port for port, read in enumerate(state.seen) if read)
    return (int(state.port_player), int(state.port_boat), held, seen, int(state.completions))


def _optimistic(core: Core, state: SearchState, left: int, rho: float) -> float:
    """Upper bound on what the rest can add. Must never undershoot.

    Every board the search could still reach counts, not only those already
    read: under a sampled or oracle view the search can sail somewhere unread
    and collect a prize, and a bound that ignored those would cut the very
    branches that use the extra information. Loose is survivable, low is not.
    """
    player, boat, held, seen, _ = state
    prizes = [core.xp[t] for t, _ in held]
    for port in range(core.n_ports):
        prizes += [core.xp[t] for t in core.offers[port]]
    best = sum(sorted(prizes, reverse=True)[:left])
    travel = min((core.sail[boat][core.dest[t] if l else core.origin[t]]
                  for t, l in held
                  if (core.dest[t] if l else core.origin[t]) != boat), default=0)
    return best - rho * travel


def plan(sim: Sim, rho: float = RHO, deliveries: int = 3, node_budget: int = 20_000,
         offers: str = 'blind', explore: bool = False,
         rng: np.random.Generator | None = None) -> Plan:
    """Best sequence of moves out to `deliveries` completions.

    `offers` picks what the search may see on unread boards - blind, one
    sampled guess, or the truth. `explore` lets it charter and recall, which
    is what makes going to look at a board a move it can weigh rather than
    one it can only stumble into.
    """
    core = _view(sim, offers, rng or np.random.default_rng())
    best = Plan(-np.inf, [])
    partial = Plan(-np.inf, [])
    deepest = -1
    seen: dict[tuple, float] = {}
    budget = node_budget

    def descend(state: SearchState, done: int, gained: int, spent: int,
                trail: list[tuple[int, int]]) -> None:
        nonlocal best, partial, deepest, budget
        value = gained - rho * spent
        if done >= deliveries:
            # Charge for where the plan leaves the ship. Without this a fixed
            # delivery count is myopic in a way better information makes worse:
            # the search reaches further for its two deliveries and strands
            # itself somewhere with nothing to do next.
            value -= rho * core.to_board[state[1]]
            if value > best.value:
                best = Plan(value, list(trail))
            return
        if (done, value) > (deepest, partial.value):
            deepest, partial = done, Plan(value, list(trail))
        if budget <= 0 or value + _optimistic(core, state, deliveries - done, rho) <= best.value:
            return
        key = (state, done)
        if seen.get(key, -1e18) >= value:
            return
        seen[key] = value

        for move in core.moves(state, explore):
            budget -= 1
            if budget <= 0:
                return
            nxt, won, cost = core.apply(state, move)
            trail.append(move)
            descend(nxt, done + (won > 0), gained + won, spent + cost, trail)
            trail.pop()

    start, _ = core.settle(_start(sim))
    descend(start, 0, 0, 0, [])
    return best if best.actions else partial


class Planner:
    """Plans, plays the plan out, and re-plans when what it knows changes.

    Re-planning every step would be honest and far too slow. Nothing can
    invalidate a plan except learning something, so the trigger is a change in
    the set of boards read - which is also exactly when a reroll has happened,
    since a reroll clears them all.

    `scenarios` above one turns it into the explorer: the unread boards are
    guessed at several times over, each guess is planned separately, and the
    first action that looks best across all of them is played. That is what
    lets it decide to go and *look*, which a planner that treats unread boards
    as empty can never have a reason to do.
    """

    def __init__(self, rho: float = RHO, deliveries: int = 3, node_budget: int = 4_000,
                 offers: str = 'blind', explore: bool = False, scenarios: int = 1,
                 seed: int = 0) -> None:
        self.rho = rho
        self.deliveries = deliveries
        self.node_budget = node_budget
        self.offers = offers
        self.explore = explore
        self.scenarios = scenarios
        self.rng = np.random.default_rng(seed)
        self._queued: list[tuple[int, int]] = []
        self._knowledge: bytes = b''
        self.plans = 0

    def _replan(self, sim: Sim) -> list[tuple[int, int]]:
        """Plan each guess separately, then take the move they agree on.

        Not the best-scoring plan across guesses: that picks whichever guess
        was luckiest, so sampling harder makes the agent more credulous rather
        than better informed. Consensus on the first move is the point of
        sampling at all - a move that only pays under one guess loses to one
        that pays under most.
        """
        self.plans += 1
        budget = max(self.node_budget // self.scenarios, 400)
        drafts = [plan(sim, self.rho, self.deliveries, budget,
                       self.offers, self.explore, self.rng)
                  for _ in range(self.scenarios)]
        drafts = [d for d in drafts if d.actions]
        if not drafts:
            return []
        if self.scenarios == 1:
            return drafts[0].actions

        votes: dict[tuple[int, int], list[float]] = {}
        for draft in drafts:
            votes.setdefault(draft.actions[0], []).append(draft.value)
        winner = max(votes, key=lambda move: (len(votes[move]), np.mean(votes[move])))
        # play out the plan that voted for the winner and scored worst under it,
        # so the committed route is one that survives a pessimistic guess
        return min((d for d in drafts if d.actions[0] == winner),
                   key=lambda d: d.value).actions

    def __call__(self, sim: Sim) -> np.ndarray:
        knowledge = sim.state.seen.tobytes()
        if not self._queued or knowledge != self._knowledge:
            self._queued = self._replan(sim)
            self._knowledge = knowledge

        legal = sim.legal_actions()
        if self._queued:
            action = np.array(self._queued[0], np.int32)
            if ((legal[:, 0] == action[0]) & (legal[:, 1] == action[1])).any():
                self._queued.pop(0)
                return action
            # the rest of the plan assumed this step happened, so it is now
            # meaningless: drop the whole thing rather than skip a step of it
            self._queued.clear()
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


def planner(rho: float = RHO, deliveries: int = 2, node_budget: int = 3_000) -> Planner:
    """Plans over what it has actually read. Sails; never charters."""
    return Planner(rho, deliveries, node_budget, offers='blind')


def explorer(rho: float = RHO, deliveries: int = 3, node_budget: int = 6_000,
             scenarios: int = 4, seed: int = 0) -> Planner:
    """Guesses at the boards it has not read, and may charter off to look."""
    return Planner(rho, deliveries, node_budget, offers='sample',
                   explore=True, scenarios=scenarios, seed=seed)


def oracle(rho: float = RHO, deliveries: int = 3, node_budget: int = 6_000) -> Planner:
    """The same search, reading every board. Not a policy - a ceiling."""
    return Planner(rho, deliveries, node_budget, offers='oracle', explore=True)
