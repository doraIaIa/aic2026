from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aic2026.core.atomic import atomic_write_json
from aic2026.core.hashing import sha256_file


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_valid_jsonl_prefix(path: str | Path) -> list[dict[str, Any]]:
    """Return all complete valid JSONL rows; tolerate one truncated final line."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # A crash may truncate the last append. Anything after a malformed line is unsafe.
                break
    return rows


def rewrite_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".recover.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def finalize_jsonl_artifact(
    artifact_dir: str | Path,
    *,
    task: str,
    shard_id: str,
    input_manifest_sha256: str,
    input_shard_sha256: str,
    expected_items: int,
    failed_items: int,
    handler: str,
    config_hash: str = "",
    git_commit: str = "",
    started_at: str = "",
) -> dict[str, Any]:
    root = Path(artifact_dir)
    root.mkdir(parents=True, exist_ok=True)
    partial = root / "results.partial.jsonl"
    rows = read_valid_jsonl_prefix(partial)
    final_tmp = root / "results.jsonl.tmp"
    final = root / "results.jsonl"
    with final_tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(final_tmp, final)
    output_hash = sha256_file(final)
    marker = {
        "schema_version": 1,
        "task": task,
        "shard_id": shard_id,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "input_manifest_sha256": input_manifest_sha256,
        "input_shard_sha256": input_shard_sha256,
        "output_file": final.name,
        "output_sha256": output_hash,
        "expected_items": expected_items,
        "processed_items": len(rows),
        "failed_items": failed_items,
        "handler": handler,
        "config_hash": config_hash,
        "git_commit": git_commit,
        "status": "completed" if failed_items == 0 else "completed_with_errors",
    }
    atomic_write_json(root / "DONE.json", marker)
    return marker


def validate_artifact(artifact_dir: str | Path) -> tuple[bool, list[str], dict[str, Any] | None]:
    root = Path(artifact_dir)
    errors: list[str] = []
    marker_path = root / "DONE.json"
    if not marker_path.exists():
        return False, ["DONE.json missing"], None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"DONE.json unreadable: {exc}"], None
    if marker.get("schema_version") != 1:
        errors.append("unsupported DONE schema_version")
    output_file = marker.get("output_file")
    if not output_file:
        errors.append("output_file missing in DONE")
        return False, errors, marker
    output = root / output_file
    if not output.exists():
        errors.append(f"output file missing: {output_file}")
    else:
        actual_hash = sha256_file(output)
        if actual_hash != marker.get("output_sha256"):
            errors.append("output SHA-256 mismatch")
        rows = read_valid_jsonl_prefix(output)
        if len(rows) != marker.get("processed_items"):
            errors.append("processed_items does not match output row count")
    expected = marker.get("expected_items")
    processed = marker.get("processed_items")
    failed = marker.get("failed_items")
    if all(isinstance(x, int) for x in (expected, processed, failed)):
        if processed + failed != expected:
            errors.append("processed_items + failed_items != expected_items")
    else:
        errors.append("invalid expected/processed/failed counts")
    return not errors, errors, marker
