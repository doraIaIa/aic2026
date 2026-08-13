from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from aic2026.core.paths import PathContractError, normalize_relpath


CONTRACT_VERSION = "retrieval.v1"
POLICY_VERSION = "retrieval-policy-v1"
LANES = ("visual", "asr", "ocr", "object")
MODES = ("KIS", "QA", "TRAKE")
CONTRACT_DIR = Path(__file__).parent / "contracts" / "v1"


class RetrievalContractError(ValueError):
    """Payload retrieval vi phạm contract v1."""


ASR_STRATEGIES = ("strict_and_v1", "relaxed_v1")
DEFAULT_ASR_STRATEGY = "relaxed_v1"
EVAL_ASR_STRATEGY = "strict_and_v1"

# Vietnamese query boilerplate / stop words — low-value scaffolding tokens
_VIETNAMESE_STOPWORDS = frozenset({
    "đoạn", "video", "hình", "ảnh", "cảnh", "cho", "biết", "hỏi",
    "trong", "có", "là", "một", "của", "và", "các", "những",
    "này", "đó", "được", "với", "về", "từ", "đến", "hay",
    "hoặc", "nào", "gì", "bao", "nhiêu", "thì", "rằng", "nếu",
    "đây", "đã", "đang", "sẽ", "vẫn", "còn", "rất", "quá",
    "cũng", "nhưng", "mà", "tuy", "vì", "nên", "phải",
    "không", "chưa", "bị", "chỉ", "lại", "ra", "lên", "xuống",
    "vào", "để", "theo", "trên", "dưới", "sau", "trước",
    "khi", "thấy", "đầu", "tiên", "cuối", "cùng",
    "kế", "tiếp", "ở", "tại", "qua",
})


def _extract_tokens(value: str) -> tuple[list[str], list[str]]:
    """Extract quoted phrases and individual word tokens from a query string.

    Returns (phrases, tokens) where phrases are "quoted" substrings
    and tokens are individual words from the remaining text.
    """
    phrases: list[str] = []
    tokens: list[str] = []
    for match in re.finditer(r'"([^"\r\n]+)"|([^\s"]+)', value):
        phrase, token = match.groups()
        if phrase is not None:
            normalized = " ".join(phrase.split())
            if normalized:
                phrases.append(normalized)
            continue
        for literal in re.findall(r"\w+", token, flags=re.UNICODE):
            tokens.append(literal)
    return phrases, tokens


def compile_strict_and_fts_query(query: str) -> str:
    """strict_and_v1: every token AND-joined, quoted phrases preserved.

    This is the original evaluation baseline strategy.
    """
    value = _string(query, "query_text")
    if value.count('"') % 2:
        raise RetrievalContractError("Query phrase thiếu dấu ngoặc kép đóng")
    # Keep the historical source-order semantics exactly.  In particular, a
    # quoted phrase stays where the operator placed it instead of being moved
    # before all individual tokens.
    terms: list[str] = []
    for match in re.finditer(r'"([^"\r\n]+)"|([^\s"]+)', value):
        phrase, token = match.groups()
        if phrase is not None:
            normalized = " ".join(phrase.split())
            if normalized:
                terms.append(f'"{normalized}"')
            continue
        for literal in re.findall(r"\w+", token, flags=re.UNICODE):
            terms.append(f'"{literal}"')
    if not terms:
        raise RetrievalContractError("Query không có token literal hợp lệ")
    return " AND ".join(terms)


# Backward-compatible alias — existing code uses this name
compile_product_fts_query = compile_strict_and_fts_query


def compile_relaxed_fts_query(query: str, *, max_tokens: int = 12) -> str:
    """relaxed_v1: OR-based with stopword removal and phrase boosting.

    Deterministic, no LLM. Designed for product natural-language queries.

    Strategy:
    1. Extract quoted phrases verbatim.
    2. Extract word tokens and remove generic Vietnamese scaffolding.
    3. Detect potential multi-word named entities (consecutive capitalized/
       proper-noun-like tokens) — not implemented for simplicity; rely on
       user quotes for now.
    4. Build: phrase matches OR content tokens, capped at max_tokens.
    """
    value = _string(query, "query_text")
    if value.count('"') % 2:
        raise RetrievalContractError("Query phrase thiếu dấu ngoặc kép đóng")
    phrases, raw_tokens = _extract_tokens(value)

    # Remove stopwords from individual tokens
    content_tokens = [t for t in raw_tokens if t.lower() not in _VIETNAMESE_STOPWORDS]

    # Cap tokens to prevent query explosion
    content_tokens = content_tokens[:max_tokens]

    if not content_tokens and not phrases:
        raise RetrievalContractError("Query không có token literal hợp lệ")

    # Build OR expression: phrases get priority, then individual tokens
    terms: list[str] = []
    for p in phrases:
        terms.append(f'"{p}"')
    for t in content_tokens:
        terms.append(f'"{t}"')

    return " OR ".join(terms)


def compile_fts_query(query: str, *, strategy: str = DEFAULT_ASR_STRATEGY) -> str:
    """Dispatch FTS query compilation to the named strategy."""
    if strategy == "strict_and_v1":
        return compile_strict_and_fts_query(query)
    if strategy == "relaxed_v1":
        return compile_relaxed_fts_query(query)
    raise RetrievalContractError(f"ASR strategy không hợp lệ: {strategy}")


def load_contract_schema() -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / "retrieval.schema.json").read_text(encoding="utf-8"))


def load_retrieval_policy() -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / "policy.json").read_text(encoding="utf-8"))


def contract_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted(CONTRACT_DIR.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RetrievalContractError(f"{field} phải là object")
    return value


def _string(value: Any, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RetrievalContractError(f"{field} phải là chuỗi không rỗng")
    if len(value) > maximum:
        raise RetrievalContractError(f"{field} vượt quá {maximum} ký tự")
    return value.strip()


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise RetrievalContractError(f"{field} phải là số không âm")
    return float(value)


def _reject_unknown(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise RetrievalContractError(f"{field} chứa field không hỗ trợ: {', '.join(unknown)}")


def validate_search_request(raw: Any) -> dict[str, Any]:
    request = _object(raw, "SearchRequest")
    allowed = {"contract_version", "request_id", "mode", "query_text", "mode_context", "routing", "filters", "result_limit"}
    _reject_unknown(request, allowed, "SearchRequest")
    if request.get("contract_version") != CONTRACT_VERSION:
        raise RetrievalContractError(f"contract_version phải bằng {CONTRACT_VERSION}")
    request_id = _string(request.get("request_id"), "request_id", maximum=128)
    if re.fullmatch(r"[A-Za-z0-9._:-]+", request_id) is None:
        raise RetrievalContractError("request_id chứa ký tự không hợp lệ")
    mode = request.get("mode")
    if mode not in MODES:
        raise RetrievalContractError("mode phải là KIS, QA hoặc TRAKE")
    query_text = _string(request.get("query_text"), "query_text")
    routing = _object(request.get("routing"), "routing")
    _reject_unknown(routing, {"strategy", "enabled_lanes", "object_match"}, "routing")
    if routing.get("strategy") not in {"auto", "manual"}:
        raise RetrievalContractError("routing.strategy không hợp lệ")
    lanes = routing.get("enabled_lanes")
    if not isinstance(lanes, list) or not lanes or len(lanes) != len(set(lanes)) or any(lane not in LANES for lane in lanes):
        raise RetrievalContractError("routing.enabled_lanes phải là danh sách lane duy nhất, không rỗng")
    if routing.get("object_match") not in {"soft", "exact_and"}:
        raise RetrievalContractError("routing.object_match không hợp lệ")
    filters = _object(request.get("filters"), "filters")
    _reject_unknown(filters, {"video_ids", "start_sec", "end_sec"}, "filters")
    video_ids = filters.get("video_ids", [])
    if not isinstance(video_ids, list) or len(video_ids) > 100 or any(not isinstance(item, str) or not item.strip() for item in video_ids):
        raise RetrievalContractError("filters.video_ids không hợp lệ")
    if len(video_ids) != len(set(video_ids)):
        raise RetrievalContractError("filters.video_ids không được trùng")
    start = filters.get("start_sec")
    end = filters.get("end_sec")
    if start is not None:
        start = _number(start, "filters.start_sec")
    if end is not None:
        end = _number(end, "filters.end_sec")
    if start is not None and end is not None and end < start:
        raise RetrievalContractError("filters.end_sec phải >= start_sec")
    limit = request.get("result_limit")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise RetrievalContractError("result_limit phải nằm trong 1..100")
    context = request.get("mode_context", {})
    if not isinstance(context, dict):
        raise RetrievalContractError("mode_context phải là object")
    return {"contract_version": CONTRACT_VERSION, "request_id": request_id, "mode": mode, "query_text": query_text, "mode_context": context, "routing": {"strategy": routing["strategy"], "enabled_lanes": list(lanes), "object_match": routing["object_match"]}, "filters": {"video_ids": list(video_ids), "start_sec": start, "end_sec": end}, "result_limit": limit}


def _validate_evidence_window(window: Any) -> None:
    item = _object(window, "EvidenceWindow")
    required = {"evidence_window_id", "video_id", "start_sec", "end_sec", "representative", "evidence", "fusion", "sources", "provenance"}
    if set(item) != required:
        raise RetrievalContractError("EvidenceWindow phải có đúng các field contract v1")
    _string(item["evidence_window_id"], "evidence_window_id")
    _string(item["video_id"], "video_id")
    start = _number(item["start_sec"], "start_sec")
    end = _number(item["end_sec"], "end_sec")
    if end < start or end - start > 12.0:
        raise RetrievalContractError("EvidenceWindow phải có 0 <= span <= 12 giây")
    representative = _object(item["representative"], "representative")
    kind = representative.get("kind")
    if kind not in {"visual_keyframe", "dense_frame", "temporal_anchor"}:
        raise RetrievalContractError("representative.kind không hợp lệ")
    if representative.get("operator_confirmation_required") is not True:
        raise RetrievalContractError("Mọi frame submit cần operator confirmation")
    submit_valid = representative.get("submit_valid")
    if type(submit_valid) is not bool:
        raise RetrievalContractError("representative.submit_valid phải là boolean")
    if kind == "temporal_anchor" and submit_valid:
        raise RetrievalContractError("Temporal anchor không được submit_valid")
    if submit_valid and (kind not in {"visual_keyframe", "dense_frame"} or representative.get("frame_idx") is None):
        raise RetrievalContractError("submit_valid cần visual/dense frame có mapping")
    _number(representative.get("timestamp_sec"), "representative.timestamp_sec")
    if kind == "visual_keyframe" and submit_valid and not representative.get("keyframe_id"):
        raise RetrievalContractError("Visual submit_valid cần keyframe_id")
    evidence = item["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise RetrievalContractError("EvidenceWindow.evidence phải không rỗng")
    ids: set[str] = set()
    best: dict[str, int] = {}
    for entry in evidence:
        entry = _object(entry, "evidence")
        evidence_id = _string(entry.get("evidence_id"), "evidence_id")
        if evidence_id in ids:
            raise RetrievalContractError("evidence_id phải duy nhất trong window")
        ids.add(evidence_id)
        lane = entry.get("modality")
        rank = entry.get("rank")
        if lane not in LANES or type(rank) is not int or rank < 1:
            raise RetrievalContractError("evidence modality/rank không hợp lệ")
        anchor = _number(entry.get("anchor_sec"), "evidence.anchor_sec")
        if not start <= anchor <= end:
            raise RetrievalContractError("evidence anchor phải nằm trong EvidenceWindow")
        _string(entry.get("score_kind"), "evidence.score_kind")
        _string(entry.get("artifact_version"), "evidence.artifact_version")
        if entry.get("raw_score") is not None and (isinstance(entry["raw_score"], bool) or not isinstance(entry["raw_score"], (int, float))):
            raise RetrievalContractError("evidence.raw_score phải là number hoặc null")
        _object(entry.get("payload"), "evidence.payload")
        best[lane] = min(rank, best.get(lane, rank))
    fusion = _object(item["fusion"], "fusion")
    if fusion.get("method") != "rrf" or fusion.get("best_rank_by_lane") != best:
        raise RetrievalContractError("fusion phải collapse best rank theo lane trước RRF")
    expected_rrf = sum(1.0 / (60 + rank) for rank in best.values())
    actual_rrf = fusion.get("rrf_score")
    if not isinstance(actual_rrf, (int, float)) or abs(actual_rrf - expected_rrf) > 1e-9:
        raise RetrievalContractError("fusion.rrf_score không khớp equal-weight RRF k=60")
    provenance = _object(item["provenance"], "provenance")
    if provenance.get("contract_version") != CONTRACT_VERSION or provenance.get("policy_version") != POLICY_VERSION:
        raise RetrievalContractError("provenance contract/policy version không hợp lệ")
    sources = _object(item["sources"], "sources")
    for field in ("video_relpath", "keyframe_relpath"):
        value = sources.get(field)
        if value is not None:
            try:
                normalize_relpath(_string(value, f"sources.{field}"))
            except PathContractError as exc:
                raise RetrievalContractError(str(exc)) from exc
    media_url = sources.get("media_url")
    if media_url is not None and (not isinstance(media_url, str) or not media_url.startswith("/api/")):
        raise RetrievalContractError("media_url phải là URL API tương đối hoặc null")


def validate_search_response(raw: Any) -> dict[str, Any]:
    response = _object(raw, "SearchResponse")
    required = {"contract_version", "request_id", "status", "route", "providers", "results", "latency_ms", "warnings"}
    if set(response) != required or response.get("contract_version") != CONTRACT_VERSION:
        raise RetrievalContractError("SearchResponse không đúng field/version v1")
    _string(response["request_id"], "request_id")
    if response["status"] not in {"OK", "PARTIAL", "ERROR", "BLOCKED_BY_SCORING_CONTRACT"}:
        raise RetrievalContractError("response.status không hợp lệ")
    results = response["results"]
    if not isinstance(results, list) or len(results) > 100:
        raise RetrievalContractError("results phải là list tối đa 100")
    for window in results:
        _validate_evidence_window(window)
    providers = _object(response["providers"], "providers")
    for lane, state in providers.items():
        if lane not in LANES:
            raise RetrievalContractError("provider lane không hợp lệ")
        state = _object(state, f"providers.{lane}")
        if state.get("status") not in {"AVAILABLE", "UNAVAILABLE", "ERROR", "SKIPPED", "MEDIA_UNAVAILABLE"}:
            raise RetrievalContractError("provider status không hợp lệ")
        if type(state.get("count")) is not int or state["count"] < 0:
            raise RetrievalContractError("provider count phải là số nguyên không âm")
        if state.get("status") == "UNAVAILABLE" and state.get("count") != 0:
            raise RetrievalContractError("Provider UNAVAILABLE không được có kết quả")
    _number(_object(response["latency_ms"], "latency_ms").get("total"), "latency_ms.total")
    if not isinstance(response["warnings"], list) or any(not isinstance(item, str) for item in response["warnings"]):
        raise RetrievalContractError("warnings phải là list string")
    return response


def media_capability(configured_root: str | Path | None = None) -> dict[str, Any]:
    candidate = os.getenv("AIC_MEDIA_ROOT") or configured_root
    try:
        available = bool(candidate and Path(candidate).is_dir())
        reason = None if available else "MEDIA_ROOT_NOT_MOUNTED"
    except OSError as exc:
        available = False
        reason = f"MEDIA_ROOT_INACCESSIBLE: {type(exc).__name__}"
    return {
        "status": "AVAILABLE" if available else "MEDIA_UNAVAILABLE",
        "reason": reason,
        "read_only": True,
        "root_exposed": False,
    }
