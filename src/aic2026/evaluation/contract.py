from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from aic2026.core.paths import PathContractError, normalize_relpath


EVAL_SCHEMA_VERSION = 1
QUERY_TYPES = {"KIS", "QA", "TRAKE"}
TRAP_CATEGORIES = {
    "visual", "micro_moment", "ocr_only", "asr_only",
    "event_chain", "count", "spatial_motion", "unclassified",
}
SPLITS = {"dev", "holdout"}
LABEL_STATUSES = {"labeled", "unlabeled_reference"}


class EvalContractError(ValueError):
    """Dữ liệu evaluation vi phạm contract đã khóa."""


def _nonempty_string(value: Any, field: str, query_id: str = "") -> str:
    if not isinstance(value, str) or not value.strip():
        prefix = f"Query {query_id}: " if query_id else ""
        raise EvalContractError(f"{prefix}{field} phải là chuỗi không rỗng")
    return value.strip()


def _validate_ranges(value: Any, query_id: str) -> list[dict[str, int]]:
    if not isinstance(value, list) or not value:
        raise EvalContractError(f"Query {query_id}: gt_frame_ranges phải là danh sách không rỗng")
    normalized: list[dict[str, int]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise EvalContractError(f"Query {query_id}: GT range {index} không phải object")
        start = item.get("start_frame")
        end = item.get("end_frame")
        if type(start) is not int or type(end) is not int or start < 0 or end < start:
            raise EvalContractError(
                f"Query {query_id}: GT range {index} phải có 0 <= start_frame <= end_frame"
            )
        normalized.append({"start_frame": start, "end_frame": end})
    return normalized


def _validate_source_provenance(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise EvalContractError("source_provenance phải là object")
    try:
        source_relpath = normalize_relpath(
            _nonempty_string(value.get("source_relpath"), "source_provenance.source_relpath")
        )
    except PathContractError as exc:
        raise EvalContractError(f"source_provenance.source_relpath không hợp lệ: {exc}") from exc
    source_sha256 = _nonempty_string(
        value.get("source_sha256"), "source_provenance.source_sha256"
    ).lower()
    if re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
        raise EvalContractError("source_provenance.source_sha256 phải là SHA-256 hợp lệ")
    imported_at = _nonempty_string(value.get("imported_at"), "source_provenance.imported_at")
    try:
        datetime.fromisoformat(imported_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvalContractError("source_provenance.imported_at phải là ISO-8601 hợp lệ") from exc
    parser_version = _nonempty_string(
        value.get("parser_version"), "source_provenance.parser_version"
    )
    return {
        "source_relpath": source_relpath,
        "source_sha256": source_sha256,
        "imported_at": imported_at,
        "parser_version": parser_version,
    }


def validate_query(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise EvalContractError("Mỗi query phải là một object")
    query_id = _nonempty_string(raw.get("query_id"), "query_id")
    query_type = raw.get("query_type")
    trap_category = raw.get("trap_category")
    split = raw.get("split")
    label_status = raw.get("label_status")
    if query_type not in QUERY_TYPES:
        raise EvalContractError(f"Query {query_id}: query_type không được hỗ trợ: {query_type}")
    if trap_category not in TRAP_CATEGORIES:
        raise EvalContractError(f"Query {query_id}: trap_category không hợp lệ: {trap_category}")
    if split not in SPLITS:
        raise EvalContractError(f"Query {query_id}: split phải là dev hoặc holdout")
    if label_status not in LABEL_STATUSES:
        raise EvalContractError(f"Query {query_id}: label_status không hợp lệ")

    query = {
        "query_id": query_id,
        "query_type": query_type,
        "query_text": _nonempty_string(raw.get("query_text"), "query_text", query_id),
        "question_text": raw.get("question_text"),
        "trap_category": trap_category,
        "split": split,
        "label_status": label_status,
        "gt_video_id": raw.get("gt_video_id"),
        "gt_frame_ranges": raw.get("gt_frame_ranges") or [],
        "gt_answer": raw.get("gt_answer"),
        "label_provenance": raw.get("label_provenance"),
    }
    if query["question_text"] is not None:
        query["question_text"] = _nonempty_string(query["question_text"], "question_text", query_id)

    if label_status == "unlabeled_reference":
        if query["gt_video_id"] is not None or query["gt_frame_ranges"] or query["gt_answer"] is not None:
            raise EvalContractError(f"Query {query_id}: unlabeled_reference không được chứa ground truth")
        if query["label_provenance"] is not None:
            raise EvalContractError(f"Query {query_id}: unlabeled_reference không được có label_provenance")
        return query

    provenance = query["label_provenance"]
    if not isinstance(provenance, dict):
        raise EvalContractError(f"Query {query_id}: labeled query phải có label_provenance")
    _nonempty_string(provenance.get("source"), "label_provenance.source", query_id)
    if query_type in {"KIS", "TRAKE"}:
        query["gt_video_id"] = _nonempty_string(query["gt_video_id"], "gt_video_id", query_id)
        query["gt_frame_ranges"] = _validate_ranges(query["gt_frame_ranges"], query_id)
    if query_type == "QA":
        query["gt_answer"] = _nonempty_string(query["gt_answer"], "gt_answer", query_id)
    return query


def validate_eval_dataset(raw: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(raw, dict):
        raise EvalContractError("Eval dataset phải là một JSON object")
    if raw.get("schema_version") != EVAL_SCHEMA_VERSION:
        raise EvalContractError(f"schema_version phải bằng {EVAL_SCHEMA_VERSION}")
    dataset_id = _nonempty_string(raw.get("dataset_id"), "dataset_id")
    dataset_version = _nonempty_string(raw.get("dataset_version"), "dataset_version")
    source_provenance = _validate_source_provenance(raw.get("source_provenance"))
    queries_raw = raw.get("queries")
    if not isinstance(queries_raw, list) or not queries_raw:
        raise EvalContractError("queries phải là danh sách không rỗng")
    queries = [validate_query(item) for item in queries_raw]
    query_ids = [item["query_id"] for item in queries]
    if len(query_ids) != len(set(query_ids)):
        raise EvalContractError("query_id phải duy nhất trong dataset")

    labeled = [item for item in queries if item["label_status"] == "labeled"]
    holdout_labeled = [item for item in labeled if item["split"] == "holdout"]
    warnings: list[str] = []
    if len(labeled) >= 4:
        ratio = len(holdout_labeled) / len(labeled)
        if not 0.20 <= ratio <= 0.30:
            warnings.append("Tỷ lệ HOLDOUT labeled nằm ngoài khoảng khuyến nghị 20–30%")
    normalized = {
        "schema_version": EVAL_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "queries": queries,
    }
    if source_provenance is not None:
        normalized["source_provenance"] = source_provenance
    summary = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "total": len(queries),
        "labeled": len(labeled),
        "unlabeled": len(queries) - len(labeled),
        "dev": sum(item["split"] == "dev" for item in queries),
        "holdout": sum(item["split"] == "holdout" for item in queries),
        "warnings": warnings,
    }
    return normalized, summary


def load_eval_dataset(path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalContractError(f"Không đọc được eval dataset: {exc}") from exc
    return validate_eval_dataset(raw)
