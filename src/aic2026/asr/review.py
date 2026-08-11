from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from aic2026.asr.fts import _resolve_valid_index, search_asr
from aic2026.asr.manifest import AsrContractError
from aic2026.asr.whisper_runner import _git_state, write_checksum_file
from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.core.hashing import sha256_bytes, sha256_file
from aic2026.evaluation.contract import load_eval_dataset


REVIEW_COLUMNS = (
    "query_id", "task_type", "query_text", "rank", "video_id",
    "segment_start_sec", "segment_end_sec", "timestamp_display",
    "transcript_text", "bm25_score", "nearest_keyframe_id",
    "nearest_frame_idx", "delta_sec",
)


def _timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _load_keyframes(path: str | Path | None) -> dict[str, list[dict[str, Any]]]:
    by_video: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if path is None:
        return by_video
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                video_id = row["video_id"]
                pts_time = float(row["pts_time"])
                frame_idx = row["frame_idx"]
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise AsrContractError(f"Keyframe metadata malformed tại dòng {line_number}") from exc
            if not isinstance(video_id, str) or type(frame_idx) is not int or pts_time < 0:
                raise AsrContractError(f"Keyframe metadata malformed tại dòng {line_number}")
            by_video[video_id].append(row)
    for rows in by_video.values():
        rows.sort(key=lambda row: (float(row["pts_time"]), str(row.get("keyframe_id", ""))))
    return by_video


def _existing_marker(
    target: Path,
    *,
    dataset_hash: str,
    index_hash: str,
    metadata_hash: str | None,
    config_hash: str,
) -> dict[str, Any] | None:
    marker_path = target / "DONE.json"
    if not marker_path.exists():
        if target.exists() and any(target.iterdir()):
            raise AsrContractError("ASR review output tồn tại không hoàn chỉnh; dùng version mới")
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AsrContractError(f"ASR review DONE.json không đọc được: {exc}") from exc
    candidate = target / str(marker.get("candidate_file", ""))
    if (
        marker.get("task") != "asr_candidate_review"
        or marker.get("dataset_sha256") != dataset_hash
        or marker.get("index_sha256") != index_hash
        or marker.get("metadata_sha256") != metadata_hash
        or marker.get("config_hash") != config_hash
        or not candidate.is_file()
        or sha256_file(candidate) != marker.get("candidate_sha256")
    ):
        raise AsrContractError("ASR review artifact hiện có sai input/config/checksum")
    return marker


def export_asr_candidate_review(
    dataset_path: str | Path,
    index_path: str | Path,
    output_dir: str | Path,
    *,
    top_k: int = 20,
    metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    if top_k <= 0 or top_k > 100:
        raise AsrContractError("top_k phải nằm trong 1..100")
    dataset, _ = load_eval_dataset(dataset_path)
    resolved_index = _resolve_valid_index(index_path)
    dataset_hash = sha256_file(dataset_path)
    index_hash = sha256_file(resolved_index)
    metadata_hash = sha256_file(metadata_path) if metadata_path is not None else None
    config_hash = sha256_bytes(json.dumps({"top_k": top_k}, sort_keys=True).encode("utf-8"))
    target = Path(output_dir)
    existing = _existing_marker(
        target,
        dataset_hash=dataset_hash,
        index_hash=index_hash,
        metadata_hash=metadata_hash,
        config_hash=config_hash,
    )
    if existing is not None:
        return existing

    keyframes = _load_keyframes(metadata_path)
    rows: list[dict[str, Any]] = []
    for query in dataset["queries"]:
        for hit in search_asr(resolved_index, query["query_text"], top_k=top_k):
            start = float(hit["start_sec"])
            end = float(hit["end_sec"])
            midpoint = (start + end) / 2
            nearest = None
            if keyframes.get(hit["video_id"]):
                nearest = min(
                    keyframes[hit["video_id"]],
                    key=lambda row: (abs(float(row["pts_time"]) - midpoint), float(row["pts_time"])),
                )
            rows.append({
                "query_id": query["query_id"],
                "task_type": query["query_type"],
                "query_text": query["query_text"],
                "rank": hit["rank"],
                "video_id": hit["video_id"],
                "segment_start_sec": start,
                "segment_end_sec": end,
                "timestamp_display": f"{_timestamp(start)}–{_timestamp(end)}",
                "transcript_text": hit["text"],
                "bm25_score": hit["bm25"],
                "nearest_keyframe_id": nearest.get("keyframe_id") if nearest else None,
                "nearest_frame_idx": nearest.get("frame_idx") if nearest else None,
                "delta_sec": float(nearest["pts_time"]) - midpoint if nearest else None,
            })

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    target.mkdir(parents=True, exist_ok=True)
    candidate = target / "asr_candidate_review.csv"
    atomic_write_text(candidate, stream.getvalue(), encoding="utf-8-sig")
    checksums, checksum_hash = write_checksum_file(target, [candidate.name])
    git_commit, git_dirty = _git_state()
    marker = {
        "schema_version": 1,
        "task": "asr_candidate_review",
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "dataset_sha256": dataset_hash,
        "index_sha256": index_hash,
        "metadata_sha256": metadata_hash,
        "config_hash": config_hash,
        "query_count": len(dataset["queries"]),
        "candidate_count": len(rows),
        "candidate_file": candidate.name,
        "candidate_sha256": checksums[candidate.name],
        "checksum_file": "checksum.sha256",
        "checksum_sha256": checksum_hash,
    }
    atomic_write_json(target / "DONE.json", marker)
    return marker
