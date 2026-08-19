import json
import pytest
from pathlib import Path

from aic2026.evaluation.media_benchmark import run_media_bm25_benchmark


DB_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
DATASET_DIR = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1")


def test_media_bm25_benchmark_runner(tmp_path):
    if not DB_PATH.exists():
        pytest.skip(f"Database not found at {DB_PATH}")
    if not DATASET_DIR.exists():
        pytest.skip(f"Dataset directory not found at {DATASET_DIR}")

    out_dir = tmp_path / "media_benchmark_test"
    summary = run_media_bm25_benchmark(
        db_path=DB_PATH,
        dataset_dir=DATASET_DIR,
        output_dir=out_dir,
        split="DEV",
        top_k=5,
    )

    assert summary["lane"] == "media_bm25"
    assert summary["entity_type"] == "VIDEO"
    assert summary["frame_space"] == "NONE"
    assert summary["total_queries"] > 0
    assert summary["quality_status"] in {"PASS", "BLOCKED_BY_GROUND_TRUTH"}
    assert summary["fabricated_frames"] == 0
    assert summary["fabricated_timestamps"] == 0
    assert summary["frame_recall_status"] == "NOT_APPLICABLE"
    assert summary["range_recall_status"] == "NOT_APPLICABLE"

    # Verify output files
    assert (out_dir / "per_query.jsonl").is_file()
    assert (out_dir / "summary.json").is_file()
    assert (out_dir / "summary.md").is_file()
    assert (out_dir / "DONE.json").is_file()

    # Check per_query records
    lines = [json.loads(line) for line in open(out_dir / "per_query.jsonl", "r", encoding="utf-8")]
    assert len(lines) == summary["total_queries"]
    for r in lines:
        assert r["entity_type"] == "VIDEO"
        assert r["frame_range_status"] == "NOT_APPLICABLE"
