"""Policy rollout: the standard baseline this project should have started with.

For each legal action, take it, then let a base policy finish the job, and
score the result. Play whichever action led somewhere best. The base policy
supplies the value estimate that a truncated search otherwise has to invent -
which is exactly what went wrong with the branch and bound in `plan.py`, where
a fixed delivery count and no terminal value let better information make
things worse.

Rollout cannot be worse than its base policy by much and usually beats it, so
it is the honest floor a cleverer search has to clear.
"""
from __future__ import annotations

import numpy as np

from .core import Core, SearchState
from .plan import _start, _view
from .sim import Sim

HORIZON = 400   # ticks simulated per candidate action
TICK = 0.6


def _greedy_move(core: Core, state: SearchState) -> tuple[int, int] | None:
    """The base policy: discharge what you hold, else take the best rate here.

    Deliberately simple. Rollout's job is to be better than this, and it can
    only be measured against something worth measuring against.
    """
    moves = core.moves(state, explore=False)
    if not moves:
        return None
    player, boat, held, _, _, _ = state

    accepts = [m for m in moves if m[0] == 0]
    if accepts and len(held) < core.capacity:
        def worth(move: tuple[int, int]) -> float:
            task = move[1]
            leg = core.sail[core.origin[task]][core.dest[task]]
            reach = core.sail[player][core.origin[task]]
            return core.xp[task] / max(leg + reach, 1)
        return max(accepts, key=worth)

    sails = [m for m in moves if m[0] == 2]
    if not sails:
        return moves[0]

    # discharge what is aboard before going to look for more: a board is
    # useless while the hold is full, and this is what the greedy baseline
    # does. Rollout is only ever its base policy plus one improvement step,
    # so the base has to be the good one.
    errands = {core.dest[t] if loaded else core.origin[t] for t, loaded in held}
    errands.discard(player)
    toward = [m for m in sails if m[1] in errands]
    return min(toward or sails, key=lambda m: core.sail[player][m[1]])


def _play_out(core: Core, state: SearchState, horizon: int) -> tuple[int, int]:
    """Run the base policy until the tick budget is gone. -> (xp, ticks)."""
    gained = spent = 0
    while spent < horizon:
        move = _greedy_move(core, state)
        if move is None:
            break
        state, won, cost = core.apply(state, move)
        gained += won
        spent += cost
    return gained, spent


def choose(sim: Sim, rho: float, horizon: int = HORIZON, offers: str = 'sample',
           samples: int = 8, rng: np.random.Generator | None = None) -> np.ndarray:
    """Score every legal action by what the base policy makes of it afterwards.

    `offers` must not be blind. Under a blind view no unread board ever yields
    anything, so every rollout wanders a world where no new work appears, every
    action scores about the same, and rollout degenerates into its own base
    policy.

    One sampled future is worse still: the agent chases whichever board drew
    the luckiest hand, and re-draws every step, so it changes its mind
    constantly. Several futures are averaged instead, and every action is
    scored against the *same* futures - common random numbers, so the
    comparison between actions carries no sampling noise of its own.
    """
    draw = rng or np.random.default_rng()
    views = [_view(sim, offers, draw) for _ in range(max(samples, 1))]
    legal = sim.legal_actions()

    best, best_value = None, -np.inf
    for action in legal:
        move = (int(action[0]), int(action[1]))
        total, counted = 0.0, 0
        for core in views:
            start, _ = core.settle(_start(sim))
            if move not in core.moves(start, explore=True):
                continue
            state, won, cost = core.apply(start, move)
            gained, spent = _play_out(core, state, horizon)
            total += (won + gained) - rho * (cost + spent)
            counted += 1
        if counted and total / counted > best_value:
            best, best_value = action, total / counted
    return best if best is not None else legal[0]


class Rollout:
    """A policy that rolls out every legal action and plays the best."""

    def __init__(self, rho: float = 1.7, horizon: int = HORIZON, offers: str = 'sample',
                 samples: int = 8, seed: int = 0) -> None:
        self.rho = rho
        self.horizon = horizon
        self.offers = offers
        self.samples = samples
        self.rng = np.random.default_rng(seed)

    def __call__(self, sim: Sim) -> np.ndarray:
        return choose(sim, self.rho, self.horizon, self.offers, self.samples, self.rng)


def rollout(rho: float = 1.7, horizon: int = HORIZON, offers: str = 'sample',
            samples: int = 8) -> Rollout:
    return Rollout(rho, horizon, offers, samples)
