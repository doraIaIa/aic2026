"""Unit tests for M7 — Sequence benchmark and controlled fixture runner."""

import unittest
from aic2026.evaluation.sequence_benchmark import run_controlled_fixture


class TestSequenceBenchmark(unittest.TestCase):
    def test_controlled_fixture_all_cases_pass(self):
        summary = run_controlled_fixture()
        self.assertEqual(summary["fixture_name"], "FUNCTIONAL_TEMPORAL_FIXTURE")
        self.assertEqual(summary["quality_status"], "FUNCTIONAL_ONLY_NOT_COMPETITION_RELEVANCE_GT")
        self.assertEqual(summary["total_cases"], 12)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["passed"], 12)


if __name__ == "__main__":
    unittest.main()
