import json
import pytest
from pathlib import Path
from aic2026.evaluation.asr_benchmark import run_asr_benchmark
from aic2026.evaluation.asr_pair_benchmark import run_asr_pair_benchmark

DB_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
DATASET_DIR = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1")


def test_asr_bm25_benchmark_execution(tmp_path):
    if not DB_PATH.exists() or not DATASET_DIR.exists():
        pytest.skip("Prerequisites missing for benchmark test")

    out_dir = tmp_path / "bm25_eval"
    summary = run_asr_benchmark(
        lane="asr_bm25",
        target_path=DB_PATH,
        dataset_dir=DATASET_DIR,
        output_dir=out_dir,
        split="DEV",
        top_k=5,
    )

    assert summary["lane"] == "asr_bm25"
    assert summary["split"] == "DEV"
    assert summary["total_queries"] == 15
    assert summary["quality_status"] == "BLOCKED_BY_GROUND_TRUTH"
    assert summary["scored_queries"] == 0
    assert summary["unscored_queries"] == 15
    assert (out_dir / "per_query.jsonl").exists()
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "summary.md").exists()
    assert (out_dir / "DONE.json").exists()

    # Validate per_query entries
    with open(out_dir / "per_query.jsonl", "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    assert len(records) == 15
    for r in records:
        assert r["split"] == "DEV"
        assert r["quality_status"] == "BLOCKED_BY_GROUND_TRUTH"
        assert "latency_ms" in r
