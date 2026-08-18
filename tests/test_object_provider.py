from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from aic2026.retrieval.providers import ObjectProvider, ProviderQuery
from aic2026.search.build_object_index import build_object_index


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    (data_root / "data_extracted" / "objects" / "V1").mkdir(parents=True)
    (data_root / "data_extracted" / "keyframes" / "V1").mkdir(parents=True)
    (data_root / "data_extracted" / "map-keyframes").mkdir(parents=True)
    (data_root / "data_extracted" / "keyframes" / "V1" / "001.jpg").write_bytes(b"image")
    with (data_root / "data_extracted" / "map-keyframes" / "V1.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["n", "pts_time", "fps", "frame_idx"])
        writer.writeheader(); writer.writerow({"n": 1, "pts_time": 0.0, "fps": 25.0, "frame_idx": 0})
    (data_root / "data_extracted" / "objects" / "V1" / "001.json").write_text(json.dumps({
        "detection_class_entities": ["Car", "Person"], "detection_scores": ["0.9", "0.8"],
        "detection_boxes": [["0", "0", "1", "1"], ["0", "0", "1", "1"]],
    }), encoding="utf-8")
    database = tmp_path / "aic.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE videos(video_id TEXT PRIMARY KEY)")
        connection.executemany("INSERT INTO videos VALUES(?)", [("V1",), ("V2",)])
    return database, data_root


def test_object_index_and_provider_are_soft_partial_evidence(tmp_path: Path):
    database, data_root = _fixture(tmp_path)
    report = build_object_index(database, data_root)
    assert report["videos_with_artifacts"] == 1
    assert report["videos_missing"] == 1
    assert report["indexed_observations"] == report["fts_rows"] == 2
    provider = ObjectProvider(database)
    assert provider.capabilities().status == "OK"
    assert provider.capabilities().counts["coverage_videos"] == 1
    hits = provider.search(ProviderQuery("ô tô", top_k=10))
    assert hits[0].payload["label"] == "Car"
    assert hits[0].payload["csv_n"] == 1
    assert hits[0].payload["frame_idx"] == 0
    assert hits[0].payload["object_match"] == "soft"
