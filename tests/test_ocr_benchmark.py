"""Unit tests for OCR benchmark runners (M4C)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from aic2026.evaluation.ocr_benchmark import run_ocr_benchmark
from aic2026.evaluation.ocr_pair_benchmark import run_ocr_three_way_comparison


@pytest.fixture
def mock_benchmark_env(tmp_path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()

    manifest_p = dataset_dir / "query_manifest.jsonl"
    with open(manifest_p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"dataset_version": "v1", "query_id": "q1", "query_text": "HTV9", "split": "DEV"}) + "\n")
        f.write(json.dumps({"dataset_version": "v1", "query_id": "q2", "query_text": "Cần Thơ", "split": "DEV"}) + "\n")

    return dataset_dir


def test_ocr_benchmark_runner_mock(tmp_path, mock_benchmark_env, monkeypatch):
    out_dir = tmp_path / "eval_out"

    # Mock provider
    mock_provider = MagicMock()
    mock_hit = MagicMock()
    mock_hit.rank = 1
    mock_hit.evidence_id = "OCR:CUSTOM:L21_V001:F15:T0"
    mock_hit.video_id = "L21_V001"
    mock_hit.start_sec = 0.5
    mock_hit.end_sec = 0.5
    mock_hit.raw_score = -12.5
    mock_hit.score_kind = "bm25_lower_is_better"
    mock_hit.payload = {"text_raw": "HTV9", "ocr_confidence": 0.98}
    mock_provider.search.return_value = [mock_hit]

    monkeypatch.setattr("aic2026.evaluation.ocr_benchmark.OcrBm25Provider", lambda path: mock_provider)

    summary = run_ocr_benchmark("ocr_bm25", tmp_path / "db.sqlite", mock_benchmark_env, out_dir, split="DEV", top_k=5)

    assert summary["lane"] == "ocr_bm25"
    assert summary["queries_evaluated"] == 2
    assert summary["ground_truth_status"] == "BLOCKED_BY_GROUND_TRUTH"
    assert summary["gt_summary"]["scored_queries"] == 0
    assert summary["gt_summary"]["unscored_queries"] == 2
    assert (out_dir / "ocr_ocr_bm25_dev_summary.json").exists()


def test_ocr_three_way_comparison_mock(tmp_path, mock_benchmark_env, monkeypatch):
    out_dir = tmp_path / "eval_out"

    mock_p = MagicMock()
    mock_hit = MagicMock()
    mock_hit.rank = 1
    mock_hit.evidence_id = "OCR:CUSTOM:L21_V001:F15:T0"
    mock_hit.video_id = "L21_V001"
    mock_hit.payload = {"text_raw": "Sample"}
    mock_p.search.return_value = [mock_hit]

    monkeypatch.setattr("aic2026.evaluation.ocr_pair_benchmark.OcrBm25Provider", lambda path: mock_p)
    monkeypatch.setattr("aic2026.evaluation.ocr_pair_benchmark.OcrTrigramProvider", lambda path, canonical_db_path=None: mock_p)
    monkeypatch.setattr("aic2026.evaluation.ocr_pair_benchmark.OcrBgeProvider", lambda path, canonical_db_path=None: mock_p)

    summary = run_ocr_three_way_comparison(
        tmp_path / "db.sqlite",
        tmp_path / "trigram_dir",
        tmp_path / "bge_dir",
        mock_benchmark_env,
        out_dir,
        split="DEV",
        top_k=5,
    )

    assert summary["benchmark"] == "OCR_THREE_WAY_COMPARISON"
    assert summary["queries_count"] == 2
    assert (out_dir / "ocr_three_way_comparison_dev.json").exists()
    assert (out_dir / "ocr_three_way_comparison_dev.md").exists()
