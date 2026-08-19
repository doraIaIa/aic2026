"""Unit tests for OCR BGE FAISS index builder and runtime reader (M4C)."""
from __future__ import annotations

import json
import numpy as np
import pytest

from aic2026.retrieval.ocr_bge_index import (
    BGE_DENSE_DIMENSION,
    OcrBgeIndex,
    build_ocr_bge_index,
)
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.ocr_bge import OcrBgeProvider


@pytest.fixture
def mock_bge_shards(tmp_path):
    shards_dir = tmp_path / "mock_shards"
    shards_dir.mkdir()

    # Create 10 mock shards (each with 5 vectors)
    for shard_idx in range(10):
        shard_str = f"{shard_idx:03d}"
        vecs = np.random.randn(5, BGE_DENSE_DIMENSION).astype(np.float32)
        # L2 normalize
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs = vecs / norms

        np.save(shards_dir / f"embeddings_shard_{shard_str}.npy", vecs)

        meta = []
        for i in range(5):
            meta.append({
                "text": f"Text {shard_str}_{i}",
                "type": "single",
                "video_id": "L21_V001" if shard_idx < 5 else "L24_V008",
                "keyframe_id": f"00000{i+1}",
                "text_index": i,
                "frame_idx": 15 * (i + 1),
                "pts_time": 0.5 * (i + 1),
                "bbox": [[10, 10], [50, 10]],
                "ocr_score": 0.95,
            })
        with open(shards_dir / f"metadata_shard_{shard_str}.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)

    return shards_dir


def test_ocr_bge_index_mock_build(tmp_path, mock_bge_shards, monkeypatch):
    # Monkeypatch expected rows for test
    monkeypatch.setattr("aic2026.retrieval.ocr_bge_index.EXPECTED_TOTAL_ROWS", 50)

    out_dir = tmp_path / "bge_out"
    passport = build_ocr_bge_index(mock_bge_shards, out_dir)

    assert passport["index_rows"] == 50
    assert passport["dimension"] == 1024
    assert passport["normalized"] is True
    assert (out_dir / "ocr_bge.faiss").exists()
    assert (out_dir / "ocr_bge_rowmap.jsonl").exists()

    # Test index reader health
    idx = OcrBgeIndex(out_dir)
    h = idx.health()
    assert h["status"] == "OK"
    assert h["index_rows"] == 50
    assert h["rowmap_rows"] == 50


def test_ocr_bge_provider_search(tmp_path, mock_bge_shards, monkeypatch):
    monkeypatch.setattr("aic2026.retrieval.ocr_bge_index.EXPECTED_TOTAL_ROWS", 50)
    out_dir = tmp_path / "bge_out"
    build_ocr_bge_index(mock_bge_shards, out_dir)

    provider = OcrBgeProvider(out_dir)

    # Mock query encoding to return unit vector
    def mock_encode(queries, model, tokenizer, max_length=512):
        return np.ones((len(queries), BGE_DENSE_DIMENSION), dtype=np.float32) / np.sqrt(BGE_DENSE_DIMENSION)

    monkeypatch.setattr("aic2026.retrieval.ocr_bge_index.encode_ocr_bge_queries", mock_encode)
    monkeypatch.setattr(provider.index, "_ensure_model", lambda: None)

    hits = provider.search(ProviderQuery(query_text="truy vấn mẫu", top_k=5))
    assert len(hits) == 5
    assert hits[0].score_kind == "cosine_ip_higher_is_better"
    assert hits[0].payload["evidence_type"] == "OCR_ITEM"
    assert hits[0].payload["frame_space"] == "CUSTOM"

    # Scoped query
    hits_scoped = provider.search(ProviderQuery(query_text="truy vấn mẫu", top_k=5, video_ids=("L21_V001",)))
    assert all(h.video_id == "L21_V001" for h in hits_scoped)
