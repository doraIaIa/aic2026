"""Unit tests for SigLIP2 CUSTOM retrieval lane."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from aic2026.retrieval.providers.base import ProviderIntegrityError, ProviderQuery, ProviderUnavailableError
from aic2026.retrieval.providers.siglip import (
    SIGLIP_DIMENSION,
    SIGLIP_MAX_LENGTH,
    SIGLIP_MODEL_ID,
    SIGLIP_PADDING,
    SIGLIP_TRUNCATION,
    SigLIPProvider,
)
from aic2026.retrieval.siglip_index import build_siglip_index


@pytest.fixture
def mock_siglip_index_dir(tmp_path: Path) -> Path:
    """Create a minimal mock SigLIP FAISS index directory."""
    import faiss

    index_dir = tmp_path / "siglip_custom_v1"
    index_dir.mkdir(parents=True, exist_ok=True)

    # 10 mock vectors (768D, unit normalized)
    rng = np.random.RandomState(42)
    raw = rng.randn(10, 768).astype(np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    vectors = raw / norms

    index = faiss.IndexFlatIP(768)
    index.add(vectors)
    index_path = index_dir / "siglip_custom.faiss"
    faiss.write_index(index, str(index_path))

    # Rowmap
    rowmap_entries = []
    vids = ["L21_V001", "L21_V001", "L21_V002", "L21_V002", "L22_V001",
            "L22_V001", "L22_V002", "L22_V002", "L23_V001", "L23_V001"]
    for i in range(10):
        rowmap_entries.append({
            "faiss_row": i,
            "keyframe_uid": f"CUSTOM:{vids[i]}:F{i * 100}",
            "video_id": vids[i],
            "video_ordinal": i // 2,
            "frame_idx": i * 100,
            "timestamp_ms": i * 4000,
            "raw_pts_time": float(i * 4.0),
            "embedding_index": i % 2,
            "image_relpath": f"output/keyframes/{vids[i]}/{i+1:06d}.jpg",
        })

    rowmap_path = index_dir / "siglip_custom_rowmap.jsonl"
    with open(rowmap_path, "w", encoding="utf-8") as f:
        for entry in rowmap_entries:
            f.write(json.dumps(entry) + "\n")

    # DONE.json
    import hashlib
    def sha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()

    done = {
        "task": "siglip_faiss_index",
        "schema_version": 1,
        "index_file": "siglip_custom.faiss",
        "rowmap_file": "siglip_custom_rowmap.jsonl",
        "passport_file": "siglip_custom_passport.json",
        "index_sha256": sha(index_path),
        "rowmap_sha256": sha(rowmap_path),
        "row_count": 10,
        "dimension": 768,
        "metric": "INNER_PRODUCT",
        "self_vector_top1": "10/10",
        "build_duration_sec": 0.1,
        "created_at": "2026-08-19T00:00:00Z",
        "status": "READY",
    }
    with open(index_dir / "DONE.json", "w", encoding="utf-8") as f:
        json.dump(done, f, indent=2)

    return index_dir


def _mock_model_loader():
    """Mock encoder that returns deterministic unit-normalized 768D vectors."""
    class MockModel:
        def get_text_features(self, **kwargs):
            import torch
            batch_size = kwargs.get("input_ids", torch.zeros(1, 64)).shape[0]
            rng = np.random.RandomState(123)
            raw = rng.randn(batch_size, 768).astype(np.float32)
            norms = np.linalg.norm(raw, axis=1, keepdims=True)
            return torch.tensor(raw / norms)

    class MockProcessor:
        def __call__(self, text, **kwargs):
            import torch
            if isinstance(text, str):
                text = [text]
            return {"input_ids": torch.zeros((len(text), 64), dtype=torch.long)}

    return MockModel(), MockProcessor()


class TestSigLIPContract:
    """Test SigLIP2 constants and model contracts."""

    def test_frozen_constants(self):
        assert SIGLIP_MODEL_ID == "google/siglip2-base-patch16-224"
        assert SIGLIP_DIMENSION == 768
        assert SIGLIP_MAX_LENGTH == 64
        assert SIGLIP_PADDING == "max_length"
        assert SIGLIP_TRUNCATION is True

    def test_query_validation(self, mock_siglip_index_dir):
        provider = SigLIPProvider(mock_siglip_index_dir, model_loader=_mock_model_loader)
        with pytest.raises(ValueError):
            provider.encode_queries([])
        with pytest.raises(ValueError):
            provider.encode_queries(["   "])

    def test_mock_encoding_shape_and_norm(self, mock_siglip_index_dir):
        provider = SigLIPProvider(mock_siglip_index_dir, model_loader=_mock_model_loader)
        vecs = provider.encode_queries(["một người đang nấu ăn", "xe đạp"])
        assert vecs.shape == (2, 768)
        assert vecs.dtype == np.float32
        assert np.isfinite(vecs).all()
        norms = np.linalg.norm(vecs, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)


class TestSigLIPProviderSearch:
    """Test SigLIP provider search, scoping, and results."""

    def test_provider_health(self, mock_siglip_index_dir):
        provider = SigLIPProvider(mock_siglip_index_dir, model_loader=_mock_model_loader)
        h = provider.health()
        assert h["status"] == "OK"
        assert h["index_rows"] == 10
        assert h["rowmap_rows"] == 10
        assert h["dimension"] == 768
        assert h["frame_space"] == "CUSTOM"

    def test_unscoped_search(self, mock_siglip_index_dir):
        provider = SigLIPProvider(mock_siglip_index_dir, model_loader=_mock_model_loader)
        query = ProviderQuery(query_text="người đi xe", top_k=5)
        hits = provider.search(query)
        assert len(hits) == 5
        for i, h in enumerate(hits):
            assert h.rank == i + 1
            assert h.provider == "siglip_custom"
            assert h.evidence_id.startswith("CUSTOM:")
            assert h.score_kind == "cosine_ip_higher_is_better"
            assert "keyframe_uid" in h.payload
            assert "timestamp_ms" in h.payload
            assert "frame_idx" in h.payload
            assert h.payload["frame_space"] == "CUSTOM"

    def test_scoped_search(self, mock_siglip_index_dir):
        provider = SigLIPProvider(mock_siglip_index_dir, model_loader=_mock_model_loader)
        allowed = ("L21_V001", "L21_V002")
        query = ProviderQuery(query_text="người đi xe", top_k=5, video_ids=allowed)
        hits = provider.search(query)
        assert len(hits) <= 4  # only 4 keyframes in L21_V001 and L21_V002
        for h in hits:
            assert h.video_id in allowed

    def test_empty_scope(self, mock_siglip_index_dir):
        provider = SigLIPProvider(mock_siglip_index_dir, model_loader=_mock_model_loader)
        query = ProviderQuery(query_text="người đi xe", top_k=5, video_ids=("L99_V999",))
        hits = provider.search(query)
        assert len(hits) == 0

    def test_corrupted_index_checksum(self, mock_siglip_index_dir):
        done_path = mock_siglip_index_dir / "DONE.json"
        done = json.loads(done_path.read_text("utf-8"))
        done["index_sha256"] = "wrong_hash"
        done_path.write_text(json.dumps(done), "utf-8")

        provider = SigLIPProvider(mock_siglip_index_dir, model_loader=_mock_model_loader)
        h = provider.health()
        assert h["status"] == "ERROR"
        with pytest.raises(ProviderUnavailableError):
            provider.search(ProviderQuery(query_text="test", top_k=5))
