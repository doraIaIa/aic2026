"""Unit tests for Qwen Field-Aware BGE-Large Benchmark Runner (M5B2)."""
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pandas as pd
import pytest
from aic2026.evaluation.qwen_bge_benchmark import (
    run_all_fields_diagnostic_benchmark,
    run_qwen_bge_benchmark,
)
from aic2026.retrieval.providers.qwen_bge import ACCEPTED_FIELDS


class MockBgeLargeEncoder:
    def __init__(self, dim: int = 1024):
        self.dim = dim

    def __call__(self, **kwargs: Any) -> Any:
        class Out:
            pass
        batch_size = kwargs.get("input_ids", [1]).shape[0] if hasattr(kwargs.get("input_ids", None), "shape") else 1
        out = Out()
        import torch
        out_tensor = torch.zeros((batch_size, 16, self.dim), dtype=torch.float32)
        out_tensor[:, 0, 0] = 1.0
        out.__getitem__ = lambda self, idx: out_tensor if idx == 0 else None
        return (out_tensor,)


class MockTokenizer:
    def __call__(self, texts: list[str], **kwargs: Any) -> dict[str, Any]:
        import torch
        return {
            "input_ids": torch.ones((len(texts), 16), dtype=torch.long),
            "attention_mask": torch.ones((len(texts), 16), dtype=torch.long),
        }


@pytest.fixture
def mock_bge_benchmark_env(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_dir = tmp_path / "source"
        faiss_dir = source_dir / "faiss"
        mappings_dir = source_dir / "mappings"
        faiss_dir.mkdir(parents=True)
        mappings_dir.mkdir(parents=True)

        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        out_dir = tmp_path / "out"

        for fld in ACCEPTED_FIELDS:
            vecs = np.random.randn(10, 1024).astype(np.float32)
            faiss.normalize_L2(vecs)
            index = faiss.IndexFlatIP(1024)
            index.add(vecs)
            faiss.write_index(index, str(faiss_dir / f"{fld}.faiss"))

            records = [
                {
                    "keyframe_global_id": f"L21_V001_{i+1}",
                    "video_id": "L21_V001",
                    "keyframe_id": i + 1,
                    "frame_idx": (i + 1) * 10,
                    "pts_time": (i + 1) * 0.5,
                    "doc_row_index": i,
                    "embedding_index": i,
                }
                for i in range(10)
            ]
            pd.DataFrame(records).to_parquet(mappings_dir / f"{fld}.parquet")

        manifest_file = dataset_dir / "query_manifest.jsonl"
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"query_id": "Q01", "query_text": "motorcycle street", "split": "DEV"}) + "\n")
            f.write(json.dumps({"query_id": "Q02", "query_text": "city scenery", "split": "DEV"}) + "\n")

        from aic2026.retrieval.providers.qwen_bge import QwenBgeProvider
        monkeypatch.setattr(
            QwenBgeProvider,
            "_default_model_loader",
            lambda self: (MockBgeLargeEncoder(), MockTokenizer()),
        )

        yield source_dir, dataset_dir, out_dir


def test_qwen_bge_benchmark_runner(mock_bge_benchmark_env):
    source_dir, dataset_dir, out_dir = mock_bge_benchmark_env
    summary = run_qwen_bge_benchmark(
        source_dir,
        dataset_dir,
        out_dir,
        field="full_text",
        split="DEV",
        top_k=5,
    )

    assert summary["lane_id"] == "qwen_bge"
    assert summary["field"] == "full_text"
    assert summary["query_count"] == 2
    assert summary["scored_query_count"] == 0
    assert summary["unscored_query_count"] == 2
    assert summary["quality_evaluation_status"] == "BLOCKED_BY_GROUND_TRUTH"

    summary_file = out_dir / "benchmark_summary.json"
    results_file = out_dir / "per_query_results.json"
    assert summary_file.exists()
    assert results_file.exists()


def test_qwen_bge_all_fields_diagnostic(mock_bge_benchmark_env):
    source_dir, dataset_dir, out_dir = mock_bge_benchmark_env
    diag_summary = run_all_fields_diagnostic_benchmark(
        source_dir,
        dataset_dir,
        out_dir,
        split="DEV",
        top_k=5,
    )
    assert diag_summary["benchmark_type"] == "independent_7_field_diagnostic"
    for fld in ACCEPTED_FIELDS:
        assert fld in diag_summary["fields"]
