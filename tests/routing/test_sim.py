"""The simulator: does it obey docs/PROBLEM.md?

These are the tests everything else is measured against, so they check
dynamics, legality and the value semantics search relies on - never
performance.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

import numpy as np

from porttasks.routing.errors import ProblemError
from porttasks.routing.problem.instance import NONE, Instance
from porttasks.routing.problem.sim import CHARTER, RECALL, SAIL, TAKE, Action, Sim, State

INSTANCE = Instance.at_level(30)
SIM = Sim(INSTANCE)


def _random_play(seed: int, steps: int):
    """Yield (state, action, step) for a run of uniformly random legal actions."""
    rng = np.random.default_rng(seed)
    state = SIM.reset(seed=seed)
    for _ in range(steps):
        legal = SIM.legal(state)
        action = legal[rng.integers(len(legal))]
        step = SIM.step(state, action)
        yield state, action, step
        state = step.state


def _with_held(state: State, task: int, slot: int, loaded: bool) -> State:
    held, aboard = state.held.copy(), state.loaded.copy()
    held[slot], aboard[slot] = task, loaded
    held.flags.writeable = aboard.flags.writeable = False
    return replace(state, held=held, loaded=aboard)


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
        with self.assertRaises(ProblemError):
            SIM.step(SIM.reset(), Action(RECALL))  # the boat is already here

    def test_cannot_sail_without_the_boat(self):
        state = SIM.reset(start_port=1)
        state = SIM.step(state, next(a for a in SIM.legal(state) if a.kind == CHARTER)).state
        self.assertNotEqual(state.port_boat, state.port_player)
        self.assertFalse(any(a.kind == SAIL for a in SIM.legal(state)))

    def test_only_eligible_unheld_offers_can_be_taken(self):
        for state, _, _ in _random_play(4, 200):
            held = set(state.tasks.tolist())
            for action in SIM.legal(state):
                if action.kind == TAKE:
                    self.assertTrue(INSTANCE.task_eligible[action.arg])
                    self.assertNotIn(action.arg, held)
                    self.assertTrue(action.victim == NONE or action.victim in held)

    def test_a_full_hold_only_offers_swaps(self):
        seen_full = False
        for state, _, _ in _random_play(5, 300):
            if state.free_slots:
                continue
            seen_full = True
            self.assertTrue(all(a.victim != NONE for a in SIM.legal(state) if a.kind == TAKE))
        self.assertTrue(seen_full, 'the hold never filled, so nothing was tested')


class TestInvariants(unittest.TestCase):
    def test_random_play_never_breaks_the_rules(self):
        for seed in range(6):
            ticks, xp = 0, 0
            for _, _, step in _random_play(seed, 300):
                state = step.state
                self.assertLessEqual(len(state.tasks), INSTANCE.capacity)
                self.assertGreaterEqual(state.ticks, ticks)
                self.assertGreaterEqual(state.xp, xp)
                self.assertLess(state.completions, INSTANCE.params.reroll_completions)
                self.assertTrue((SIM.observed(state)[~state.seen] == NONE).all())
                ticks, xp = state.ticks, state.xp

    def test_xp_is_only_awarded_on_delivery(self):
        for state, _, step in _random_play(3, 400):
            if step.xp:
                self.assertLess(len(step.state.tasks), len(state.tasks) + 1)

    def test_accounting_matches_the_totals(self):
        xp = ticks = 0
        for _, _, step in _random_play(7, 300):
            xp, ticks = xp + step.xp, ticks + step.ticks
            self.assertEqual((step.state.xp, step.state.ticks), (xp, ticks))


class TestValueSemantics(unittest.TestCase):
    def test_stepping_leaves_the_parent_untouched(self):
        for state, _, step in _random_play(1, 120):
            before = state.clone()
            SIM.step(step.state, SIM.legal(step.state)[0])
            self.assertEqual(state, before)

    def test_state_arrays_are_read_only(self):
        state = SIM.reset()
        for array in (state.held, state.loaded, state.seen):
            with self.assertRaises(ValueError):
                array[0] = 0

    def test_a_state_survives_a_json_round_trip(self):
        for _, _, step in _random_play(2, 60):
            sim, restored = Sim.from_json(SIM.to_json(step.state), INSTANCE)
            self.assertEqual(restored, step.state)
            self.assertEqual(hash(restored), hash(step.state))
            self.assertTrue(np.array_equal(sim.observed(restored), SIM.observed(step.state)))

    def test_a_restored_state_plays_on_identically(self):
        state = next(s for s, _, _ in _random_play(8, 40))
        _, restored = Sim.from_json(SIM.to_json(state))
        twin = Sim(INSTANCE)
        for _ in range(40):
            action = SIM.legal(state)[0]
            self.assertEqual(action, twin.legal(restored)[0])
            state = SIM.step(state, action).state
            restored = twin.step(restored, action).state
            self.assertEqual(state, restored)

    def test_from_dict_rejects_the_wrong_level(self):
        with self.assertRaises(ProblemError):
            Sim.from_dict({'level': 58, 'state': SIM.reset().to_dict()}, INSTANCE)

    def test_the_key_ignores_the_scoreboard(self):
        # xp and ticks are totals, not state: two states differing only in them
        # face the same decision problem
        state = SIM.reset()
        self.assertEqual(state, replace(state, xp=99, ticks=99))


class TestMechanics(unittest.TestCase):
    def test_recall_destroys_cargo_but_keeps_the_task(self):
        state = SIM.reset()
        take = next(a for a in SIM.legal(state) if a.kind == TAKE)
        state = _with_held(SIM.step(state, take).state, take.arg, 0, loaded=True)
        shipwright = int(np.flatnonzero((INSTANCE.recall != NONE)
                                        & (np.arange(INSTANCE.n_ports) != state.port_player))[0])
        state = SIM.step(state, Action(CHARTER, shipwright)).state  # boat left behind
        state = SIM.step(state, Action(RECALL)).state
        self.assertEqual(state.port_boat, state.port_player)
        self.assertFalse(state.loaded.any())
        self.assertIn(take.arg, state.tasks.tolist())

    def test_a_swap_costs_the_drop_and_does_not_advance_the_reroll(self):
        state = SIM.reset()
        first = next(a for a in SIM.legal(state) if a.kind == TAKE)
        state = SIM.step(state, first).state
        swap = next(a for a in SIM.legal(state) if a.kind == TAKE and a.victim == first.arg)
        step = SIM.step(state, swap)
        self.assertEqual(step.ticks, INSTANCE.params.t_board + INSTANCE.params.t_drop)
        self.assertEqual(step.state.completions, state.completions)
        self.assertNotIn(first.arg, step.state.tasks.tolist())
        self.assertIn(swap.arg, step.state.tasks.tolist())

    def test_a_reroll_clears_what_was_seen(self):
        state = SIM.reset()
        seen = np.ones(INSTANCE.n_ports, bool)
        seen.flags.writeable = False
        state = replace(state, seen=seen, completions=INSTANCE.params.reroll_completions - 1)
        # force one delivery: hold a task already at its destination, loaded
        task = int(np.flatnonzero(INSTANCE.task_eligible
                                  & (INSTANCE.task_dest == state.port_player))[0])
        settled, gained = SIM._settle(_with_held(state, task, 0, loaded=True))
        self.assertEqual(gained, int(INSTANCE.task_xp[task]))
        self.assertEqual(settled.epoch, state.epoch + 1)
        self.assertEqual(settled.completions, 0)
        # only the board underfoot is read again, because reveal follows the reroll
        self.assertEqual(int(settled.seen.sum()), 1)

    def test_accepted_tasks_survive_a_reroll(self):
        # the property the whole specification turns on: offers are perishable,
        # accepted tasks are not, which is why banking before a reroll is a play
        state = SIM.reset()
        state = SIM.step(state, next(a for a in SIM.legal(state) if a.kind == TAKE)).state
        banked = set(state.tasks.tolist())
        state = replace(state, completions=INSTANCE.params.reroll_completions - 1)
        task = int(np.flatnonzero(INSTANCE.task_eligible
                                  & (INSTANCE.task_dest == state.port_player))[0])
        settled, _ = SIM._settle(_with_held(state, task, -1, loaded=True))
        self.assertEqual(settled.completions, 0)
        self.assertLessEqual(banked, set(settled.tasks.tolist()))


class TestBeliefs(unittest.TestCase):
    def test_a_sample_keeps_what_was_read_and_redraws_the_rest(self):
        rng = np.random.default_rng(0)
        for state, _, _ in _random_play(9, 80):
            guess = SIM.sample_offers(state, rng)
            truth = SIM.true_offers(state)
            self.assertTrue((guess[state.seen] == truth[state.seen]).all())
            self.assertTrue((guess[~INSTANCE.has_board] == NONE).all())
            for port in np.flatnonzero(~state.seen & INSTANCE.has_board):
                self.assertTrue(np.isin(guess[port], INSTANCE.board_pool(port)).all())
                self.assertEqual(len(set(guess[port].tolist())), len(guess[port]))

    def test_the_true_offers_are_a_function_of_seed_and_epoch_alone(self):
        state = SIM.reset(seed=11)
        self.assertTrue(np.array_equal(SIM.true_offers(state), Sim(INSTANCE).true_offers(state)))
        self.assertFalse(np.array_equal(SIM.true_offers(state),
                                        SIM.true_offers(replace(state, epoch=1))))


if __name__ == '__main__':
    unittest.main()
