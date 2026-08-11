from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.core.hashing import sha256_file
from aic2026.evaluation.contract import load_eval_dataset
from aic2026.evaluation.runner import EvalIntegrityError, validate_eval_run_artifact
from aic2026.jobs.artifact import read_valid_jsonl_prefix


REVIEW_COLUMNS = (
    "query_id", "task_type", "query_text", "rank", "video_id", "frame_idx",
    "keyframe_id", "pts_time", "score", "stable_id", "csv_n", "clip_row",
    "keyframe_relpath",
)
FAILURE_COLUMNS = (
    "query_id", "task_type", "query_text", "status", "error_type", "error", "latency_ms",
)


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _csv_row_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return sum(1 for _ in csv.DictReader(stream))


def validate_candidate_review_artifact(
    review_dir: str | Path,
) -> tuple[bool, list[str], dict[str, Any] | None]:
    root = Path(review_dir)
    errors: list[str] = []
    try:
        marker = json.loads((root / "DONE.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"DONE.json không đọc được: {exc}"], None
    if marker.get("schema_version") != 1 or marker.get("task") != "eval_candidate_review":
        errors.append("DONE.json sai schema hoặc task")
    for file_field, hash_field in (
        ("candidate_file", "candidate_sha256"),
        ("failure_file", "failure_sha256"),
    ):
        path = root / str(marker.get(file_field, ""))
        if not path.is_file():
            errors.append(f"Thiếu {file_field}")
        elif sha256_file(path) != marker.get(hash_field):
            errors.append(f"Checksum {file_field} không khớp")
    if type(marker.get("candidate_count")) is not int or type(marker.get("failure_count")) is not int:
        errors.append("Count candidate/failure không hợp lệ")
    else:
        candidate_path = root / str(marker.get("candidate_file", ""))
        failure_path = root / str(marker.get("failure_file", ""))
        try:
            if candidate_path.is_file() and _csv_row_count(candidate_path) != marker["candidate_count"]:
                errors.append("Số dòng candidate không khớp marker")
            if failure_path.is_file() and _csv_row_count(failure_path) != marker["failure_count"]:
                errors.append("Số dòng failure không khớp marker")
        except (OSError, csv.Error) as exc:
            errors.append(f"Không kiểm tra được count CSV: {exc}")
    return not errors, errors, marker


def export_candidate_review(
    dataset_path: str | Path,
    run_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    dataset, _ = load_eval_dataset(dataset_path)
    dataset_hash = sha256_file(dataset_path)
    run_valid, run_errors, run_marker = validate_eval_run_artifact(run_dir)
    if not run_valid or run_marker is None:
        raise EvalIntegrityError(f"Evaluation run không hợp lệ: {run_errors}")
    if run_marker.get("input_manifest_sha256") != dataset_hash:
        raise EvalIntegrityError("Evaluation run không thuộc dataset đã cung cấp")

    target = Path(output_dir)
    if (target / "DONE.json").exists():
        valid, errors, marker = validate_candidate_review_artifact(target)
        if not valid:
            raise EvalIntegrityError(f"Review artifact đã tồn tại nhưng không hợp lệ: {errors}")
        if (
            marker.get("dataset_sha256") != dataset_hash
            or marker.get("run_output_sha256") != run_marker.get("output_sha256")
        ):
            raise EvalIntegrityError("Review artifact hoàn tất thuộc dataset/run khác")
        return marker or {}

    query_by_id = {query["query_id"]: query for query in dataset["queries"]}
    prediction_path = Path(run_dir) / str(run_marker["output_file"])
    records = read_valid_jsonl_prefix(prediction_path)
    candidate_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for record in records:
        query_id = record.get("query_id")
        query = query_by_id.get(query_id)
        if query is None:
            raise EvalIntegrityError(f"Run chứa query_id không có trong dataset: {query_id}")
        if record.get("status") != "OK":
            failure_rows.append(
                {
                    "query_id": query_id,
                    "task_type": query["query_type"],
                    "query_text": query["query_text"],
                    "status": record.get("status"),
                    "error_type": record.get("error_type"),
                    "error": record.get("error"),
                    "latency_ms": record.get("latency_ms"),
                }
            )
            continue
        for prediction in record.get("predictions", []):
            candidate_rows.append(
                {
                    "query_id": query_id,
                    "task_type": query["query_type"],
                    "query_text": query["query_text"],
                    "rank": prediction.get("rank"),
                    "video_id": prediction.get("video_id"),
                    "frame_idx": prediction.get("frame_idx"),
                    "keyframe_id": prediction.get("keyframe_id"),
                    "pts_time": prediction.get("pts_time"),
                    "score": prediction.get("score"),
                    "stable_id": prediction.get("stable_id", prediction.get("embedding_id")),
                    "csv_n": prediction.get("csv_n"),
                    "clip_row": prediction.get("clip_row"),
                    "keyframe_relpath": prediction.get("keyframe_relpath"),
                }
            )

    target.mkdir(parents=True, exist_ok=True)
    candidate_path = target / "candidate_review.csv"
    failure_path = target / "failure_sheet.csv"
    atomic_write_text(candidate_path, _csv_text(REVIEW_COLUMNS, candidate_rows), encoding="utf-8-sig")
    atomic_write_text(failure_path, _csv_text(FAILURE_COLUMNS, failure_rows), encoding="utf-8-sig")
    marker = {
        "schema_version": 1,
        "task": "eval_candidate_review",
        "dataset_sha256": dataset_hash,
        "run_output_sha256": run_marker["output_sha256"],
        "run_summary_sha256": run_marker["summary_sha256"],
        "candidate_file": candidate_path.name,
        "candidate_sha256": sha256_file(candidate_path),
        "candidate_count": len(candidate_rows),
        "failure_file": failure_path.name,
        "failure_sha256": sha256_file(failure_path),
        "failure_count": len(failure_rows),
        "query_count": len(records),
        "quality_status": run_marker.get("quality_status"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": run_marker.get("git_commit"),
        "git_dirty": run_marker.get("git_dirty"),
    }
    atomic_write_json(target / "DONE.json", marker)
    return marker
