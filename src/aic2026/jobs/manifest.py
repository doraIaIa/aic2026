from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from aic2026.core.atomic import atomic_write_json
from aic2026.core.hashing import sha256_file
from aic2026.core.paths import normalize_relpath
from aic2026.jobs.models import ManifestItem


def read_jsonl_manifest(path: str | Path) -> list[ManifestItem]:
    items: list[ManifestItem] = []
    seen: set[str] = set()
    with Path(path).open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{lineno}: {exc}") from exc
            item = ManifestItem.from_dict(raw)
            item = ManifestItem(item.item_id, normalize_relpath(item.source_relpath), item.metadata)
            if item.item_id in seen:
                raise ValueError(f"Duplicate item_id {item.item_id!r} in {path}")
            seen.add(item.item_id)
            items.append(item)
    return items


def write_jsonl_manifest(path: str | Path, items: Iterable[ManifestItem]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    seen: set[str] = set()
    for item in items:
        if item.item_id in seen:
            raise ValueError(f"Duplicate item_id {item.item_id!r}")
        seen.add(item.item_id)
        normalized = ManifestItem(item.item_id, normalize_relpath(item.source_relpath), item.metadata)
        rows.append(json.dumps(normalized.to_dict(), ensure_ascii=False, sort_keys=True))
    target.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def build_shards(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    task: str,
    shard_size: int,
) -> list[Path]:
    if shard_size <= 0:
        raise ValueError("shard_size must be > 0")
    manifest_path = Path(manifest_path)
    items = read_jsonl_manifest(manifest_path)
    source_hash = sha256_file(manifest_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    width = max(3, len(str(max(0, (len(items) - 1) // shard_size))))
    for index, start in enumerate(range(0, len(items), shard_size)):
        shard_items = items[start : start + shard_size]
        shard_id = f"{task}-{index:0{width}d}"
        payload = {
            "schema_version": 1,
            "task": task,
            "shard_id": shard_id,
            "source_manifest": manifest_path.as_posix(),
            "source_manifest_sha256": source_hash,
            "item_count": len(shard_items),
            "items": [x.to_dict() for x in shard_items],
        }
        output = out_dir / f"shard-{index:0{width}d}.json"
        atomic_write_json(output, payload)
        outputs.append(output)
    return outputs


def read_shard(path: str | Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"schema_version", "task", "shard_id", "source_manifest_sha256", "items"}
    missing = required.difference(raw)
    if missing:
        raise ValueError(f"Shard manifest missing keys: {sorted(missing)}")
    if raw["schema_version"] != 1:
        raise ValueError(f"Unsupported shard schema_version: {raw['schema_version']}")
    items = [ManifestItem.from_dict(x) for x in raw["items"]]
    ids = [x.item_id for x in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Shard contains duplicate item IDs")
    if raw.get("item_count") is not None and raw["item_count"] != len(items):
        raise ValueError("Shard item_count does not match items length")
    raw["items"] = items
    return raw
