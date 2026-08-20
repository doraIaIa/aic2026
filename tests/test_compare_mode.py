"""Tests for M6 Compare Mode & Lane Diagnostics Orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aic2026.search.compare import (
    CompareDiagnostics,
    CompareLaneConfig,
    CompareLaneResult,
    CompareOrchestrator,
    LaneStatus,
    OverallStatus,
    compute_video_diagnostics,
)


def test_compute_video_diagnostics_set_algebra() -> None:
    lane1_results = [
        {"video_id": "V001", "raw_score": 0.9},
        {"video_id": "V002", "raw_score": 0.8},
        {"video_id": "V003", "raw_score": 0.7},
    ]
    lane2_results = [
        {"video_id": "V002", "raw_score": 12.5},
        {"video_id": "V003", "raw_score": 10.1},
        {"video_id": "V004", "raw_score": 8.0},
    ]
    lane3_results = [
        {"video_id": "V003", "raw_score": 0.95},
        {"video_id": "V005", "raw_score": 0.85},
    ]

    r1 = CompareLaneResult(
        lane="siglip_custom",
        status=LaneStatus.OK,
        latency_ms=10.0,
        requested_top_k=10,
        result_count=3,
        results=lane1_results,
    )
    r2 = CompareLaneResult(
        lane="asr_bm25",
        status=LaneStatus.OK,
        latency_ms=5.0,
        requested_top_k=10,
        result_count=3,
        results=lane2_results,
    )
    r3 = CompareLaneResult(
        lane="ocr_bge",
        status=LaneStatus.OK,
        latency_ms=12.0,
        requested_top_k=10,
        result_count=2,
        results=lane3_results,
    )

    diag = compute_video_diagnostics([r1, r2, r3])

    # Total union: V001, V002, V003, V004, V005 = 5
    assert diag.video_union_count == 5
    # Intersection across all 3 lanes: V003 = 1
    assert diag.video_intersection_count == 1

    assert diag.per_lane_unique_videos == {
        "siglip_custom": 3,
        "asr_bm25": 3,
        "ocr_bge": 2,
    }

    # Unique to single lane:
    # siglip: V001 (1)
    # asr: V004 (1)
    # ocr: V005 (1)
    assert diag.unique_to_lane_videos == {
        "siglip_custom": 1,
        "asr_bm25": 1,
        "ocr_bge": 1,
    }

    # Pairwise:
    # siglip & asr: V002, V003 -> intersection=2, union=4 (V001..V004) -> jaccard = 2/4 = 0.5
    pair_map = {f"{p['lane_a']}__{p['lane_b']}": p for p in diag.pairwise_video_overlap}
    siglip_asr = pair_map.get("siglip_custom__asr_bm25")
    assert siglip_asr is not None
    assert siglip_asr["overlap_count"] == 2
    assert siglip_asr["jaccard"] == 0.5


def test_compare_orchestrator_sequential_execution_and_no_fusion() -> None:
    mock_api = MagicMock()
    mock_api.siglip_search.return_value = (
        200,
        {
            "status": "OK",
            "lane": "siglip_custom",
            "hits": [
                {"video_id": "V001", "raw_score": 0.88, "evidence_id": "EV1"},
                {"video_id": "V002", "raw_score": 0.77, "evidence_id": "EV2"},
            ],
        },
    )
    mock_api.asr_bm25_search.return_value = (
        200,
        {
            "status": "OK",
            "lane": "asr_bm25",
            "hits": [
                {"video_id": "V002", "raw_score": 5.4, "evidence_id": "EV3"},
                {"video_id": "V003", "raw_score": 4.1, "evidence_id": "EV4"},
            ],
        },
    )

    orchestrator = CompareOrchestrator(mock_api)
    res = orchestrator.execute_compare(
        query="test search query",
        lanes=[
            CompareLaneConfig(lane="siglip_custom", enabled=True),
            CompareLaneConfig(lane="asr_bm25", enabled=True),
        ],
        top_k=20,
    )

    assert res["status"] == "OK"
    assert res["mode"] == "COMPARE"
    assert res["query"] == "test search query"
    assert len(res["lanes"]) == 2

    # Verify native ranks and raw scores are preserved without normalization
    siglip_res = res["lanes"][0]
    assert siglip_res["lane"] == "siglip_custom"
    assert siglip_res["status"] == "OK"
    assert siglip_res["score_type"] == "cosine_similarity"
    assert siglip_res["score_direction"] == "HIGHER_IS_BETTER"
    assert siglip_res["results"][0]["raw_score"] == 0.88
    assert siglip_res["results"][1]["raw_score"] == 0.77

    asr_res = res["lanes"][1]
    assert asr_res["lane"] == "asr_bm25"
    assert asr_res["status"] == "OK"
    assert asr_res["score_type"] == "sqlite_fts5_bm25"
    assert asr_res["score_direction"] == "LOWER_IS_BETTER"
    assert asr_res["results"][0]["raw_score"] == 5.4
    assert asr_res["results"][1]["raw_score"] == 4.1

    # Ensure NO fusion or fused_results key exists
    assert "fused_results" not in res
    assert "rrf" not in res
    assert "combined_ranking" not in res


def test_compare_orchestrator_partial_failure_isolation() -> None:
    mock_api = MagicMock()
    mock_api.siglip_search.return_value = (
        200,
        {
            "status": "OK",
            "lane": "siglip_custom",
            "hits": [{"video_id": "V001", "raw_score": 0.85}],
        },
    )
    mock_api.asr_bge_search.return_value = (
        503,
        {"status": "ERROR", "error": "Model offline"},
    )
    mock_api.ocr_bm25_search.return_value = (
        200,
        {"status": "OK", "lane": "ocr_bm25", "hits": []},
    )

    orchestrator = CompareOrchestrator(mock_api)
    res = orchestrator.execute_compare(
        query="query with partial failure",
        lanes=[
            CompareLaneConfig(lane="siglip_custom", enabled=True),
            CompareLaneConfig(lane="asr_bge", enabled=True),
            CompareLaneConfig(lane="ocr_bm25", enabled=True),
        ],
        top_k=10,
    )

    # Partial status because at least 1 succeeded and 1 failed
    assert res["status"] == "PARTIAL"
    assert len(res["lanes"]) == 3

    assert res["lanes"][0]["status"] == "OK"
    assert len(res["lanes"][0]["results"]) == 1

    assert res["lanes"][1]["status"] == "UNAVAILABLE"
    assert res["lanes"][1]["error"] == "Model offline"

    assert res["lanes"][2]["status"] == "EMPTY"
    assert len(res["lanes"][2]["results"]) == 0


def test_compare_structured_lanes_skip_without_manual_config() -> None:
    mock_api = MagicMock()
    orchestrator = CompareOrchestrator(mock_api)

    # 1. qwen_structured with no facets
    res1 = orchestrator.execute_compare(
        query="natural language query",
        lanes=[
            CompareLaneConfig(lane="qwen_structured", enabled=True, options={}),
            CompareLaneConfig(lane="btc_objects", enabled=True, options={}),
        ],
        top_k=10,
    )

    # Neither structured lane was given explicit manual config -> both skipped
    assert res1["status"] == "ERROR"
    assert res1["lanes"][0]["status"] == "SKIPPED_INVALID_CONFIG"
    assert "qwen_structured skipped" in res1["lanes"][0]["warning"]
    assert res1["lanes"][1]["status"] == "SKIPPED_INVALID_CONFIG"
    assert "btc_objects skipped" in res1["lanes"][1]["warning"]

    # Verify api search was NOT called (no auto-parsing of natural query)
    mock_api.qwen_structured_search.assert_not_called()
    mock_api.btc_objects_search.assert_not_called()


def test_compare_structured_lanes_execute_with_valid_manual_config() -> None:
    mock_api = MagicMock()
    mock_api.qwen_structured_search.return_value = (
        200,
        {
            "status": "OK",
            "lane": "qwen_structured",
            "hits": [{"video_id": "V001", "raw_score": 1.0}],
        },
    )
    mock_api.btc_objects_search.return_value = (
        200,
        {
            "status": "OK",
            "lane": "btc_objects",
            "hits": [{"video_id": "V002", "raw_score": 0.95}],
        },
    )

    orchestrator = CompareOrchestrator(mock_api)
    res = orchestrator.execute_compare(
        query="car and motorcycle",
        lanes=[
            CompareLaneConfig(lane="qwen_structured", enabled=True, options={"objects": "car, motorcycle"}),
            CompareLaneConfig(
                lane="btc_objects",
                enabled=True,
                options={"classes": ["Car", "Motorcycle"], "match_mode": "ALL", "min_detector_score": 0.15},
            ),
        ],
        top_k=10,
    )

    assert res["status"] == "OK"
    assert res["lanes"][0]["status"] == "OK"
    assert res["lanes"][1]["status"] == "OK"
    mock_api.qwen_structured_search.assert_called_once()
    mock_api.btc_objects_search.assert_called_once()


def test_compare_scope_propagation() -> None:
    mock_api = MagicMock()
    mock_api.siglip_search.return_value = (200, {"status": "OK", "hits": []})
    mock_api.asr_bm25_search.return_value = (200, {"status": "OK", "hits": []})

    orchestrator = CompareOrchestrator(mock_api)
    orchestrator.execute_compare(
        query="test query",
        lanes=[
            CompareLaneConfig(lane="siglip_custom", enabled=True),
            CompareLaneConfig(lane="asr_bm25", enabled=True),
        ],
        candidate_video_ids=("L21_V001", "L21_V002"),
        top_k=15,
    )

    # Assert candidate_video_ids was propagated to both providers
    mock_api.siglip_search.assert_called_once()
    siglip_call_arg = mock_api.siglip_search.call_args[0][0]
    assert siglip_call_arg["candidate_video_ids"] == ["L21_V001", "L21_V002"]
    assert siglip_call_arg["top_k"] == 15

    mock_api.asr_bm25_search.assert_called_once()
    asr_call_arg = mock_api.asr_bm25_search.call_args[0][0]
    assert asr_call_arg["candidate_video_ids"] == ["L21_V001", "L21_V002"]
    assert asr_call_arg["top_k"] == 15
