from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aic2026.core.atomic import atomic_write_json
from aic2026.core.hashing import sha256_file
from aic2026.core.paths import PathContractError, normalize_relpath
from aic2026.evaluation.contract import EvalContractError, validate_eval_dataset


COMBINED_QUERY_PARSER_VERSION = "group-a-combined-v1"
_HEADER = re.compile(
    r"^===== (query-p3-(\d+)-(kis|qa|trake)\.txt) =====\s*$",
    flags=re.MULTILINE | re.IGNORECASE,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_combined_queries(text: str, *, expected_count: int = 35) -> list[dict[str, Any]]:
    matches = list(_HEADER.finditer(text))
    if len(matches) != expected_count:
        raise EvalContractError(
            f"Combined query file phải có đúng {expected_count} header, nhận được {len(matches)}"
        )

    queries: list[dict[str, Any]] = []
    ordinals: list[int] = []
    for index, match in enumerate(matches):
        ordinal = int(match.group(2))
        task_type = match.group(3).upper()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        query_text = text[start:end].strip("\r\n")
        if not query_text.strip():
            raise EvalContractError(f"Query {match.group(1)} không có nội dung")
        ordinals.append(ordinal)
        queries.append(
            {
                "query_id": Path(match.group(1)).stem,
                "query_type": task_type,
                "query_text": query_text,
                "question_text": None,
                "trap_category": "unclassified",
                "split": "dev",
                "label_status": "unlabeled_reference",
                "gt_video_id": None,
                "gt_frame_ranges": [],
                "gt_answer": None,
                "label_provenance": None,
            }
        )

    expected_ordinals = list(range(1, expected_count + 1))
    if ordinals != expected_ordinals:
        raise EvalContractError(
            f"Thứ tự query phải liên tục 1..{expected_count}; nhận được {ordinals}"
        )
    return queries


def import_combined_queries(
    source_path: str | Path,
    output_path: str | Path,
    *,
    dataset_id: str,
    dataset_version: str,
    source_relpath: str | None = None,
    expected_sha256: str | None = None,
    expected_count: int = 35,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = Path(source_path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvalContractError(f"Không đọc được combined query file UTF-8: {exc}") from exc

    source_hash = sha256_file(source)
    if expected_sha256 is not None and source_hash != expected_sha256.lower():
        raise EvalContractError(
            f"Checksum nguồn không khớp: expected={expected_sha256.lower()}, actual={source_hash}"
        )
    try:
        normalized_source = normalize_relpath(source_relpath or source.name)
    except PathContractError as exc:
        raise EvalContractError(f"source_relpath không hợp lệ: {exc}") from exc

    raw_dataset = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "source_provenance": {
            "source_relpath": normalized_source,
            "source_sha256": source_hash,
            "imported_at": _utc_now(),
            "parser_version": COMBINED_QUERY_PARSER_VERSION,
        },
        "queries": parse_combined_queries(text, expected_count=expected_count),
    }
    dataset, summary = validate_eval_dataset(raw_dataset)
    atomic_write_json(output_path, dataset)
    return dataset, summary
