from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aic2026.asr.manifest import AsrContractError, _git_state, load_asr_manifest
from aic2026.core.atomic import atomic_write_json
from aic2026.core.hashing import sha256_bytes, sha256_file
from aic2026.core.paths import PathContractError, normalize_relpath


def load_asr_shard(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AsrContractError(f"Không đọc được ASR shard: {exc}") from exc
    if raw.get("schema_version") != 1 or raw.get("task") != "asr_whisper":
        raise AsrContractError("ASR shard sai schema/task")
    items = raw.get("items")
    if not isinstance(items, list) or raw.get("item_count") != len(items):
        raise AsrContractError("ASR shard item_count/items không hợp lệ")
    ids = [item.get("video_id") for item in items if isinstance(item, dict)]
    if len(ids) != len(items) or len(ids) != len(set(ids)) or any(not item for item in ids):
        raise AsrContractError("ASR shard chứa item malformed hoặc video_id trùng")
    for item in items:
        if item.get("schema_version") != 1:
            raise AsrContractError("ASR shard item sai schema_version")
        try:
            normalize_relpath(str(item.get("video_path", "")))
        except PathContractError as exc:
            raise AsrContractError(f"ASR shard video_path không hợp lệ: {exc}") from exc
    return raw


def split_asr_shards(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    num_shards: int,
) -> list[Path]:
    manifest = Path(manifest_path)
    items = load_asr_manifest(manifest)
    if num_shards <= 0 or num_shards > len(items):
        raise AsrContractError("num_shards phải nằm trong 1..số video")
    source_hash = sha256_file(manifest)
    config_hash = sha256_bytes(json.dumps({"num_shards": num_shards}, sort_keys=True).encode("utf-8"))
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    expected_names = [f"shard_{index:03d}_of_{num_shards:03d}.json" for index in range(num_shards)]
    existing = sorted(target.glob("shard_*_of_*.json"))
    if existing:
        if [path.name for path in existing] != expected_names:
            raise AsrContractError("Shard directory đã chứa layout khác; dùng output version mới")
        for path in existing:
            shard = load_asr_shard(path)
            if (
                shard.get("source_manifest_sha256") != source_hash
                or shard.get("shard_count") != num_shards
                or shard.get("config_hash") != config_hash
            ):
                raise AsrContractError("Shard hiện có thuộc manifest/config khác")
        return existing

    base, remainder = divmod(len(items), num_shards)
    git_commit, git_dirty = _git_state()
    outputs: list[Path] = []
    start = 0
    for index in range(num_shards):
        count = base + (1 if index < remainder else 0)
        shard_items = items[start:start + count]
        start += count
        shard_id = f"shard_{index:03d}_of_{num_shards:03d}"
        payload = {
            "schema_version": 1,
            "task": "asr_whisper",
            "shard_id": shard_id,
            "shard_index": index,
            "shard_count": num_shards,
            "source_manifest": manifest.name,
            "source_manifest_sha256": source_hash,
            "config_hash": config_hash,
            "git_commit": git_commit,
            "git_dirty": git_dirty,
            "item_count": len(shard_items),
            "items": shard_items,
        }
        output = target / f"{shard_id}.json"
        atomic_write_json(output, payload)
        outputs.append(output)
    return outputs
