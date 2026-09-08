"""Do the two simulators agree?

There are two implementations of `docs/PROBLEM.md`: `problem/sim.py`, which is
the definition, and the Rust one in `search/`, which is the fast one. Keeping
both is a deliberate cost, and this is what makes it safe - a recording of
random legal play, replayed through Python, asserting that every legal set,
every duration and every resulting state matches.

**If they disagree, Python is right.**

Random play rather than sensible play, because the interesting divergences are
in the corners: swapping a held task, recalling onto stranded cargo, a delivery
that trips a reroll. A policy would never go there; a bug would.

The offers travel in the recording rather than being redrawn here. numpy's
generator does not exist outside numpy, so the draw is defined in Rust and this
test primes `Sim._draws` with it - the one thing the two ends do not compute
independently.

Skipped, not failed, when the crate has not been built: `make search-check`
builds it, and a machine without a Rust toolchain can still run `make check`.
"""
from __future__ import annotations

import json
import subprocess
import unittest

import numpy as np

from porttasks.paths import ROOT
from porttasks.routing.problem.export import write
from porttasks.routing.problem.instance import Instance
from porttasks.routing.problem.sim import Action, Sim, State

LEVEL = 67
SEEDS = (0, 1, 2, 3, 4)
STEPS = 5_000

CRATE = ROOT / 'search'
BINARY = CRATE / 'target' / 'release' / 'porttasks-search'


def _trace(seed: int) -> dict:
    out = subprocess.run([str(BINARY), 'trace', str(LEVEL), str(seed), str(STEPS)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _state(raw: dict, seed: int) -> State:
    """A recorded state as Python's, so the two can be compared as values."""
    return State.from_dict({**raw, 'seed': seed, 'held': raw['held'], 'loaded': raw['loaded']})


@unittest.skipUnless(BINARY.exists(), f'{BINARY.relative_to(ROOT)} not built; run `make search`')
class TestRustAgreesWithPython(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        write(LEVEL)  # the crate reads the export, so it must be current
        cls.instance = Instance.at_level(LEVEL)

    def _sim_primed(self, trace: dict) -> Sim:
        """A Python sim whose board draws are the ones Rust actually used."""
        sim = Sim(self.instance)
        for epoch, offers in enumerate(trace['offers']):
            drawn = np.array(offers, np.int32)
            drawn.flags.writeable = False
            sim._draws[(trace['seed'], epoch)] = drawn
        return sim

    def test_every_step_matches(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                trace = _trace(seed)
                sim = self._sim_primed(trace)
                state = sim.reset(seed=seed, start_port=trace['start_port'])
                self.assertEqual(state, _state(trace['start'], seed), 'initial state')

                for i, record in enumerate(trace['steps']):
                    mine = {a.as_tuple() for a in sim.legal(state)}
                    theirs = {tuple(a) for a in record['legal']}
                    self.assertEqual(mine, theirs, f'legal actions at step {i}')

                    # step, not step_unchecked: Python re-derives legality itself,
                    # so an action Rust invented would raise rather than pass
                    step = sim.step(state, Action(*record['action']))
                    self.assertEqual(step.ticks, record['ticks'], f'duration at step {i}')
                    self.assertEqual(step.xp, record['xp'], f'xp at step {i}')
                    self.assertEqual(step.state, _state(record['after'], seed),
                                     f'state after step {i}')
                    self.assertEqual(step.state.xp, record['after']['xp'], f'total xp at {i}')
                    self.assertEqual(step.state.ticks, record['after']['ticks'], f'ticks at {i}')
                    state = step.state

    def test_the_run_actually_exercised_the_corners(self):
        """A parity test over play that never rerolls or swaps proves little."""
        seen = {'reroll': False, 'swap': False, 'recall': False, 'deliver': False}
        for seed in SEEDS:
            trace = _trace(seed)
            for record in trace['steps']:
                kind, _, victim = record['action']
                seen['swap'] |= kind == 0 and victim != -1
                seen['recall'] |= kind == 3
                seen['deliver'] |= record['xp'] > 0
            seen['reroll'] |= trace['steps'][-1]['after']['epoch'] > 0
        self.assertTrue(all(seen.values()), f'random play never reached: {seen}')
