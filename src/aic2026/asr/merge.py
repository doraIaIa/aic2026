from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aic2026.asr.manifest import AsrContractError
from aic2026.asr.whisper_runner import (
    _git_state,
    _strict_jsonl,
    _write_jsonl,
    validate_asr_shard_artifact,
    write_checksum_file,
)
from aic2026.core.atomic import atomic_write_json
from aic2026.core.hashing import sha256_file


def merge_asr_shards(shards_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(shards_dir)
    shard_dirs = sorted(path for path in source.glob("shard_*_of_*") if path.is_dir())
    if not shard_dirs:
        raise AsrContractError("Không tìm thấy ASR shard artifact để merge")
    target = Path(output_dir)
    if (target / "DONE.json").exists():
        try:
            marker = json.loads((target / "DONE.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AsrContractError(f"Merged artifact hiện có không đọc được: {exc}") from exc
        required = ["asr_segments.jsonl", "asr_videos.jsonl", "errors.jsonl", "checksum.sha256"]
        if all((target / name).is_file() for name in required):
            checks = marker.get("output_checksums", {})
            if all(sha256_file(target / name) == checks.get(name) for name in required[:3]):
                return marker
        raise AsrContractError("Merged artifact hiện có không hợp lệ; dùng output version mới")

    segments: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []
    seen_shards: set[str] = set()
    seen_videos: set[str] = set()
    for shard_dir in shard_dirs:
        valid, validation_errors, marker = validate_asr_shard_artifact(shard_dir)
        if not valid or marker is None:
            raise AsrContractError(f"Shard {shard_dir.name} không hợp lệ: {validation_errors}")
        shard_id = marker["shard_id"]
        if shard_id in seen_shards:
            raise AsrContractError(f"Trùng shard_id khi merge: {shard_id}")
        seen_shards.add(shard_id)
        shard_videos = _strict_jsonl(shard_dir / "asr_videos.jsonl")
        shard_errors = _strict_jsonl(shard_dir / "errors.jsonl")
        for row in [*shard_videos, *shard_errors]:
            video_id = row.get("video_id")
            if not isinstance(video_id, str) or video_id in seen_videos:
                raise AsrContractError(f"Video thiếu/trùng khi merge: {video_id}")
            seen_videos.add(video_id)
        videos.extend(shard_videos)
        errors.extend(shard_errors)
        segments.extend(_strict_jsonl(shard_dir / "asr_segments.jsonl"))
        markers.append(marker)

    segment_ids = [row.get("segment_id") for row in segments]
    if any(not item for item in segment_ids) or len(segment_ids) != len(set(segment_ids)):
        raise AsrContractError("Segment ID thiếu/trùng khi merge")
    config_hashes = {marker.get("config_hash") for marker in markers}
    manifest_hashes = {marker.get("input_manifest_sha256") for marker in markers}
    if len(config_hashes) != 1 or len(manifest_hashes) != 1:
        raise AsrContractError("Không được merge shard khác config hoặc source manifest")

    target.mkdir(parents=True, exist_ok=True)
    _write_jsonl(target / "asr_segments.jsonl", segments)
    _write_jsonl(target / "asr_videos.jsonl", videos)
    _write_jsonl(target / "errors.jsonl", errors)
    checksums, checksum_hash = write_checksum_file(
        target, ["asr_segments.jsonl", "asr_videos.jsonl", "errors.jsonl"]
    )
    git_commit, git_dirty = _git_state()
    marker = {
        "schema_version": 1,
        "task": "asr_whisper_merge",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "source_shards": sorted(seen_shards),
        "source_done_sha256": {
            path.name: sha256_file(path / "DONE.json") for path in shard_dirs
        },
        "input_manifest_sha256": next(iter(manifest_hashes)),
        "config_hash": next(iter(config_hashes)),
        "model": markers[0].get("model"),
        "model_revision": markers[0].get("model_revision"),
        "language": markers[0].get("language"),
        "expected_videos": sum(marker["expected_videos"] for marker in markers),
        "processed_videos": len(videos),
        "failed_videos": len(errors),
        "segment_count": len(segments),
        "output_checksums": checksums,
        "checksum_file": "checksum.sha256",
        "checksum_sha256": checksum_hash,
        "status": "completed" if not errors else "completed_with_errors",
    }
    atomic_write_json(target / "DONE.json", marker)
    return marker
