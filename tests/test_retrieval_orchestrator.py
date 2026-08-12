from __future__ import annotations

import time

import pytest

from aic2026.retrieval.contract import validate_search_response
from aic2026.retrieval.orchestrator import OrchestratorConfig, SearchOrchestrator
from aic2026.retrieval.providers.base import ProviderCapability, ProviderHit, ProviderQuery


class FakeProvider:
    def __init__(self, name, hits=(), *, status="OK", fail=False, delay=0.0):
        self.name = name
        self.hits = list(hits)
        self.status = status
        self.fail = fail
        self.delay = delay
        self.queries = []

    def capabilities(self):
        return ProviderCapability(self.name, self.status, None if self.status == "OK" else "NOT_READY", f"{self.name}-v1", {f"{self.name}_sha256": "a" * 64}, {}, {"items": len(self.hits)})

    def search(self, query: ProviderQuery):
        self.queries.append(query)
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("synthetic failure")
        return list(self.hits[:query.top_k])


def _asr(eid="A1", video="V1", anchor=3.0, rank=1):
    return ProviderHit("asr", eid, video, rank, anchor - 1, anchor + 1, anchor, -2.0, "bm25_lower_is_better", "asr-v1", {"segment_id": eid, "text": "thành phố"}, f"video/{video}.mp4", {})


def _visual(eid="V1:1", video="V1", anchor=3.0, rank=1):
    ordinal = int(eid.split(":")[-1])
    return ProviderHit("visual", eid, video, rank, anchor, anchor, anchor, 0.4, "cosine_ip_higher_is_better", "visual-v1", {"embedding_id": 1, "keyframe_id": eid, "csv_n": ordinal, "clip_row": ordinal - 1, "frame_idx": 75, "pts_time": anchor, "keyframe_relpath": f"keyframes/{video}/{ordinal:03d}.jpg"}, None, {})


def _request(strategy="auto", lanes=("visual", "asr"), mode="KIS", limit=20):
    return {"contract_version": "retrieval.v1", "request_id": "test-request", "mode": mode, "query_text": "thành phố", "mode_context": {}, "routing": {"strategy": strategy, "enabled_lanes": list(lanes), "object_match": "soft"}, "filters": {"video_ids": [], "start_sec": None, "end_sec": None}, "result_limit": limit}


def test_auto_runs_all_ok_providers_and_is_deterministic():
    providers = {"asr": FakeProvider("asr", [_asr()]), "visual": FakeProvider("visual", [_visual()])}
    orchestrator = SearchOrchestrator(providers, config=OrchestratorConfig(per_lane_top_k=7))
    try:
        first = orchestrator.search(_request())
        second = orchestrator.search(_request())
    finally:
        orchestrator.close()
    assert first["status"] == "OK"
    assert first["route"]["reason"] == "baseline_all_available_v1"
    assert first["route"]["selected_lanes"] == ["visual", "asr"]
    assert first["providers"]["ocr"]["status"] == "UNAVAILABLE"
    assert first["providers"]["object"]["status"] == "UNAVAILABLE"
    assert first["results"] == second["results"]
    assert providers["asr"].queries[0].top_k == 7
    assert set(first["latency_ms"]["capabilities"]) == {"asr", "visual"}
    assert set(first["latency_ms"]["providers"]) == {"asr", "visual"}
    assert validate_search_response(first) == first


@pytest.mark.parametrize("mode", ["KIS", "QA", "TRAKE"])
@pytest.mark.parametrize("lane", ["asr", "visual"])
def test_manual_overrides_and_modes(mode, lane):
    providers = {"asr": FakeProvider("asr", [_asr()]), "visual": FakeProvider("visual", [_visual()])}
    orchestrator = SearchOrchestrator(providers)
    try:
        response = orchestrator.search(_request("manual", (lane,), mode=mode))
    finally:
        orchestrator.close()
    assert response["route"]["reason"] == "manual_override_v1"
    assert response["route"]["executed_lanes"] == [lane]
    other = "visual" if lane == "asr" else "asr"
    assert response["providers"][other]["status"] == "SKIPPED"
    assert providers[other].queries == []


def test_unavailable_manual_lanes_do_not_mock_or_crash_successful_lane():
    providers = {"asr": FakeProvider("asr", [_asr()]), "visual": FakeProvider("visual", status="UNAVAILABLE")}
    orchestrator = SearchOrchestrator(providers)
    try:
        response = orchestrator.search(_request("manual", ("asr", "visual", "ocr", "object")))
    finally:
        orchestrator.close()
    assert response["status"] == "PARTIAL"
    assert len(response["results"]) == 1
    assert response["providers"]["visual"]["status"] == "UNAVAILABLE"
    assert response["providers"]["ocr"]["count"] == 0
    assert response["providers"]["object"]["count"] == 0


def test_only_unavailable_lane_returns_explicit_error():
    orchestrator = SearchOrchestrator({"asr": FakeProvider("asr", [_asr()])})
    try:
        response = orchestrator.search(_request("manual", ("ocr",)))
    finally:
        orchestrator.close()
    assert response["status"] == "ERROR"
    assert response["results"] == []
    assert response["providers"]["ocr"]["status"] == "UNAVAILABLE"


def test_temporal_filter_boundaries_are_inclusive():
    provider = FakeProvider("asr", [_asr("A1", anchor=3.0), _asr("A2", anchor=4.0, rank=2)])
    request = _request("manual", ("asr",))
    request["filters"] = {"video_ids": [], "start_sec": 3.0, "end_sec": 3.0}
    orchestrator = SearchOrchestrator({"asr": provider})
    try:
        response = orchestrator.search(request)
    finally:
        orchestrator.close()
    evidence_ids = [evidence["evidence_id"] for window in response["results"] for evidence in window["evidence"]]
    assert evidence_ids == ["A1"]


def test_one_failure_is_partial_and_both_failure_is_error():
    one = SearchOrchestrator({"asr": FakeProvider("asr", [_asr()]), "visual": FakeProvider("visual", fail=True)})
    try:
        partial = one.search(_request())
    finally:
        one.close()
    assert partial["status"] == "PARTIAL" and partial["providers"]["visual"]["status"] == "ERROR"
    both = SearchOrchestrator({"asr": FakeProvider("asr", fail=True), "visual": FakeProvider("visual", fail=True)})
    try:
        error = both.search(_request())
    finally:
        both.close()
    assert error["status"] == "ERROR" and error["results"] == []


def test_provider_timeout_is_partial_and_explicit():
    orchestrator = SearchOrchestrator({"asr": FakeProvider("asr", [_asr()]), "visual": FakeProvider("visual", delay=0.2)}, config=OrchestratorConfig(provider_timeout_sec=0.03))
    try:
        response = orchestrator.search(_request())
    finally:
        orchestrator.close()
    assert response["status"] == "PARTIAL"
    assert response["providers"]["visual"]["reason"] == "PROVIDER_TIMEOUT"
    assert "VISUAL_TIMEOUT" in response["warnings"]


@pytest.mark.parametrize("limit", [0, 101])
def test_request_caps_fail_closed(limit):
    orchestrator = SearchOrchestrator({"asr": FakeProvider("asr")})
    try:
        with pytest.raises(ValueError, match="result_limit"):
            orchestrator.search(_request(limit=limit))
    finally:
        orchestrator.close()
