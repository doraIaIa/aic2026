from pathlib import Path

from aic2026.jobs.artifact import validate_artifact
from aic2026.jobs.handlers import EchoHandler
from aic2026.jobs.manifest import build_shards, write_jsonl_manifest
from aic2026.jobs.models import ManifestItem
from aic2026.jobs.runner import run_shard


def test_checksum_detects_corruption(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    write_jsonl_manifest(manifest, [ManifestItem("id-0", "x/0")])
    shard = build_shards(manifest, tmp_path / "shards", task="demo", shard_size=1)[0]
    artifact = tmp_path / "artifact"
    run_shard(shard, artifact, EchoHandler(), checkpoint_every=1)

    with (artifact / "results.jsonl").open("a", encoding="utf-8") as f:
        f.write("corruption\n")

    valid, errors, _ = validate_artifact(artifact)
    assert not valid
    assert any("SHA-256" in error for error in errors)
