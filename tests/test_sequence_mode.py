"""Unit tests for M7 — Manual Temporal Sequence Engine V1."""

import unittest
from unittest.mock import MagicMock

from aic2026.search.sequence import (
    MatchGroup,
    SequenceChain,
    SequenceDiagnostics,
    SequenceOrchestrator,
    SequenceOverallStatus,
    StepConfig,
    StepStatus,
    TemporalOccurrence,
    classify_chain_group,
    deduplicate_dense_occurrences,
    extract_temporal_occurrence,
    rank_chains,
)


class TestTemporalOccurrenceExtraction(unittest.TestCase):
    def test_point_frame_occurrence_mapping(self):
        hit = {
            "video_id": "L21_V001",
            "frame_id": 1200,
            "pts_time": 48.0,
            "rank": 1,
            "score": 0.88,
            "score_type": "cosine_similarity",
            "evidence_id": "L21_V001:1200",
            "payload": {"frame_idx": 1200, "pts_time": 48.0},
        }
        occ = extract_temporal_occurrence("S1", 0, "siglip_custom", hit)
        self.assertIsNotNone(occ)
        assert occ is not None
        self.assertEqual(occ.video_id, "L21_V001")
        self.assertEqual(occ.start_ms, 48000)
        self.assertEqual(occ.end_ms, 48000)
        self.assertEqual(occ.anchor_ms, 48000)
        self.assertEqual(occ.native_rank, 1)
        self.assertEqual(occ.native_score, 0.88)

    def test_ocr_item_occurrence_mapping(self):
        hit = {
            "video_id": "L21_V002",
            "pts_time": 15.5,
            "rank": 2,
            "score": -3.2,
            "score_type": "bm25",
            "evidence_id": "ocr_1234",
        }
        occ = extract_temporal_occurrence("S1", 0, "ocr_bm25", hit)
        self.assertIsNotNone(occ)
        assert occ is not None
        self.assertEqual(occ.start_ms, 15500)
        self.assertEqual(occ.end_ms, 15500)
        self.assertEqual(occ.anchor_ms, 15500)

    def test_asr_segment_occurrence_mapping(self):
        hit = {
            "video_id": "L21_V003",
            "start_sec": 10.2,
            "end_sec": 14.8,
            "rank": 3,
            "score": -5.1,
            "score_type": "bm25",
            "evidence_id": "asr_seg_99",
        }
        occ = extract_temporal_occurrence("S2", 1, "asr_bm25", hit)
        self.assertIsNotNone(occ)
        assert occ is not None
        self.assertEqual(occ.start_ms, 10200)
        self.assertEqual(occ.end_ms, 14800)
        self.assertEqual(occ.anchor_ms, 12500)

    def test_invalid_hit_missing_video_id(self):
        hit = {"pts_time": 10.0}
        occ = extract_temporal_occurrence("S1", 0, "siglip_custom", hit)
        self.assertIsNone(occ)


class TestStepConfigValidation(unittest.TestCase):
    def test_valid_free_text_config(self):
        cfg = StepConfig(step_id="S1", lane="siglip_custom", query="car on street")
        is_valid, err = cfg.validate()
        self.assertTrue(is_valid)
        self.assertIsNone(err)

    def test_media_bm25_rejected(self):
        cfg = StepConfig(step_id="S1", lane="media_bm25", query="HTV")
        is_valid, err = cfg.validate()
        self.assertFalse(is_valid)
        self.assertIn("no temporal authority", err or "")

    def test_btc_objects_requires_classes(self):
        cfg = StepConfig(step_id="S1", lane="btc_objects", query="")
        is_valid, err = cfg.validate()
        self.assertFalse(is_valid)
        self.assertIn("classes", err or "")

        cfg_with_classes = StepConfig(step_id="S1", lane="btc_objects", options={"classes": ["person"]})
        is_valid2, err2 = cfg_with_classes.validate()
        self.assertTrue(is_valid2)
        self.assertIsNone(err2)


class TestMatchGroupClassification(unittest.TestCase):
    def test_group_classification_3_steps(self):
        # 3 steps total: indices 0, 1, 2
        self.assertEqual(classify_chain_group([0, 1, 2], 3), MatchGroup.FULL_MATCH)
        self.assertEqual(classify_chain_group([0, 1], 3), MatchGroup.PREFIX_MATCH)
        self.assertEqual(classify_chain_group([1, 2], 3), MatchGroup.SUFFIX_MATCH)
        self.assertEqual(classify_chain_group([0, 2], 3), MatchGroup.PARTIAL_MATCH)  # non-consecutive
        self.assertEqual(classify_chain_group([1], 3), MatchGroup.STEP_ONLY_MATCH)
        self.assertEqual(classify_chain_group([0], 3), MatchGroup.STEP_ONLY_MATCH)

    def test_group_classification_4_steps(self):
        # 4 steps total: indices 0, 1, 2, 3
        self.assertEqual(classify_chain_group([0, 1, 2, 3], 4), MatchGroup.FULL_MATCH)
        self.assertEqual(classify_chain_group([0, 1, 2], 4), MatchGroup.PREFIX_MATCH)
        self.assertEqual(classify_chain_group([1, 2, 3], 4), MatchGroup.SUFFIX_MATCH)
        self.assertEqual(classify_chain_group([1, 2], 4), MatchGroup.PARTIAL_MATCH)  # intermediate consecutive
        self.assertEqual(classify_chain_group([0, 3], 4), MatchGroup.PARTIAL_MATCH)
        self.assertEqual(classify_chain_group([2], 4), MatchGroup.STEP_ONLY_MATCH)


class TestChainRanking(unittest.TestCase):
    def test_lexicographical_ranking(self):
        occ_a = TemporalOccurrence("S1", 0, "siglip_custom", "L01", 1000, 1000, 1000, 1, 0.9, "cos", "H", "e1", {})
        occ_b = TemporalOccurrence("S2", 1, "siglip_custom", "L01", 5000, 5000, 5000, 2, 0.8, "cos", "H", "e2", {})
        occ_c = TemporalOccurrence("S2", 1, "siglip_custom", "L01", 8000, 8000, 8000, 1, 0.85, "cos", "H", "e3", {})

        # Chain 1: S1 (rank 1) + S2 (rank 2), span 4000
        c1 = SequenceChain(
            chain_id="c1", video_id="L01", group=MatchGroup.FULL_MATCH,
            matched_step_ids=["S1", "S2"], matched_step_indices=[0, 1],
            total_steps=2, matched_step_count=2, occurrences=[occ_a, occ_b],
            consecutive_gaps_ms=[4000], total_span_ms=4000,
            sum_native_ranks=3, worst_native_rank=2, min_start_ms=1000, max_end_ms=5000
        )

        # Chain 2: S1 (rank 1) + S2 (rank 1), span 7000 (better sum rank, worse span)
        c2 = SequenceChain(
            chain_id="c2", video_id="L01", group=MatchGroup.FULL_MATCH,
            matched_step_ids=["S1", "S2"], matched_step_indices=[0, 1],
            total_steps=2, matched_step_count=2, occurrences=[occ_a, occ_c],
            consecutive_gaps_ms=[7000], total_span_ms=7000,
            sum_native_ranks=2, worst_native_rank=1, min_start_ms=1000, max_end_ms=8000
        )

        ranked = rank_chains([c1, c2])
        # c2 has sum_native_ranks=2 vs c1 sum_native_ranks=3 -> c2 must be first
        self.assertEqual(ranked[0].chain_id, "c2")
        self.assertEqual(ranked[1].chain_id, "c1")


class TestDenseDeduplication(unittest.TestCase):
    def test_dense_shot_deduplication(self):
        occs = [
            TemporalOccurrence("S1", 0, "siglip", "V1", 1000, 1000, 1000, 5, 0.7, "c", "H", "e1", {}),
            TemporalOccurrence("S1", 0, "siglip", "V1", 1200, 1200, 1200, 1, 0.9, "c", "H", "e2", {}),  # best rank in cluster
            TemporalOccurrence("S1", 0, "siglip", "V1", 1400, 1400, 1400, 8, 0.6, "c", "H", "e3", {}),
            TemporalOccurrence("S1", 0, "siglip", "V1", 8000, 8000, 8000, 2, 0.85, "c", "H", "e4", {}),
        ]
        deduped = deduplicate_dense_occurrences(occs, dedup_window_ms=1000)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0].evidence_id, "e2")  # picked rank 1
        self.assertEqual(deduped[1].evidence_id, "e4")


class TestSequenceOrchestratorExecution(unittest.TestCase):
    def test_mocked_2_step_full_and_partial_join(self):
        mock_api = MagicMock()
        # S1 (siglip_custom) returns video L21_V001 at 10s and L21_V002 at 50s
        mock_api.siglip_search.return_value = (
            200,
            {
                "hits": [
                    {"video_id": "L21_V001", "pts_time": 10.0, "rank": 1, "score": 0.9, "evidence_id": "s1_h1"},
                    {"video_id": "L21_V002", "pts_time": 50.0, "rank": 2, "score": 0.8, "evidence_id": "s1_h2"},
                ]
            },
        )
        # S2 (asr_bm25) returns video L21_V001 at 20s-25s and L21_V003 at 30s-35s
        mock_api.asr_bm25_search.return_value = (
            200,
            {
                "hits": [
                    {"video_id": "L21_V001", "start_sec": 20.0, "end_sec": 25.0, "rank": 1, "score": -4.0, "evidence_id": "s2_h1"},
                    {"video_id": "L21_V003", "start_sec": 30.0, "end_sec": 35.0, "rank": 2, "score": -5.0, "evidence_id": "s2_h2"},
                ]
            },
        )

        orchestrator = SequenceOrchestrator(mock_api)
        steps = [
            StepConfig(step_id="S1", lane="siglip_custom", query="red car"),
            StepConfig(step_id="S2", lane="asr_bm25", query="welcome"),
        ]

        resp = orchestrator.execute_sequence(
            steps=steps,
            top_k_per_step=10,
            strict_order=True,
            min_gap_ms=0,
            max_gap_ms=60000,
        )

        self.assertEqual(resp.status, SequenceOverallStatus.OK)
        self.assertEqual(len(resp.steps), 2)
        self.assertEqual(len(resp.groups["FULL_MATCH"]), 1)
        self.assertEqual(resp.groups["FULL_MATCH"][0].video_id, "L21_V001")
        self.assertEqual(resp.groups["FULL_MATCH"][0].consecutive_gaps_ms, [10000])  # 20s - 10s = 10000ms
        self.assertEqual(resp.groups["FULL_MATCH"][0].total_span_ms, 15000)  # 25s - 10s = 15000ms

        # STEP_ONLY_MATCH should contain L21_V002 and L21_V003
        step_only_vids = {c.video_id for c in resp.groups["STEP_ONLY_MATCH"]}
        self.assertIn("L21_V002", step_only_vids)
        self.assertIn("L21_V003", step_only_vids)


if __name__ == "__main__":
    unittest.main()
