"""Unit tests for SigLIP benchmark runner."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aic2026.evaluation.siglip_benchmark import run_siglip_benchmark

INDEX_DIR = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\siglip_custom_v1")
DATASET_DIR = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1")


@pytest.mark.skipif(not (INDEX_DIR / "DONE.json").exists(), reason="Production SigLIP index not built")
class TestSigLIPBenchmarkRunner:
    """Test SigLIP benchmark execution and artifact contracts."""

    def test_run_benchmark_mock_dataset(self, tmp_path: Path):
        # Create minimal test dataset
        dataset_dir = tmp_path / "test_dataset"
        dataset_dir.mkdir(parents=True)
        manifest_path = dataset_dir / "query_manifest.jsonl"
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "dataset_version": "test_v1",
                "query_id": "test-q1",
                "query_type": "KIS",
                "query_text": "người mặc áo đỏ",
                "split": "DEV",
            }) + "\n")

        output_dir = tmp_path / "bench_out"
        summary = run_siglip_benchmark(
            index_dir=INDEX_DIR,
            dataset_dir=dataset_dir,
            output_dir=output_dir,
            split="DEV",
            top_k=5,
            device="cpu",
        )

        assert summary["status"] == "PASS"
        assert summary["lane"] == "siglip_custom"
        assert summary["query_count"] == 1
        assert summary["unscored_query_count"] == 1

        run_id = summary["run_id"]
        run_dir = output_dir / run_id
        assert (run_dir / "DONE.json").is_file()
        assert (run_dir / "summary.json").is_file()
        assert (run_dir / "summary.md").is_file()
        assert (run_dir / "per_query.jsonl").is_file()

        # Check per_query content
        records = [json.loads(line) for line in open(run_dir / "per_query.jsonl", "r", encoding="utf-8")]
        assert len(records) == 1
        assert records[0]["query_id"] == "test-q1"
        assert len(records[0]["predictions_top_10"]) == 5
        assert records[0]["predictions_top_10"][0]["keyframe_uid"].startswith("CUSTOM:")
