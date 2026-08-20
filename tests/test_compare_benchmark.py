"""Unit tests for M6 Compare Benchmark Suite."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aic2026.evaluation.compare_benchmark import (
    run_compare_dev_benchmark,
    run_structured_functional_probes,
)


def test_compare_benchmark_manifest_and_summary_generation() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        out_dir = tmp_path / "output"

        # Create dummy query_manifest.jsonl with 2 queries
        manifest_file = dataset_dir / "query_manifest.jsonl"
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"query_id": "Q01", "query": "dog playing", "split": "DEV"}) + "\n")
            f.write(json.dumps({"query_id": "Q02", "query": "car on street", "split": "DEV"}) + "\n")

        dummy_db = tmp_path / "mapping.sqlite"
        dummy_db.touch()

        # Mock CompareOrchestrator.execute_compare
        with patch("aic2026.evaluation.compare_benchmark.CompareOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.execute_compare.return_value = {
                "status": "OK",
                "mode": "COMPARE",
                "lanes": [
                    {
                        "lane": "siglip_custom",
                        "status": "OK",
                        "latency_ms": 15.0,
                        "result_count": 5,
                        "results": [{"video_id": "V001"}],
                    }
                ],
                "diagnostics": {
                    "video_union_count": 1,
                    "per_lane_unique_videos": {"siglip_custom": 1},
                    "pairwise_video_overlap": [],
                },
            }
            mock_orch_cls.return_value = mock_orch

            summary = run_compare_dev_benchmark(
                database_path=dummy_db,
                dataset_dir=dataset_dir,
                output_dir=out_dir,
                lane_profile=[{"lane": "siglip_custom", "enabled": True}],
            )

            assert summary["benchmark"] == "compare_dev_v1"
            assert summary["total_queries"] == 2
            assert summary["scored_queries"] == 0
            assert summary["unscored_queries"] == 2
            assert summary["quality_status"] == "BLOCKED_BY_GROUND_TRUTH"

            # Check files created
            assert (out_dir / "manifest.json").is_file()
            assert (out_dir / "summary.json").is_file()
            assert (out_dir / "per_query.jsonl").is_file()
            assert (out_dir / "DONE").is_file()

            per_query_lines = open(out_dir / "per_query.jsonl", "r", encoding="utf-8").readlines()
            assert len(per_query_lines) == 2


def test_structured_functional_probes_execution() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        dummy_db = Path(tmp_dir) / "mapping.sqlite"
        dummy_db.touch()

        with patch("aic2026.evaluation.compare_benchmark.CompareOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.execute_compare.return_value = {
                "status": "OK",
                "lanes": [{"lane": "test", "status": "OK", "result_count": 2}],
            }
            mock_orch_cls.return_value = mock_orch

            res = run_structured_functional_probes(database_path=dummy_db)
            assert res["qwen_probes_count"] == 5
            assert res["btc_probes_count"] == 5
            assert res["combined_probes_count"] == 3
            assert res["all_qwen_ok"] is True
            assert res["all_btc_ok"] is True
            assert res["all_combined_ok"] is True
