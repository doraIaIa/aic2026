"""Unit tests for Qwen Text Benchmark Runners (M5B)."""
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from aic2026.evaluation.qwen_text_benchmark import run_qwen_text_benchmark
from aic2026.evaluation.qwen_text_pair_benchmark import run_qwen_text_pair_benchmark
from aic2026.retrieval.qwen_bge_index import DOCUMENT_POLICY_ID


class MockEncoder:
    def __init__(self, dim: int = 1024):
        self.dim = dim

    def __call__(self, **kwargs: Any) -> Any:
        class Out:
            pass
        batch_size = kwargs.get("input_ids", [1]).shape[0] if hasattr(kwargs.get("input_ids", None), "shape") else 1
        out = Out()
        import torch
        out_tensor = torch.zeros((batch_size, 10, self.dim), dtype=torch.float32)
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
def mock_benchmark_env():
    import faiss

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "mapping.sqlite"
        bge_dir = tmp_path / "bge_index"
        bge_dir.mkdir()
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        out_dir = tmp_path / "out"

        # 1. Mock SQLite mapping with qwen_caption_fts
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE qwen_frames (
                keyframe_uid TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                frame_idx INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                raw_pts_time REAL NOT NULL,
                objects_json TEXT NOT NULL DEFAULT '[]',
                attributes_json TEXT NOT NULL DEFAULT '[]',
                spatial_relations_json TEXT NOT NULL DEFAULT '[]',
                counts_json TEXT NOT NULL DEFAULT '[]',
                scene_json TEXT NOT NULL DEFAULT '[]',
                visible_actions_json TEXT NOT NULL DEFAULT '[]',
                caption TEXT NOT NULL DEFAULT '',
                semantic_status TEXT NOT NULL DEFAULT 'OK',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE qwen_caption_fts USING fts5(
                keyframe_uid UNINDEXED,
                video_id UNINDEXED,
                caption_raw,
                caption_norm,
                caption_accentless,
                tokenize = 'unicode61'
            );
        """)

        # Add 116,767 dummy rows for health check
        frames = [
            (
                f"CUSTOM:L21_V001:F{i}",
                "L21_V001",
                i,
                i * 1000,
                float(i),
                "[]",
                "[]",
                "[]",
                "[]",
                "[]",
                "[]",
                "motorcycle riding on street" if i == 1 else "other scene",
                "OK",
            )
            for i in range(1, 116768)
        ]
        fts_rows = [
            (
                f"CUSTOM:L21_V001:F{i}",
                "L21_V001",
                "motorcycle riding on street" if i == 1 else "other scene",
                "motorcycle riding on street" if i == 1 else "other scene",
                "motorcycle riding on street" if i == 1 else "other scene",
            )
            for i in range(1, 116768)
        ]
        conn.executemany("INSERT INTO qwen_frames VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", frames)
        conn.executemany("INSERT INTO qwen_caption_fts VALUES (?, ?, ?, ?, ?)", fts_rows)
        conn.commit()
        conn.close()

        # 2. Mock FAISS index
        dim = 1024
        index = faiss.IndexFlatIP(dim)
        vecs = np.zeros((1, dim), dtype=np.float32)
        vecs[0, 0] = 1.0
        index.add(vecs)
        faiss.write_index(index, str(bge_dir / "qwen_bge.faiss"))

        with open(bge_dir / "qwen_bge_rowmap.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "dense_row": 0,
                "keyframe_uid": "CUSTOM:L21_V001:F1",
                "video_id": "L21_V001",
                "frame_idx": 1,
                "timestamp_ms": 1000,
                "document_policy_id": DOCUMENT_POLICY_ID,
                "document_sha256": "sha1",
                "caption": "motorcycle riding on street",
            }) + "\n")

        with open(bge_dir / "qwen_bge_passport.json", "w", encoding="utf-8") as f:
            json.dump({"status": "PASS", "index_rows": 1}, f)

        # 3. Mock query manifest
        manifest_file = dataset_dir / "query_manifest.jsonl"
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"query_id": "Q001", "query_text": "motorcycle", "split": "DEV"}) + "\n")

        yield db_path, bge_dir, dataset_dir, out_dir


def test_run_qwen_bm25_benchmark(mock_benchmark_env):
    db_path, _, dataset_dir, out_dir = mock_benchmark_env
    bm25_out = out_dir / "bm25"
    summary = run_qwen_text_benchmark("qwen_bm25", db_path, dataset_dir, bm25_out, run_id="test_bm25_001")

    assert summary["lane_id"] == "qwen_bm25"
    assert summary["dataset_query_count"] == 1
    assert summary["quality_eval_status"] == "BLOCKED_BY_GROUND_TRUTH"
    assert (bm25_out / "summary.json").exists()
    assert (bm25_out / "DONE.json").exists()


def test_run_qwen_text_pair_benchmark(mock_benchmark_env):
    db_path, bge_dir, dataset_dir, out_dir = mock_benchmark_env
    pair_out = out_dir / "pair"
    mock_loader = lambda: (MockEncoder(1024), MockTokenizer())
    summary = run_qwen_text_pair_benchmark(
        db_path, bge_dir, dataset_dir, pair_out, run_id="test_pair_001", model_loader=mock_loader
    )

    assert summary["comparison"] == "qwen_bm25_vs_qwen_bge"
    assert summary["query_count"] == 1
    assert "mean_frame_jaccard" in summary["divergence_metrics"]
    assert (pair_out / "summary.json").exists()
    assert (pair_out / "DONE.json").exists()
