from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aic2026.core.hashing import sha256_bytes, sha256_file
from aic2026.jobs.artifact import append_jsonl, finalize_jsonl_artifact, read_valid_jsonl_prefix, rewrite_jsonl, validate_artifact
from aic2026.jobs.checkpoint import load_checkpoint, save_checkpoint
from aic2026.jobs.handlers import ItemHandler
from aic2026.jobs.manifest import read_shard


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit(repo_root: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def run_shard(
    shard_path: str | Path,
    artifact_dir: str | Path,
    handler: ItemHandler,
    *,
    checkpoint_every: int = 50,
    max_item_retries: int = 2,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if checkpoint_every <= 0:
        raise ValueError("checkpoint_every must be > 0")
    shard_path = Path(shard_path)
    shard_sha256 = sha256_file(shard_path)
    shard = read_shard(shard_path)
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # A valid DONE marker makes the run idempotent.
    valid, _, marker = validate_artifact(artifact_dir)
    if valid and marker:
        if marker.get("input_manifest_sha256") != shard["source_manifest_sha256"]:
            raise RuntimeError("Completed artifact belongs to a different source manifest")
        if marker.get("shard_id") != shard["shard_id"]:
            raise RuntimeError("Completed artifact belongs to a different shard ID")
        if marker.get("input_shard_sha256") != shard_sha256:
            raise RuntimeError("Completed artifact belongs to different shard content")
        return marker

    checkpoint_path = artifact_dir / "checkpoint.json"
    partial_path = artifact_dir / "results.partial.jsonl"
    checkpoint = load_checkpoint(checkpoint_path)

    # Reconcile checkpoint with durable partial records. Output rows are the authoritative completed set.
    partial_rows = read_valid_jsonl_prefix(partial_path)
    # Recover from a crash-truncated final line before appending new records.
    if partial_path.exists():
        rewrite_jsonl(partial_path, partial_rows)
    completed_from_output = {str(row.get("item_id")) for row in partial_rows if row.get("item_id") is not None}
    completed = set(checkpoint.get("completed_item_ids", [])) | completed_from_output
    failed: dict[str, Any] = dict(checkpoint.get("failed", {}))
    started_at = checkpoint.get("started_at") or _utc_now()

    config_payload = json.dumps(config or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    config_hash = sha256_bytes(config_payload)

    since_checkpoint = 0
    for item in shard["items"]:
        if item.item_id in completed:
            continue
        attempts = 0
        last_exc: Exception | None = None
        while attempts <= max_item_retries:
            attempts += 1
            try:
                result = handler.process(item)
                if not isinstance(result, dict):
                    raise TypeError("handler.process must return a dict")
                result = dict(result)
                result["item_id"] = item.item_id
                append_jsonl(partial_path, result)
                completed.add(item.item_id)
                failed.pop(item.item_id, None)
                last_exc = None
                break
            except Exception as exc:  # job-level policy captures item failure for later analysis
                last_exc = exc
        if last_exc is not None:
            failed[item.item_id] = {
                "error_type": type(last_exc).__name__,
                "error": str(last_exc),
                "attempts": attempts,
            }
        since_checkpoint += 1
        if since_checkpoint >= checkpoint_every:
            save_checkpoint(
                checkpoint_path,
                {
                    "schema_version": 1,
                    "task": shard["task"],
                    "shard_id": shard["shard_id"],
                    "started_at": started_at,
                    "completed_item_ids": sorted(completed),
                    "failed": failed,
                },
            )
            since_checkpoint = 0

    save_checkpoint(
        checkpoint_path,
        {
            "schema_version": 1,
            "task": shard["task"],
            "shard_id": shard["shard_id"],
            "started_at": started_at,
            "completed_item_ids": sorted(completed),
            "failed": failed,
        },
    )

    expected_ids = {item.item_id for item in shard["items"]}
    completed_ids = set(completed)
    failed_ids = set(failed)
    if completed_ids | failed_ids != expected_ids:
        missing = sorted(expected_ids - completed_ids - failed_ids)
        raise RuntimeError(f"Shard did not reach a terminal state for item(s): {missing[:10]}")
    if completed_ids & failed_ids:
        raise RuntimeError("An item cannot be both completed and failed")

    return finalize_jsonl_artifact(
        artifact_dir,
        task=shard["task"],
        shard_id=shard["shard_id"],
        input_manifest_sha256=shard["source_manifest_sha256"],
        input_shard_sha256=shard_sha256,
        expected_items=len(shard["items"]),
        failed_items=len(failed),
        handler=handler.name,
        config_hash=config_hash,
        git_commit=_git_commit(Path.cwd()),
        started_at=started_at,
    )
