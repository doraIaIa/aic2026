import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from aic2026.retrieval.contract import (
    CONTRACT_DIR,
    CONTRACT_VERSION,
    POLICY_VERSION,
    RetrievalContractError,
    compile_product_fts_query,
    contract_sha256,
    load_contract_schema,
    load_retrieval_policy,
    media_capability,
    validate_search_request,
    validate_search_response,
)


def _fixture(name: str):
    return json.loads((CONTRACT_DIR / "fixtures" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["request_kis.json", "request_qa.json", "request_trake.json"])
def test_request_fixtures_validate_deterministically(name):
    raw = _fixture(name)
    first = validate_search_request(raw)
    second = validate_search_request(json.loads(json.dumps(raw, ensure_ascii=False, sort_keys=True)))
    assert first == second
    assert first["contract_version"] == CONTRACT_VERSION


@pytest.mark.parametrize(
    "name",
    ["response_asr_only.json", "response_visual_only.json", "response_fused.json", "response_optional_unavailable.json"],
)
def test_response_fixtures_validate(name):
    raw = _fixture(name)
    assert validate_search_response(raw) == raw


def test_schema_and_policy_versions_are_locked():
    schema = load_contract_schema()
    policy = load_retrieval_policy()
    assert schema["$defs"]["SearchRequest"]["properties"]["contract_version"]["const"] == CONTRACT_VERSION
    assert policy["policy_version"] == POLICY_VERSION
    assert policy["fusion"]["collapse_per_lane"] == "best_rank_per_evidence_window"
    assert policy["fusion"]["rrf_k"] == 60
    assert policy["windowing"]["max_window_span_sec"] == 12.0
    assert policy["windowing"]["prevent_transitive_chain_merge"] is True
    assert len(contract_sha256()) == 64


def test_product_fts_policy_is_literal_all_token_and_keeps_phrase():
    assert compile_product_fts_query('thành phố "hồ chí minh"') == '"thành" AND "phố" AND "hồ chí minh"'
    assert compile_product_fts_query("bão OR lũ*") == '"bão" AND "OR" AND "lũ"'


@pytest.mark.parametrize("query", ['"phrase chưa đóng', "***"])
def test_product_fts_policy_rejects_malformed_query_safely(query):
    with pytest.raises(RetrievalContractError):
        compile_product_fts_query(query)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(query_text=""),
        lambda r: r.update(result_limit=101),
        lambda r: r.update(contract_version="retrieval.v2"),
        lambda r: r["routing"].update(enabled_lanes=["asr", "asr"]),
        lambda r: r["filters"].update(start_sec=10, end_sec=5),
        lambda r: r.update(raw_fts="text OR *"),
    ],
)
def test_malformed_requests_fail_closed(mutation):
    raw = _fixture("request_kis.json")
    mutation(raw)
    with pytest.raises(RetrievalContractError):
        validate_search_request(raw)


def test_temporal_anchor_never_opens_submit_gate():
    raw = _fixture("response_asr_only.json")
    raw["results"][0]["representative"]["submit_valid"] = True
    with pytest.raises(RetrievalContractError, match="Temporal anchor"):
        validate_search_response(raw)


def test_fusion_must_use_best_rank_per_lane():
    raw = _fixture("response_fused.json")
    raw["results"][0]["fusion"]["best_rank_by_lane"]["asr"] = 4
    with pytest.raises(RetrievalContractError, match="best rank"):
        validate_search_response(raw)


def test_window_span_blocks_transitive_chain_growth():
    raw = _fixture("response_fused.json")
    raw["results"][0]["end_sec"] = raw["results"][0]["start_sec"] + 12.001
    with pytest.raises(RetrievalContractError, match="12 giây"):
        validate_search_response(raw)


def test_unavailable_provider_cannot_claim_results():
    raw = _fixture("response_optional_unavailable.json")
    raw["providers"]["ocr"]["count"] = 1
    with pytest.raises(RetrievalContractError, match="UNAVAILABLE"):
        validate_search_response(raw)


def test_absolute_media_paths_are_rejected():
    raw = _fixture("response_visual_only.json")
    raw["results"][0]["sources"]["video_relpath"] = "F:/private/video.mp4"
    with pytest.raises(RetrievalContractError, match="absolute|drive-prefixed"):
        validate_search_response(raw)


def test_media_capability_hides_root(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AIC_MEDIA_ROOT", raising=False)
    assert media_capability()["status"] == "MEDIA_UNAVAILABLE"
    assert media_capability(tmp_path)["status"] == "AVAILABLE"
    assert media_capability(tmp_path)["root_exposed"] is False


def test_frontend_type_generator_embeds_contract_checksum(tmp_path: Path):
    output = tmp_path / "retrieval-contract.generated.ts"
    subprocess.run(
        [sys.executable, "scripts/generate_retrieval_contract_types.py", "--out", str(output)],
        check=True,
    )
    generated = output.read_text(encoding="utf-8")
    assert f"contract_sha256: {contract_sha256()}" in generated
    assert f'RETRIEVAL_CONTRACT_VERSION = "{CONTRACT_VERSION}"' in generated
