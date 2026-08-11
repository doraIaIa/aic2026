from __future__ import annotations

import json
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.core.hashing import sha256_bytes, sha256_file
from aic2026.evaluation.contract import EvalContractError, load_eval_dataset
from aic2026.evaluation.scoring import aggregate_scores, score_query
from aic2026.jobs.artifact import append_jsonl, read_valid_jsonl_prefix


class EvalIntegrityError(RuntimeError):
    """Evaluation artifact hoặc M1 index không vượt qua kiểm tra integrity."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout)
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN", True


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def load_validated_index_artifact(index_dir: str | Path) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    root = Path(index_dir)
    try:
        marker = json.loads((root / "DONE.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalIntegrityError(f"Không đọc được M1 DONE.json: {exc}") from exc
    if marker.get("task") != "clip_faiss_index" or marker.get("schema_version") != 1:
        raise EvalIntegrityError("M1 marker không đúng task/schema")
    index_path = root / str(marker.get("index_file", ""))
    metadata_path = root / str(marker.get("metadata_file", ""))
    if not index_path.is_file() or not metadata_path.is_file():
        raise EvalIntegrityError("M1 index hoặc metadata bị thiếu")
    if sha256_file(index_path) != marker.get("index_sha256"):
        raise EvalIntegrityError("M1 index checksum không khớp")
    if sha256_file(metadata_path) != marker.get("metadata_sha256"):
        raise EvalIntegrityError("M1 metadata checksum không khớp")

    metadata: dict[int, dict[str, Any]] = {}
    with metadata_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                row = json.loads(line)
                embedding_id = int(row["embedding_id"])
                video_id = row["video_id"]
                frame_idx = row["frame_idx"]
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise EvalIntegrityError(f"Metadata M1 lỗi tại dòng {line_number}") from exc
            if embedding_id in metadata or not isinstance(video_id, str) or type(frame_idx) is not int:
                raise EvalIntegrityError(f"Metadata M1 trùng hoặc malformed tại dòng {line_number}")
            metadata[embedding_id] = row
    if len(metadata) != marker.get("processed_count") or len(metadata) != marker.get("expected_count"):
        raise EvalIntegrityError("Count metadata M1 không khớp marker")
    return marker, metadata


def _default_runtime(index_path: Path, model_name: str, pretrained: str, device: str):
    try:
        import faiss
        import open_clip
        import torch
    except ImportError as exc:
        raise RuntimeError("Baseline evaluation cần faiss-cpu và open-clip-torch") from exc
    index = faiss.read_index(str(index_path))
    model, _, _ = open_clip.create_model_and_transforms(model_name, pretrained=pretrained, device=device)
    tokenizer = open_clip.get_tokenizer(model_name)
    model.eval()

    def encode(text: str) -> np.ndarray:
        tokens = tokenizer([text]).to(device)
        with torch.no_grad():
            vector = model.encode_text(tokens)
            vector = vector / vector.norm(dim=-1, keepdim=True)
        return vector.cpu().numpy()[0].astype(np.float32)

    def search(vector: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        query = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        scores, ids = index.search(query, top_k)
        return [(int(item_id), float(score)) for item_id, score in zip(ids[0], scores[0]) if item_id >= 0]

    return encode, search


def _breakdown(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record[field])].append(record)
    return {name: aggregate_scores(rows, split=rows[0]["split"]) for name, rows in sorted(groups.items())}


def validate_eval_run_artifact(run_dir: str | Path) -> tuple[bool, list[str], dict[str, Any] | None]:
    root = Path(run_dir)
    errors: list[str] = []
    try:
        marker = json.loads((root / "DONE.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"DONE.json không đọc được: {exc}"], None
    if marker.get("schema_version") != 1 or marker.get("task") != "clip_baseline_evaluation":
        errors.append("DONE.json sai schema hoặc task")
    for file_field, hash_field in (("output_file", "output_sha256"), ("summary_file", "summary_sha256")):
        path = root / str(marker.get(file_field, ""))
        if not path.is_file():
            errors.append(f"Thiếu {file_field}")
        elif sha256_file(path) != marker.get(hash_field):
            errors.append(f"Checksum {file_field} không khớp")
    expected = marker.get("expected_items")
    processed = marker.get("processed_items")
    failed = marker.get("failed_items")
    if not all(type(value) is int for value in (expected, processed, failed)) or processed + failed != expected:
        errors.append("Count expected/processed/failed không hợp lệ")
    output_file = root / str(marker.get("output_file", ""))
    if output_file.is_file() and len(read_valid_jsonl_prefix(output_file)) != expected:
        errors.append("Số record predictions không khớp expected_items")
    return not errors, errors, marker


def run_baseline_evaluation(
    dataset_path: str | Path,
    index_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str,
    experiment_name: str,
    pipeline_description: str,
    model_name: str = "ViT-B-32",
    pretrained: str = "openai",
    device: str = "cpu",
    feature_flags: dict[str, bool] | None = None,
    encoder: Callable[[str], np.ndarray] | None = None,
    searcher: Callable[[np.ndarray, int], list[tuple[int, float]]] | None = None,
) -> dict[str, Any]:
    dataset, _ = load_eval_dataset(dataset_path)
    selected = [query for query in dataset["queries"] if query["split"] == split]
    if not selected:
        raise EvalContractError(f"Dataset không có query thuộc split={split}")

    dataset_hash = sha256_file(dataset_path)
    flags = feature_flags or {"clip": True, "ocr": False, "asr": False, "objects": False, "siglip": False}
    config = {
        "experiment_name": experiment_name, "pipeline_description": pipeline_description,
        "split": split, "model_name": model_name, "pretrained": pretrained,
        "device": device, "feature_flags": flags,
    }
    config_hash = sha256_bytes(json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    git_commit, git_dirty = _git_state()

    target = Path(output_dir)
    if (target / "DONE.json").exists():
        valid, errors, marker = validate_eval_run_artifact(target)
        if not valid:
            raise EvalIntegrityError(f"Artifact eval đã tồn tại nhưng không hợp lệ: {errors}")
        if marker.get("input_manifest_sha256") != dataset_hash or marker.get("config_hash") != config_hash:
            raise EvalIntegrityError("Artifact eval hoàn tất thuộc dataset/config khác")
        return marker or {}
    target.mkdir(parents=True, exist_ok=True)

    index_marker, metadata = load_validated_index_artifact(index_dir)
    index_path = Path(index_dir) / index_marker["index_file"]
    if encoder is None or searcher is None:
        encoder, searcher = _default_runtime(index_path, model_name, pretrained, device)
    assert encoder is not None and searcher is not None

    partial_path = target / "predictions.partial.jsonl"
    resume_path = target / "resume_contract.json"
    resume_contract = {
        "schema_version": 1,
        "dataset_sha256": dataset_hash,
        "config_hash": config_hash,
        "split": split,
        "index_sha256": index_marker["index_sha256"],
        "metadata_sha256": index_marker["metadata_sha256"],
    }
    if resume_path.exists():
        try:
            existing_resume = json.loads(resume_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvalIntegrityError(f"Không đọc được resume contract: {exc}") from exc
        if existing_resume != resume_contract:
            raise EvalIntegrityError("Partial eval thuộc dataset/config/index khác")
    elif partial_path.exists():
        raise EvalIntegrityError("Partial eval tồn tại nhưng thiếu resume contract")
    else:
        atomic_write_json(resume_path, resume_contract)
    prior_rows = read_valid_jsonl_prefix(partial_path)
    prior_ids = [row.get("query_id") for row in prior_rows]
    if len(prior_ids) != len(set(prior_ids)) or any(query_id is None for query_id in prior_ids):
        raise EvalIntegrityError("Partial eval chứa query_id thiếu hoặc trùng")
    selected_ids = {query["query_id"] for query in selected}
    if any(query_id not in selected_ids for query_id in prior_ids):
        raise EvalIntegrityError("Partial eval không thuộc dataset/split hiện tại")

    started_at = _utc_now()
    completed = set(prior_ids)
    for query in selected:
        if query["query_id"] in completed:
            continue
        started = time.perf_counter()
        try:
            vector = encoder(query["query_text"])
            hits = searcher(vector, 100)
            predictions = []
            for rank, (embedding_id, similarity) in enumerate(hits[:100], start=1):
                row = metadata.get(embedding_id)
                if row is None:
                    raise EvalIntegrityError(f"FAISS trả embedding_id không có trong metadata: {embedding_id}")
                predictions.append({
                    "rank": rank,
                    "embedding_id": embedding_id,
                    "video_id": row["video_id"],
                    "frame_idx": row["frame_idx"],
                    "keyframe_id": row.get("keyframe_id"),
                    "score": similarity,
                })
            score = score_query(query, predictions)
            record = {
                "query_id": query["query_id"], "query_type": query["query_type"],
                "trap_category": query["trap_category"], "split": query["split"],
                "label_status": query["label_status"], "status": "OK",
                "predictions": predictions, "score": score,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        except Exception as exc:
            record = {
                "query_id": query["query_id"], "query_type": query["query_type"],
                "trap_category": query["trap_category"], "split": query["split"],
                "label_status": query["label_status"], "status": "ERROR",
                "error_type": type(exc).__name__, "error": str(exc),
                "predictions": [], "score": None,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        append_jsonl(partial_path, record)

    rows_by_id = {row["query_id"]: row for row in read_valid_jsonl_prefix(partial_path)}
    rows = [rows_by_id[query["query_id"]] for query in selected]
    failed = sum(row["status"] == "ERROR" for row in rows)
    aggregate = aggregate_scores(rows, split=split)
    latencies = [float(row["latency_ms"]) for row in rows]
    if aggregate["scored"]:
        quality_status = "SCORED"
    elif aggregate["labeled"] == 0:
        quality_status = "BLOCKED_BY_GROUND_TRUTH"
    else:
        quality_status = "BLOCKED_BY_SCORING_CONTRACT"

    summary = {
        "schema_version": 1,
        "experiment_name": experiment_name,
        "pipeline_description": pipeline_description,
        "quality_status": quality_status,
        "dataset": {"id": dataset["dataset_id"], "version": dataset["dataset_version"],
                    "sha256": dataset_hash, "split": split},
        "pipeline": {"git_commit": git_commit, "git_dirty": git_dirty,
                     "model_name": model_name, "pretrained": pretrained,
                     "feature_flags": flags, "config_hash": config_hash},
        "index": {"artifact_version": Path(index_dir).name,
                  "index_sha256": index_marker["index_sha256"],
                  "metadata_sha256": index_marker["metadata_sha256"],
                  "source_git_commit": index_marker.get("git_commit"),
                  "source_model": index_marker.get("model"),
                  "source_model_revision": index_marker.get("model_revision")},
        "counts": aggregate,
        "latency_ms": {"p50": _percentile(latencies, 0.50),
                       "p95": _percentile(latencies, 0.95),
                       "mean": sum(latencies) / len(latencies) if latencies else None},
        "breakdown": {"query_type": _breakdown(rows, "query_type"),
                      "trap_category": _breakdown(rows, "trap_category")},
        "started_at": started_at,
        "finished_at": _utc_now(),
    }

    predictions_path = target / "predictions.jsonl"
    atomic_write_text(predictions_path, "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    ))
    summary_path = target / "summary.json"
    atomic_write_json(summary_path, summary)
    marker = {
        "schema_version": 1, "task": "clip_baseline_evaluation",
        "experiment_name": experiment_name, "started_at": started_at,
        "finished_at": summary["finished_at"], "input_manifest_sha256": dataset_hash,
        "config_hash": config_hash, "git_commit": git_commit, "git_dirty": git_dirty,
        "model": model_name, "model_revision": pretrained,
        "expected_items": len(selected), "processed_items": len(selected) - failed,
        "failed_items": failed, "output_file": predictions_path.name,
        "output_sha256": sha256_file(predictions_path), "summary_file": summary_path.name,
        "summary_sha256": sha256_file(summary_path), "index_sha256": index_marker["index_sha256"],
        "metadata_sha256": index_marker["metadata_sha256"], "quality_status": quality_status,
    }
    atomic_write_json(target / "DONE.json", marker)
    return marker
