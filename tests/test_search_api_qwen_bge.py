"""Unit tests for Qwen Field-Aware BGE-Large HTTP API endpoints (M5B2)."""
import json
import sqlite3
import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pandas as pd
import pytest
from aic2026.retrieval.providers.qwen_bge import ACCEPTED_FIELDS, QwenBgeProvider
from aic2026.search.api import AsrSearchApi


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
def mock_api_qwen_bge(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_dir = tmp_path / "source"
        faiss_dir = source_dir / "faiss"
        mappings_dir = source_dir / "mappings"
        faiss_dir.mkdir(parents=True)
        mappings_dir.mkdir(parents=True)

        db_path = tmp_path / "mapping.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE qwen_frames (
                keyframe_uid TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                frame_idx INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                raw_pts_time REAL NOT NULL,
                caption TEXT NOT NULL DEFAULT '',
                semantic_status TEXT NOT NULL DEFAULT 'OK'
            );
        """)

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

        conn.commit()
        conn.close()

        monkeypatch.setattr(
            QwenBgeProvider,
            "_default_model_loader",
            lambda self: (MockBgeLargeEncoder(), MockTokenizer()),
        )

        bge_provider = QwenBgeProvider(source_dir, canonical_db_path=db_path)
        api = AsrSearchApi(db_path, qwen_bge_provider=bge_provider)
        try:
            yield api
        finally:
            api.close()


def test_qwen_bge_api_health(mock_api_qwen_bge):
    api = mock_api_qwen_bge
    code, payload = api.qwen_bge_health()
    assert code == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["dimension"] == 1024


def test_qwen_bge_api_search(mock_api_qwen_bge):
    api = mock_api_qwen_bge
    code, payload = api.qwen_bge_search({
        "query": "người đi xe máy",
        "embedding_query": "man on motorcycle",
        "field": "caption",
        "top_k": 5,
    })
    assert code == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["lane"] == "qwen_bge"
    assert payload["field"] == "caption"
    assert payload["embedding_query"] == "man on motorcycle"
    assert payload["count"] > 0
    assert payload["hits"][0]["video_id"] == "L21_V001"


def test_qwen_bge_api_validation(mock_api_qwen_bge):
    api = mock_api_qwen_bge
    # Empty query
    code, payload = api.qwen_bge_search({"query": ""})
    assert code == HTTPStatus.BAD_REQUEST
    assert payload["status"] == "ERROR"

    # Invalid field
    code, payload = api.qwen_bge_search({"query": "valid query", "field": "unknown_field"})
    assert code == HTTPStatus.BAD_REQUEST
    assert payload["status"] == "ERROR"
