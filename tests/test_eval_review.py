import csv
import json
from pathlib import Path

from aic2026.core.hashing import sha256_file
from aic2026.evaluation.review import export_candidate_review, validate_candidate_review_artifact


def _write_dataset(root: Path) -> Path:
    path = root / "eval.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "dataset_id": "review-test",
        "dataset_version": "v1",
        "queries": [
            {
                "query_id": query_id,
                "query_type": "KIS",
                "query_text": text,
                "question_text": None,
                "trap_category": "unclassified",
                "split": "dev",
                "label_status": "unlabeled_reference",
                "gt_video_id": None,
                "gt_frame_ranges": [],
                "gt_answer": None,
                "label_provenance": None,
            }
            for query_id, text in (("q1", "người đi xe đạp"), ("q2", "query lỗi"))
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def _write_run(root: Path, dataset: Path) -> Path:
    run = root / "run"
    run.mkdir()
    records = [
        {
            "query_id": "q1", "status": "OK", "latency_ms": 5.0,
            "predictions": [{
                "rank": 1, "embedding_id": 123, "stable_id": 123,
                "video_id": "V1", "frame_idx": 75, "keyframe_id": "V1:2",
                "pts_time": 3.0, "score": 0.8, "csv_n": 2, "clip_row": 1,
                "keyframe_relpath": "data_extracted/keyframes/V1/002.jpg",
            }],
        },
        {
            "query_id": "q2", "status": "ERROR", "error_type": "RuntimeError",
            "error": "synthetic failure", "latency_ms": 2.0, "predictions": [],
        },
    ]
    prediction_path = run / "predictions.jsonl"
    prediction_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8"
    )
    summary_path = run / "summary.json"
    summary_path.write_text("{}\n", encoding="utf-8")
    marker = {
        "schema_version": 1, "task": "clip_baseline_evaluation",
        "input_manifest_sha256": sha256_file(dataset),
        "expected_items": 2, "processed_items": 1, "failed_items": 1,
        "output_file": prediction_path.name, "output_sha256": sha256_file(prediction_path),
        "summary_file": summary_path.name, "summary_sha256": sha256_file(summary_path),
        "quality_status": "BLOCKED_BY_GROUND_TRUTH", "git_commit": "test", "git_dirty": True,
    }
    (run / "DONE.json").write_text(json.dumps(marker), encoding="utf-8")
    return run


def test_export_candidate_review_writes_candidates_failures_and_provenance(tmp_path):
    dataset = _write_dataset(tmp_path)
    run = _write_run(tmp_path, dataset)
    output = tmp_path / "review"
    marker = export_candidate_review(dataset, run, output)
    assert marker["candidate_count"] == 1
    assert marker["failure_count"] == 1
    valid, errors, _ = validate_candidate_review_artifact(output)
    assert valid, errors

    with (output / "candidate_review.csv").open(encoding="utf-8-sig", newline="") as stream:
        candidates = list(csv.DictReader(stream))
    assert candidates[0]["query_text"] == "người đi xe đạp"
    assert candidates[0]["stable_id"] == "123"
    assert candidates[0]["keyframe_relpath"].endswith("002.jpg")
    with (output / "failure_sheet.csv").open(encoding="utf-8-sig", newline="") as stream:
        failures = list(csv.DictReader(stream))
    assert failures[0]["query_id"] == "q2"
    assert failures[0]["error"] == "synthetic failure"


def test_export_candidate_review_is_idempotent_after_valid_done(tmp_path):
    dataset = _write_dataset(tmp_path)
    run = _write_run(tmp_path, dataset)
    output = tmp_path / "review"
    first = export_candidate_review(dataset, run, output)
    second = export_candidate_review(dataset, run, output)
    assert first == second
