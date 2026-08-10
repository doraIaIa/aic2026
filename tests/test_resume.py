import json
from pathlib import Path

from aic2026.jobs.artifact import append_jsonl, validate_artifact
from aic2026.jobs.checkpoint import save_checkpoint
from aic2026.jobs.handlers import EchoHandler
from aic2026.jobs.manifest import build_shards, write_jsonl_manifest
from aic2026.jobs.models import ManifestItem
from aic2026.jobs.runner import run_shard


def test_resume_from_partial_output(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    write_jsonl_manifest(
        manifest,
        [ManifestItem(f"id-{i}", f"x/{i}.jpg", {"i": i}) for i in range(4)],
    )
    shard = build_shards(manifest, tmp_path / "shards", task="demo", shard_size=10)[0]
    shard_payload = json.loads(shard.read_text(encoding="utf-8"))
    artifact = tmp_path / "artifact"
    artifact.mkdir()

    append_jsonl(artifact / "results.partial.jsonl", {"item_id": "id-0", "preexisting": True})
    save_checkpoint(
        artifact / "checkpoint.json",
        {
            "schema_version": 1,
            "task": "demo",
            "shard_id": shard_payload["shard_id"],
            "completed_item_ids": ["id-0"],
            "failed": {},
        },
    )

    marker = run_shard(shard, artifact, EchoHandler(), checkpoint_every=1)
    assert marker["processed_items"] == 4
    valid, errors, _ = validate_artifact(artifact)
    assert valid, errors

    # Idempotent second run: valid completed artifact is reused.
    marker2 = run_shard(shard, artifact, EchoHandler(), checkpoint_every=1)
    assert marker2["output_sha256"] == marker["output_sha256"]


def test_truncated_partial_line_is_recovered(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    write_jsonl_manifest(manifest, [ManifestItem("id-0", "x/0"), ManifestItem("id-1", "x/1")])
    shard = build_shards(manifest, tmp_path / "shards", task="demo", shard_size=10)[0]
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "results.partial.jsonl").write_text('{"item_id":"id-0"}\n{"item_id":', encoding="utf-8")

    marker = run_shard(shard, artifact, EchoHandler(), checkpoint_every=1)
    assert marker["processed_items"] == 2
    valid, errors, _ = validate_artifact(artifact)
    assert valid, errors
