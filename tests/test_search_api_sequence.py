"""HTTP API tests for M7 — Sequence retrieval endpoints."""

import json
import unittest
from http import HTTPStatus
from unittest.mock import MagicMock

from aic2026.search.api import AsrSearchApi


class TestSearchApiSequence(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_db.is_file.return_value = True
        self.mock_capability = MagicMock()
        self.mock_orchestrator = MagicMock()
        self.mock_workspace = MagicMock()

        self.api = AsrSearchApi(
            database=self.mock_db,
            capability_service=self.mock_capability,
            orchestrator=self.mock_orchestrator,
        )

    def test_sequence_health_endpoint(self):
        status, payload = self.api.sequence_health()
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["status"], "OK")
        self.assertEqual(payload["mode"], "SEQUENCE")
        self.assertIn("siglip_custom", payload["temporal_lanes_supported"])
        self.assertIn("asr_bm25", payload["temporal_lanes_supported"])
        self.assertNotIn("media_bm25", payload["temporal_lanes_supported"])

    def test_sequence_search_validation_errors(self):
        # Empty steps
        status, payload = self.api.sequence_search({})
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["status"], "ERROR")

        # 1 step (minimum 2 required)
        status, payload = self.api.sequence_search({
            "steps": [{"step_id": "S1", "lane": "siglip_custom", "query": "dog"}]
        })
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertIn("at least 2 steps", payload["error"])

        # >5 steps (maximum 5 supported)
        status, payload = self.api.sequence_search({
            "steps": [{"step_id": f"S{i}", "lane": "siglip_custom", "query": "dog"} for i in range(6)]
        })
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertIn("at most 5 steps", payload["error"])

        # Negative min_gap
        status, payload = self.api.sequence_search({
            "steps": [
                {"step_id": "S1", "lane": "siglip_custom", "query": "dog"},
                {"step_id": "S2", "lane": "siglip_custom", "query": "cat"},
            ],
            "min_gap_ms": -100,
        })
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertIn("negative", payload["error"])

    def test_sequence_search_media_bm25_rejected(self):
        status, payload = self.api.sequence_search({
            "steps": [
                {"step_id": "S1", "lane": "media_bm25", "query": "HTV9"},
                {"step_id": "S2", "lane": "siglip_custom", "query": "cat"},
            ]
        })
        self.assertEqual(status, HTTPStatus.OK)
        # S1 should have INVALID_CONFIG / NO_TEMPORAL_AUTHORITY status
        s1_result = [s for s in payload["steps"] if s["step_id"] == "S1"][0]
        self.assertEqual(s1_result["status"], "INVALID_CONFIG")
        self.assertIn("no temporal authority", s1_result["error"])


if __name__ == "__main__":
    unittest.main()
