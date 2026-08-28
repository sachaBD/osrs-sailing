"""Behavioural tests for the port-task simulator."""
from __future__ import annotations

import unittest

import numpy as np

from routing.instance import NONE, Instance
from routing.sim import ABANDON, ACCEPT, RECALL, SAIL, Sim
from routing.errors import ModelError
from routing import policies

INSTANCE = Instance.at_level(30)


def _sim(seed: int = 0, start: int = 0) -> Sim:
    sim = Sim(INSTANCE, np.random.default_rng(seed))
    sim.reset(start)
    return sim


class TestInstance(unittest.TestCase):
    def test_board_pools_keep_tasks_the_level_cannot_do(self):
        # the draw is from the whole pool, so ineligible tasks still burn a slot;
        # filtering them out here would silently inflate how much choice a board gives
        pools = np.concatenate([INSTANCE.board_pool(p)
                                for p in np.flatnonzero(INSTANCE.has_board)])
        self.assertTrue((~INSTANCE.task_eligible[pools]).any())

    def test_sail_matrix_is_symmetric_with_zero_diagonal(self):
        self.assertTrue((INSTANCE.sail == INSTANCE.sail.T).all())
        self.assertTrue((np.diag(INSTANCE.sail) == 0).all())


class TestLegality(unittest.TestCase):
    def test_illegal_action_raises(self):
        sim = _sim()
        with self.assertRaises(ModelError):
            sim.step((RECALL, 0))  # the boat is already here

    def test_cannot_sail_without_the_boat(self):
        sim = _sim(start=1)
        charter = [a for a in sim.legal_actions() if a[0] == 3][0]
        sim.step(charter)
        self.assertNotEqual(sim.state.port_boat, sim.state.port_player)
        self.assertFalse((sim.legal_actions()[:, 0] == SAIL).any())

    def test_only_eligible_offers_can_be_accepted(self):
        sim = _sim()
        for kind, task in sim.legal_actions():
            if kind == ACCEPT:
                self.assertTrue(INSTANCE.task_eligible[task])


class TestInvariants(unittest.TestCase):
    def test_random_play_never_breaks_the_rules(self):
        for seed in range(8):
            sim = _sim(seed)
            rng = np.random.default_rng(seed)
            previous_ticks, previous_xp = 0, 0
            for _ in range(400):
                sim.step(policies.random_legal(sim, rng))
                state = sim.state
                self.assertLessEqual(int((state.held != NONE).sum()), INSTANCE.capacity)
                self.assertGreaterEqual(state.ticks, previous_ticks)
                self.assertGreaterEqual(state.xp, previous_xp)
                self.assertLess(state.completions, INSTANCE.params.reroll_completions)
                self.assertTrue((state.offers[~state.seen] == NONE).all())
                previous_ticks, previous_xp = state.ticks, state.xp

    def test_xp_is_only_awarded_on_delivery(self):
        sim = _sim()
        rng = np.random.default_rng(3)
        for _ in range(400):
            before = sim.state.held[sim.state.held != NONE].copy()
            gained, _ = sim.step(policies.random_legal(sim, rng))
            after = sim.state.held[sim.state.held != NONE]
            if gained:
                self.assertLess(len(after), len(before) + 1)


class TestMechanics(unittest.TestCase):
    def test_recall_destroys_cargo_but_keeps_the_task(self):
        sim = _sim()
        offer = next(a for a in sim.legal_actions() if a[0] == ACCEPT)
        sim.step(offer)
        task = int(offer[1])
        sim.state.loaded[:] = sim.state.held != NONE
        shipwright = int(np.flatnonzero((INSTANCE.recall != NONE)
                                        & (np.arange(INSTANCE.n_ports) != sim.state.port_player))[0])
        sim.step((3, shipwright))  # charter away, leaving the boat
        sim.step((RECALL, 0))
        self.assertEqual(sim.state.port_boat, sim.state.port_player)
        self.assertFalse(sim.state.loaded.any())
        self.assertIn(task, list(sim.state.held))

    def test_abandon_frees_a_slot_without_advancing_the_reroll(self):
        sim = _sim()
        sim.step(next(a for a in sim.legal_actions() if a[0] == ACCEPT))
        before_slots, before_k = sim.state.free_slots, sim.state.completions
        sim.step(next(a for a in sim.legal_actions() if a[0] == ABANDON))
        self.assertEqual(sim.state.free_slots, before_slots + 1)
        self.assertEqual(sim.state.completions, before_k)

    def test_a_reroll_clears_what_was_seen(self):
        sim = _sim()
        sim.state.seen[:] = True
        sim.state.completions = INSTANCE.params.reroll_completions - 1
        # force one delivery: hold a task already at its destination, loaded
        task = int(np.flatnonzero(INSTANCE.task_eligible
                                  & (INSTANCE.task_dest == sim.state.port_player))[0])
        sim.state.held[0], sim.state.loaded[0] = task, True
        sim._settle()
        self.assertEqual(sim.state.completions, 0)
        # only the board underfoot is read again, because reveal follows the reroll
        self.assertEqual(int(sim.state.seen.sum()), 1)

    def test_accepted_tasks_survive_a_reroll(self):
        # the property the whole specification turns on: offers are perishable,
        # accepted tasks are not, which is why banking before a reroll is a play
        sim = _sim()
        sim.step(next(a for a in sim.legal_actions() if a[0] == ACCEPT))
        banked = sorted(int(t) for t in sim.state.held if t != NONE)
        sim.state.completions = INSTANCE.params.reroll_completions - 1
        task = int(np.flatnonzero(INSTANCE.task_eligible
                                  & (INSTANCE.task_dest == sim.state.port_player))[0])
        sim.state.held[-1], sim.state.loaded[-1] = task, True
        sim._settle()
        self.assertEqual(sim.state.completions, 0)
        self.assertTrue(set(banked) <= {int(t) for t in sim.state.held})


class TestPolicies(unittest.TestCase):
    def test_greedy_beats_random_by_a_mile(self):
        from routing.evaluate import measure
        random_rate, _ = measure(INSTANCE, policies.random_legal, seeds=4, horizon=6000)
        greedy_rate, _ = measure(INSTANCE, policies.greedy_rate, seeds=4, horizon=6000)
        self.assertGreater(greedy_rate, 10 * random_rate)


if __name__ == '__main__':
    unittest.main()
