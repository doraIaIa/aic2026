import json
from pathlib import Path

import pytest

from aic2026.jobs.manifest import build_shards, read_jsonl_manifest, write_jsonl_manifest
from aic2026.jobs.models import ManifestItem


def test_manifest_round_trip_and_shard(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    items = [ManifestItem(f"id-{i}", f"x/{i}.jpg", {"i": i}) for i in range(5)]
    write_jsonl_manifest(manifest, items)
    loaded = read_jsonl_manifest(manifest)
    assert [x.item_id for x in loaded] == [x.item_id for x in items]

    shards = build_shards(manifest, tmp_path / "shards", task="ocr", shard_size=2)
    assert len(shards) == 3
    payload = json.loads(shards[0].read_text(encoding="utf-8"))
    assert payload["task"] == "ocr"
    assert payload["item_count"] == 2


def test_duplicate_ids_rejected(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        '{"item_id":"x","source_relpath":"a"}\n{"item_id":"x","source_relpath":"b"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        read_jsonl_manifest(manifest)
