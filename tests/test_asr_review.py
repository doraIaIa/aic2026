from __future__ import annotations

import csv
import json
from pathlib import Path

from aic2026.asr.fts import build_asr_fts
from aic2026.asr.review import export_asr_candidate_review


def test_export_asr_review_with_optional_nearest_keyframe(tmp_path: Path) -> None:
    segments = tmp_path / "segments.jsonl"
    segments.write_text(json.dumps({
        "segment_id": "V1:000000", "video_id": "V1", "start_sec": 10.0, "end_sec": 14.0,
        "text": "thành phố Hồ Chí Minh", "source_video_path": "video/V1.mp4",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    fts = tmp_path / "fts"
    build_asr_fts(segments, fts)
    dataset = tmp_path / "eval.json"
    dataset.write_text(json.dumps({
        "schema_version": 1,
        "dataset_id": "group-a",
        "dataset_version": "v1",
        "queries": [{
            "query_id": "q1", "query_type": "KIS", "query_text": "Hồ Chí Minh",
            "question_text": None, "trap_category": "asr_only", "split": "dev",
            "label_status": "unlabeled_reference", "gt_video_id": None,
            "gt_frame_ranges": [], "gt_answer": None, "label_provenance": None,
        }],
    }, ensure_ascii=False), encoding="utf-8")
    metadata = tmp_path / "metadata.jsonl"
    metadata.write_text(json.dumps({
        "video_id": "V1", "pts_time": 11.5, "frame_idx": 345,
        "keyframe_id": "V1:012", "embedding_id": 1,
    }) + "\n", encoding="utf-8")

    marker = export_asr_candidate_review(
        dataset, fts, tmp_path / "review", top_k=5, metadata_path=metadata,
    )
    with (tmp_path / "review" / "asr_candidate_review.csv").open(
        encoding="utf-8-sig", newline="",
    ) as stream:
        rows = list(csv.DictReader(stream))

    assert marker["query_count"] == 1
    assert marker["candidate_count"] == 1
    assert rows[0]["nearest_keyframe_id"] == "V1:012"
    assert rows[0]["nearest_frame_idx"] == "345"
    assert float(rows[0]["delta_sec"]) == -0.5
    assert rows[0]["timestamp_display"] == "00:00:10.000–00:00:14.000"
