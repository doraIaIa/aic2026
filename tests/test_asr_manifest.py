from __future__ import annotations

import csv
import json
from pathlib import Path

from aic2026.asr.manifest import build_asr_pilot_manifest, load_asr_manifest
from aic2026.asr.shard import load_asr_shard, split_asr_shards
from aic2026.core.hashing import sha256_file


def _write_review(root: Path) -> Path:
    root.mkdir()
    candidate = root / "candidate_review.csv"
    columns = ["query_id", "video_id", "rank"]
    with candidate.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows([
            {"query_id": "q1", "video_id": "V1", "rank": 1},
            {"query_id": "q2", "video_id": "V2", "rank": 1},
            {"query_id": "q1", "video_id": "V3", "rank": 2},
        ])
    failure = root / "failure_sheet.csv"
    failure.write_text("query_id,status\n", encoding="utf-8-sig")
    marker = {
        "schema_version": 1,
        "task": "eval_candidate_review",
        "candidate_file": candidate.name,
        "candidate_sha256": sha256_file(candidate),
        "candidate_count": 3,
        "failure_file": failure.name,
        "failure_sha256": sha256_file(failure),
        "failure_count": 0,
    }
    (root / "DONE.json").write_text(json.dumps(marker), encoding="utf-8")
    return candidate


def test_build_pilot_manifest_expands_rank_and_uses_inventory_paths(tmp_path: Path) -> None:
    candidate = _write_review(tmp_path / "review")
    inventory = tmp_path / "videos.jsonl"
    inventory.write_text("".join(
        json.dumps({
            "video_id": f"V{index}",
            "relative_path": f"data_extracted/video/V{index}.mp4",
            "logical_size": index * 100,
        }) + "\n"
        for index in range(1, 4)
    ), encoding="utf-8")
    output = tmp_path / "pilot.jsonl"

    summary = build_asr_pilot_manifest(
        candidate, inventory, output,
        min_videos=3, max_videos=4, primary_rank=1, expanded_rank=2,
    )
    rows = load_asr_manifest(output)

    assert summary["primary_unique_videos"] == 2
    assert summary["selection_rank_limit"] == 2
    assert summary["video_count"] == 3
    assert [row["video_id"] for row in rows] == ["V1", "V2", "V3"]
    assert rows[0]["video_path"] == "data_extracted/video/V1.mp4"
    assert rows[0]["source_candidate_ranks"] == {"q1": [1]}
    assert Path(rows[0]["video_path"]).is_absolute() is False
    assert build_asr_pilot_manifest(
        candidate, inventory, output,
        min_videos=3, max_videos=4, primary_rank=1, expanded_rank=2,
    ) == summary


def test_split_asr_shards_is_balanced_and_idempotent(tmp_path: Path) -> None:
    manifest = tmp_path / "pilot.jsonl"
    manifest.write_text("".join(
        json.dumps({
            "schema_version": 1,
            "video_id": f"V{index}",
            "video_path": f"video/V{index}.mp4",
            "source_query_ids": ["q1"],
            "source_candidate_ranks": {"q1": [index]},
        }) + "\n"
        for index in range(1, 6)
    ), encoding="utf-8")

    outputs = split_asr_shards(manifest, tmp_path / "shards", num_shards=2)
    assert [load_asr_shard(path)["item_count"] for path in outputs] == [3, 2]
    assert split_asr_shards(manifest, tmp_path / "shards", num_shards=2) == outputs
