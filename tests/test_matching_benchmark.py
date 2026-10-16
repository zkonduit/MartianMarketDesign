"""Tests for the matching benchmark harness.

Run from the repository root:

    python -m unittest discover tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.matching_benchmark import make_world, simulate, stress
from kingdom_wars import Resource, settle_proposal


class WorldConstructionTest(unittest.TestCase):
    def test_make_world_is_deterministic(self) -> None:
        state_a, _ = make_world(10, seed=42)
        state_b, _ = make_world(10, seed=42)
        self.assertEqual(state_a.kingdoms.keys(), state_b.kingdoms.keys())
        for name, kingdom_a in state_a.kingdoms.items():
            self.assertEqual(kingdom_a.resources, state_b.kingdoms[name].resources)

    def test_make_world_builds_requested_kingdoms(self) -> None:
        state, _ = make_world(17, seed=1)
        self.assertEqual(len(state.kingdoms), 17)
        self.assertTrue(all(kingdom.active for kingdom in state.kingdoms.values()))


class SimulateTest(unittest.TestCase):
    def test_simulate_is_deterministic(self) -> None:
        first = simulate(12, epochs=25, seed=99).summary()
        second = simulate(12, epochs=25, seed=99).summary()
        self.assertEqual(first, second)

    def test_metrics_lie_in_expected_ranges(self) -> None:
        summary = simulate(12, epochs=25, seed=99).summary()
        self.assertGreaterEqual(summary["match_rate"], 0.0)
        self.assertLessEqual(summary["match_rate"], 1.0)
        self.assertGreaterEqual(summary["completion_rate"], 0.0)
        self.assertLessEqual(summary["completion_rate"], 1.0)
        self.assertLessEqual(summary["participants_who_traded"], 12)
        self.assertGreaterEqual(summary["median_time_to_match_epochs"], 0)

    def test_credit_settlements_preserve_zero_sum(self) -> None:
        state, rng = make_world(8, seed=3)
        state.epoch = 1
        from benchmarks.matching_benchmark import top_up

        top_up(state, rng)
        from kingdom_wars import IntentKind, post_intent

        post_intent(state, "K0", IntentKind.SELL, Resource.WOOD, 2)
        post_intent(state, "K1", IntentKind.BUY, Resource.WOOD, 2)
        from kingdom_wars import create_proposal, generate_candidates

        candidates = generate_candidates(state)
        self.assertTrue(candidates, "seeded world should produce a credit candidate")
        proposal = create_proposal(state, candidates[0].id)
        settle_proposal(state, proposal.id)
        balances = [kingdom.balance for kingdom in state.kingdoms.values()]
        self.assertEqual(sum(balances), 0)

    def test_cold_start_records_joiners(self) -> None:
        metrics = simulate(16, epochs=40, seed=5, late_join_epoch=20)
        self.assertIsInstance(metrics.cold_start_delays, list)
        for delay in metrics.cold_start_delays:
            self.assertGreaterEqual(delay, 0)


class StressTest(unittest.TestCase):
    def test_stress_sweeps_and_records_positive_times(self) -> None:
        rows = stress(max_kingdoms=15, seed=7)
        self.assertEqual([row["kingdoms"] for row in rows], [5, 10, 15])
        for row in rows:
            self.assertGreater(row["intents"], 0)
            self.assertGreaterEqual(row["generate_ms"], 0.0)

    def test_stress_is_deterministic_in_counts(self) -> None:
        first = stress(max_kingdoms=15, seed=7)
        second = stress(max_kingdoms=15, seed=7)
        for row_a, row_b in zip(first, second):
            self.assertEqual(row_a["intents"], row_b["intents"])
            self.assertEqual(row_a["candidates"], row_b["candidates"])


if __name__ == "__main__":
    unittest.main()
