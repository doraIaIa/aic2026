from __future__ import annotations

import csv
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.core.hashing import sha256_bytes, sha256_file
from aic2026.core.paths import PathContractError, normalize_relpath
from aic2026.evaluation.review import validate_candidate_review_artifact


ASR_PILOT_MANIFEST_SCHEMA_VERSION = 1


class AsrContractError(ValueError):
    """ASR manifest, shard, or artifact violates its locked contract."""


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


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AsrContractError(f"JSONL lỗi tại {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise AsrContractError(f"JSONL row tại {path}:{line_number} phải là object")
            rows.append(row)
    return rows


def load_asr_manifest(path: str | Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(path)
    if not rows:
        raise AsrContractError("ASR manifest không được rỗng")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        video_id = row.get("video_id")
        if not isinstance(video_id, str) or not video_id.strip():
            raise AsrContractError(f"Manifest row {index}: video_id không hợp lệ")
        video_id = video_id.strip()
        if video_id in seen:
            raise AsrContractError(f"Manifest trùng video_id: {video_id}")
        seen.add(video_id)
        try:
            video_path = normalize_relpath(str(row.get("video_path", "")))
        except PathContractError as exc:
            raise AsrContractError(f"Manifest row {index}: video_path không hợp lệ: {exc}") from exc
        query_ids = row.get("source_query_ids")
        ranks = row.get("source_candidate_ranks")
        if not isinstance(query_ids, list) or not all(isinstance(item, str) and item for item in query_ids):
            raise AsrContractError(f"Manifest row {index}: source_query_ids không hợp lệ")
        if not isinstance(ranks, dict):
            raise AsrContractError(f"Manifest row {index}: source_candidate_ranks không hợp lệ")
        normalized_row = dict(row)
        normalized_row.update({"video_id": video_id, "video_path": video_path})
        normalized.append(normalized_row)
    return normalized


def _existing_manifest_summary(output: Path, summary_path: Path) -> dict[str, Any] | None:
    if not output.exists() and not summary_path.exists():
        return None
    if not output.is_file() or not summary_path.is_file():
        raise AsrContractError("Pilot manifest tồn tại không đầy đủ; dùng output version mới")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AsrContractError(f"Không đọc được manifest summary hiện có: {exc}") from exc
    if summary.get("manifest_sha256") != sha256_file(output):
        raise AsrContractError("Pilot manifest hiện có không khớp checksum; không overwrite")
    load_asr_manifest(output)
    return summary


def build_asr_pilot_manifest(
    candidate_review: str | Path,
    video_inventory: str | Path,
    output_path: str | Path,
    *,
    data_root: str | Path | None = None,
    min_videos: int = 100,
    max_videos: int = 250,
    primary_rank: int = 10,
    expanded_rank: int = 20,
) -> dict[str, Any]:
    if min_videos <= 0 or max_videos < min_videos:
        raise AsrContractError("Cần 0 < min_videos <= max_videos")
    if primary_rank <= 0 or expanded_rank < primary_rank:
        raise AsrContractError("Rank selection không hợp lệ")

    candidate_path = Path(candidate_review)
    inventory_path = Path(video_inventory)
    output = Path(output_path)
    summary_path = output.with_suffix(".summary.json")
    existing = _existing_manifest_summary(output, summary_path)
    candidate_hash = sha256_file(candidate_path)
    inventory_hash = sha256_file(inventory_path)
    selection_config = {
        "min_videos": min_videos,
        "max_videos": max_videos,
        "primary_rank": primary_rank,
        "expanded_rank": expanded_rank,
    }
    config_hash = sha256_bytes(json.dumps(selection_config, sort_keys=True).encode("utf-8"))
    if existing is not None:
        expected = {
            "candidate_review_sha256": candidate_hash,
            "video_inventory_sha256": inventory_hash,
            "min_videos": min_videos,
            "max_videos": max_videos,
            "primary_rank": primary_rank,
            "expanded_rank": expanded_rank,
            "config_hash": config_hash,
        }
        if any(existing.get(key) != value for key, value in expected.items()):
            raise AsrContractError("Pilot manifest hoàn tất thuộc input/config khác; dùng version mới")
        return existing

    review_valid, review_errors, _ = validate_candidate_review_artifact(candidate_path.parent)
    if not review_valid:
        raise AsrContractError(f"Candidate review artifact không hợp lệ: {review_errors}")

    candidates: list[dict[str, Any]] = []
    try:
        with candidate_path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row_number, row in enumerate(csv.DictReader(stream), start=2):
                try:
                    rank = int(row.get("rank", ""))
                except ValueError as exc:
                    raise AsrContractError(f"Candidate row {row_number}: rank không hợp lệ") from exc
                query_id = (row.get("query_id") or "").strip()
                video_id = (row.get("video_id") or "").strip()
                if not query_id or not video_id or rank <= 0:
                    raise AsrContractError(f"Candidate row {row_number}: thiếu query_id/video_id/rank")
                candidates.append({"query_id": query_id, "video_id": video_id, "rank": rank})
    except (OSError, csv.Error) as exc:
        raise AsrContractError(f"Không đọc được candidate review CSV: {exc}") from exc
    if not candidates:
        raise AsrContractError("Candidate review CSV không có row")

    primary_ids = {row["video_id"] for row in candidates if row["rank"] <= primary_rank}
    rank_limit = primary_rank if len(primary_ids) >= min_videos else expanded_rank
    selected_rows = [row for row in candidates if row["rank"] <= rank_limit]
    evidence: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for row in selected_rows:
        ranks = evidence[row["video_id"]][row["query_id"]]
        if row["rank"] not in ranks:
            ranks.append(row["rank"])

    ordered_ids = sorted(
        evidence,
        key=lambda video_id: (
            min(rank for ranks in evidence[video_id].values() for rank in ranks),
            video_id,
        ),
    )[:max_videos]

    inventory: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(inventory_path):
        video_id = row.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            raise AsrContractError("Video inventory chứa video_id không hợp lệ")
        if video_id in inventory:
            raise AsrContractError(f"Video inventory trùng video_id: {video_id}")
        inventory[video_id] = row
    missing = [video_id for video_id in ordered_ids if video_id not in inventory]
    if missing:
        raise AsrContractError(f"Candidate video thiếu trong inventory: {missing[:10]}")

    root = Path(data_root) if data_root is not None else None
    manifest_rows: list[dict[str, Any]] = []
    for video_id in ordered_ids:
        source = inventory[video_id]
        try:
            relpath = normalize_relpath(str(source.get("relative_path", "")))
        except PathContractError as exc:
            raise AsrContractError(f"Inventory path của {video_id} không hợp lệ: {exc}") from exc
        full_path = root / Path(relpath) if root is not None else None
        stat = None
        if full_path is not None:
            try:
                stat = full_path.stat()
            except OSError:
                stat = None
        rank_map = {
            query_id: sorted(ranks)
            for query_id, ranks in sorted(evidence[video_id].items())
        }
        manifest_rows.append({
            "schema_version": ASR_PILOT_MANIFEST_SCHEMA_VERSION,
            "video_id": video_id,
            "video_path": relpath,
            "source_query_ids": list(rank_map),
            "source_candidate_ranks": rank_map,
            "duration_sec": source.get("duration_sec"),
            "source_size_bytes": stat.st_size if stat is not None else source.get("logical_size"),
            "source_mtime_ns": stat.st_mtime_ns if stat is not None else None,
        })

    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in manifest_rows)
    atomic_write_text(output, payload)
    git_commit, git_dirty = _git_state()
    summary = {
        "schema_version": ASR_PILOT_MANIFEST_SCHEMA_VERSION,
        "task": "asr_pilot_manifest",
        "created_at": _utc_now(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "config_hash": config_hash,
        "candidate_review_file": candidate_path.name,
        "candidate_review_sha256": candidate_hash,
        "video_inventory_file": inventory_path.name,
        "video_inventory_sha256": inventory_hash,
        "manifest_file": output.name,
        "manifest_sha256": sha256_file(output),
        "video_count": len(manifest_rows),
        "primary_unique_videos": len(primary_ids),
        "selection_rank_limit": rank_limit,
        "min_videos": min_videos,
        "max_videos": max_videos,
        "primary_rank": primary_rank,
        "expanded_rank": expanded_rank,
    }
    atomic_write_json(summary_path, summary)
    return summary
