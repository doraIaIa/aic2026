import json
from pathlib import Path

import numpy as np
import pytest

from aic2026.core.hashing import sha256_file
from aic2026.evaluation.runner import EvalIntegrityError, run_baseline_evaluation, validate_eval_run_artifact


def _write_index_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "index"
    root.mkdir()
    (root / "clip.index").write_bytes(b"synthetic-index")
    rows = [
        {"embedding_id": 1, "keyframe_id": "V1:1", "video_id": "V1", "frame_idx": 15},
        {"embedding_id": 2, "keyframe_id": "V2:1", "video_id": "V2", "frame_idx": 30},
    ]
    (root / "metadata.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    marker = {
        "schema_version": 1,
        "task": "clip_faiss_index",
        "index_file": "clip.index",
        "metadata_file": "metadata.jsonl",
        "index_sha256": sha256_file(root / "clip.index"),
        "metadata_sha256": sha256_file(root / "metadata.jsonl"),
        "expected_count": 2,
        "processed_count": 2,
        "git_commit": "m1-test-commit",
        "model": "test-model",
        "model_revision": "test-revision",
    }
    (root / "DONE.json").write_text(json.dumps(marker), encoding="utf-8")
    return root


def _write_dataset(tmp_path: Path) -> Path:
    dataset = {
        "schema_version": 1,
        "dataset_id": "synthetic-eval",
        "dataset_version": "v1",
        "queries": [
            {
                "query_id": "good",
                "query_type": "KIS",
                "query_text": "good query",
                "question_text": None,
                "trap_category": "visual",
                "split": "dev",
                "label_status": "labeled",
                "gt_video_id": "V1",
                "gt_frame_ranges": [{"start_frame": 10, "end_frame": 20}],
                "gt_answer": None,
                "label_provenance": {"source": "synthetic-test"},
            },
            {
                "query_id": "bad",
                "query_type": "KIS",
                "query_text": "bad query",
                "question_text": None,
                "trap_category": "micro_moment",
                "split": "dev",
                "label_status": "unlabeled_reference",
                "gt_video_id": None,
                "gt_frame_ranges": [],
                "gt_answer": None,
                "label_provenance": None,
            },
        ],
    }
    path = tmp_path / "eval.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")
    return path


def test_runner_preserves_valid_result_when_another_query_fails_and_records_provenance(tmp_path: Path):
    dataset = _write_dataset(tmp_path)
    index_dir = _write_index_artifact(tmp_path)

    def encoder(text):
        if text == "bad query":
            raise RuntimeError("synthetic encoder failure")
        return np.array([1.0, 0.0], dtype=np.float32)

    marker = run_baseline_evaluation(
        dataset,
        index_dir,
        tmp_path / "run",
        split="dev",
        experiment_name="synthetic-run",
        pipeline_description="synthetic CLIP-only baseline",
        encoder=encoder,
        searcher=lambda vector, top_k: [(1, 0.9), (2, 0.2)],
    )
    assert marker["expected_items"] == 2
    assert marker["processed_items"] == 1
    assert marker["failed_items"] == 1
    valid, errors, _ = validate_eval_run_artifact(tmp_path / "run")
    assert valid, errors

    rows = [
        json.loads(line)
        for line in (tmp_path / "run" / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["query_id"] == "good" and rows[0]["score"]["metrics"]["r_at_1"] == 1
    assert rows[1]["query_id"] == "bad" and rows[1]["status"] == "ERROR"
    summary = json.loads((tmp_path / "run" / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["labeled"] == 1
    assert summary["counts"]["unlabeled"] == 1
    assert summary["pipeline"]["git_commit"]
    assert isinstance(summary["pipeline"]["git_dirty"], bool)
    assert summary["index"]["index_sha256"] == marker["index_sha256"]
    assert summary["latency_ms"]["p50"] is not None


def test_runner_is_idempotent_after_valid_done(tmp_path: Path):
    dataset = _write_dataset(tmp_path)
    index_dir = _write_index_artifact(tmp_path)
    output = tmp_path / "run"
    kwargs = dict(
        split="dev",
        experiment_name="synthetic-run",
        pipeline_description="synthetic",
        encoder=lambda text: np.array([1.0, 0.0], dtype=np.float32),
        searcher=lambda vector, top_k: [(1, 0.9)],
    )
    first = run_baseline_evaluation(dataset, index_dir, output, **kwargs)
    second = run_baseline_evaluation(dataset, index_dir, output, **kwargs)
    assert first == second
    with pytest.raises(EvalIntegrityError, match="dataset/config khác"):
        run_baseline_evaluation(
            dataset,
            index_dir,
            output,
            **dict(kwargs, experiment_name="different-run"),
        )
