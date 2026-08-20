"""Unit tests for Qwen Field-Aware BGE-Large Dense Retrieval Provider (M5B2)."""
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pandas as pd
import pytest
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.qwen_bge import (
    ACCEPTED_FIELDS,
    BGE_DENSE_DIMENSION,
    BGE_LARGE_MODEL_ID,
    EXPECTED_FIELD_COUNTS,
    QwenBgeProvider,
)


class MockBgeLargeEncoder:
    def __init__(self, dim: int = 1024):
        self.dim = dim

    def __call__(self, **kwargs: Any) -> Any:
        class Out:
            pass
        batch_size = kwargs.get("input_ids", [1]).shape[0] if hasattr(kwargs.get("input_ids", None), "shape") else 1
        out = Out()
        import torch
        # Dummy tensor [batch, seq_len, dim]
        out_tensor = torch.zeros((batch_size, 16, self.dim), dtype=torch.float32)
        # Unit vector at index 0
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
def mock_qwen_bge_environment():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source_dir = root / "source"
        faiss_dir = source_dir / "faiss"
        mappings_dir = source_dir / "mappings"
        faiss_dir.mkdir(parents=True)
        mappings_dir.mkdir(parents=True)

        db_path = root / "mapping.sqlite"
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

        # Populate synthetic FAISS and mappings for all 7 fields
        for fld in ACCEPTED_FIELDS:
            n_rows = 10
            # 1024D normalized random vectors
            vecs = np.random.randn(n_rows, 1024).astype(np.float32)
            faiss.normalize_L2(vecs)
            index = faiss.IndexFlatIP(1024)
            index.add(vecs)
            faiss.write_index(index, str(faiss_dir / f"{fld}.faiss"))

            records = []
            for i in range(n_rows):
                vid = f"L21_V00{i % 3 + 1}"
                fidx = (i + 1) * 10
                pts = (i + 1) * 0.5
                uid = f"CUSTOM:{vid}:F{fidx}"
                records.append({
                    "keyframe_global_id": f"{vid}_{i+1}",
                    "video_id": vid,
                    "keyframe_id": i + 1,
                    "frame_idx": fidx,
                    "pts_time": pts,
                    "doc_row_index": i,
                    "embedding_index": i,
                })
                conn.execute(
                    "INSERT OR IGNORE INTO qwen_frames (keyframe_uid, video_id, frame_idx, timestamp_ms, raw_pts_time, caption) VALUES (?, ?, ?, ?, ?, ?)",
                    (uid, vid, fidx, int(pts * 1000), pts, f"Caption for {uid}"),
                )
            pd.DataFrame(records).to_parquet(mappings_dir / f"{fld}.parquet")

        conn.commit()
        conn.close()

        def mock_loader():
            return MockBgeLargeEncoder(), MockTokenizer()

        provider = QwenBgeProvider(
            source_dir,
            canonical_db_path=db_path,
            model_loader=mock_loader,
        )
        try:
            yield provider
        finally:
            provider.close()


def test_qwen_bge_health(mock_qwen_bge_environment):
    provider = mock_qwen_bge_environment
    h = provider.health()
    assert h["status"] == "OK"
    assert h["dimension"] == 1024
    assert h["pooling"] == "CLS"
    assert h["max_length"] == 512
    assert h["normalization"] == "L2"
    assert h["faiss_class"] == "IndexFlatIP"
    assert h["faiss_metric"] == "METRIC_INNER_PRODUCT"
    for fld in ACCEPTED_FIELDS:
        assert fld in h["fields"]
        assert h["fields"][fld]["status"] == "OK"


def test_qwen_bge_search_explicit_fields(mock_qwen_bge_environment):
    provider = mock_qwen_bge_environment
    for fld in ACCEPTED_FIELDS:
        hits = provider.search("man riding motorbike", field=fld, top_k=5)
        assert len(hits) > 0
        assert hits[0].provider == "qwen_bge"
        assert hits[0].payload["field"] == fld
        assert hits[0].payload["entity_type"] == "FRAME"
        assert hits[0].payload["frame_space"] == "CUSTOM"
        assert hits[0].payload["score_type"] == "faiss_inner_product_l2norm"
        assert hits[0].payload["score_direction"] == "HIGHER_IS_BETTER"


def test_qwen_bge_embedding_query_override(mock_qwen_bge_environment):
    provider = mock_qwen_bge_environment
    hits = provider.search(
        query="người đi xe máy",
        embedding_query="person riding motorbike",
        field="full_text",
        top_k=5,
    )
    assert len(hits) > 0
    assert hits[0].provenance["original_query"] == "người đi xe máy"
    assert hits[0].provenance["embedding_query"] == "person riding motorbike"


def test_qwen_bge_candidate_video_scoping(mock_qwen_bge_environment):
    provider = mock_qwen_bge_environment
    # 1-video scope
    hits_1v = provider.search("test query", field="caption", candidate_video_ids=["L21_V001"], top_k=10)
    assert len(hits_1v) > 0
    assert all(h.video_id == "L21_V001" for h in hits_1v)

    # Empty scope
    hits_empty = provider.search("test query", field="caption", candidate_video_ids=[], top_k=10)
    assert len(hits_empty) == 0

    # Nonexistent video
    hits_none = provider.search("test query", field="caption", candidate_video_ids=["NONEXISTENT_VID"], top_k=10)
    assert len(hits_none) == 0


def test_qwen_bge_invalid_field_rejection(mock_qwen_bge_environment):
    provider = mock_qwen_bge_environment
    with pytest.raises(ValueError, match="Invalid field"):
        provider.search("test query", field="invalid_field_xyz")

