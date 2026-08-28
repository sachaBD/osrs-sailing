"""Run policies against the simulator and report xp/hr.

    python3 -m routing.evaluate               level 30, every baseline
    python3 -m routing.evaluate 30 40         a sensitivity sweep on t_dock

Absolute numbers mean little while the cost constants are guesses, so what
this reports is a comparison, and the sweep exists to show whether the
comparison survives being wrong about them.
"""
from __future__ import annotations

import sys
from dataclasses import replace

import numpy as np

from . import policies
from .instance import Instance
from .params import Params
from .sim import Sim

TICK = 0.6
HORIZON = 20_000  # ticks, about 3.3 hours
SEEDS = 30


def measure(instance: Instance, policy, seeds: int = SEEDS,
            horizon: int = HORIZON, start: int = 0) -> tuple[float, float]:
    """-> mean xp/hr and the half-width of its 95% interval over `seeds` runs."""
    rates = np.empty(seeds)
    for seed in range(seeds):
        sim = Sim(instance, np.random.default_rng(seed))
        sim.reset(start)
        state = sim.run(policy, horizon)
        rates[seed] = state.xp / state.ticks * 3600 / TICK
    return float(rates.mean()), float(1.96 * rates.std(ddof=1) / np.sqrt(seeds))


def compare(instance: Instance) -> dict[str, tuple[float, float]]:
    return {name: measure(instance, policy) for name, policy in policies.ALL.items()}


def main(argv: list[str]) -> None:
    level = int(argv[0]) if argv else 30
    instance = Instance.at_level(level)
    print(instance.describe(), f'\n{SEEDS} seeds, {HORIZON * TICK / 3600:.1f}h each\n')

    results = compare(instance)
    best = max(results.values())[0]
    for name, (mean, error) in sorted(results.items(), key=lambda kv: -kv[1][0]):
        bar = '#' * round(28 * mean / best)
        print(f'  {name:20} {mean:8,.0f} +/- {error:5,.0f}  {bar}')

    if len(argv) > 1:
        print('\nsensitivity: does the ranking survive a wrong t_dock?\n')
        print(f'  {"t_dock":>7}  ' + ''.join(f'{n:>20}' for n in policies.ALL))
        for dock in (2, 5, 10, 20, 40):
            tweaked = Instance.at_level(level, params=replace(instance.params, t_dock=dock))
            row = [measure(tweaked, p, seeds=12)[0] for p in policies.ALL.values()]
            order = np.argsort(np.argsort(-np.array(row)))
            print(f'  {dock:>7}  ' + ''.join(f'{v:>14,.0f} (#{o + 1})' for v, o in zip(row, order)))


if __name__ == '__main__':
    main(sys.argv[1:])
