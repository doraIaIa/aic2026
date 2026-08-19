"""Unit tests for Qwen BGE Provider Lane (M5B)."""
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.qwen_bge import QwenBgeProvider
from aic2026.retrieval.qwen_bge_index import DOCUMENT_POLICY_ID


class MockEncoder:
    """Mock encoder simulating BGE-M3."""
    def __init__(self, dim: int = 1024):
        self.dim = dim

    def __call__(self, **kwargs: Any) -> Any:
        class Out:
            pass
        batch_size = kwargs.get("input_ids", [1]).shape[0] if hasattr(kwargs.get("input_ids", None), "shape") else 1
        out = Out()
        import torch
        # Return deterministic mock vector
        out_tensor = torch.zeros((batch_size, 10, self.dim), dtype=torch.float32)
        out_tensor[:, 0, 0] = 1.0  # Unit vector along axis 0
        out.__getitem__ = lambda self, idx: out_tensor if idx == 0 else None
        return (out_tensor,)


class MockTokenizer:
    """Mock tokenizer."""
    def __call__(self, texts: list[str], **kwargs: Any) -> dict[str, Any]:
        import torch
        return {
            "input_ids": torch.ones((len(texts), 16), dtype=torch.long),
            "attention_mask": torch.ones((len(texts), 16), dtype=torch.long),
        }


@pytest.fixture
def mock_qwen_bge_env():
    import faiss

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        faiss_file = tmp_path / "qwen_bge.faiss"
        rowmap_file = tmp_path / "qwen_bge_rowmap.jsonl"
        passport_file = tmp_path / "qwen_bge_passport.json"

        dim = 1024
        index = faiss.IndexFlatIP(dim)
        vecs = np.zeros((3, dim), dtype=np.float32)
        vecs[0, 0] = 1.0  # Aligns with mock encoder query vector
        vecs[1, 1] = 1.0
        vecs[2, 0] = 0.8
        vecs[2, 1] = 0.6
        index.add(vecs)
        faiss.write_index(index, str(faiss_file))

        rowmap_entries = [
            {
                "dense_row": 0,
                "keyframe_uid": "CUSTOM:L21_V001:F100",
                "video_id": "L21_V001",
                "frame_idx": 100,
                "timestamp_ms": 4000,
                "document_policy_id": DOCUMENT_POLICY_ID,
                "document_sha256": "sha0",
                "caption": "Motorcycle on road",
            },
            {
                "dense_row": 1,
                "keyframe_uid": "CUSTOM:L21_V001:F200",
                "video_id": "L21_V001",
                "frame_idx": 200,
                "timestamp_ms": 8000,
                "document_policy_id": DOCUMENT_POLICY_ID,
                "document_sha256": "sha1",
                "caption": "Car on highway",
            },
            {
                "dense_row": 2,
                "keyframe_uid": "CUSTOM:L21_V002:F300",
                "video_id": "L21_V002",
                "frame_idx": 300,
                "timestamp_ms": 12000,
                "document_policy_id": DOCUMENT_POLICY_ID,
                "document_sha256": "sha2",
                "caption": "Motorcycle in city",
            },
        ]
        with open(rowmap_file, "w", encoding="utf-8") as f:
            for r in rowmap_entries:
                f.write(json.dumps(r) + "\n")

        with open(passport_file, "w", encoding="utf-8") as f:
            json.dump({"status": "PASS", "index_rows": 3}, f)

        mock_loader = lambda: (MockEncoder(dim), MockTokenizer())
        provider = QwenBgeProvider(tmp_path, model_loader=mock_loader)
        try:
            yield provider
        finally:
            provider.close()


def test_qwen_bge_search(mock_qwen_bge_env):
    provider = mock_qwen_bge_env

    hits = provider.search("motorcycle on road", top_k=2)
    assert len(hits) == 2
    assert hits[0].rank == 1
    assert hits[0].payload["keyframe_uid"] == "CUSTOM:L21_V001:F100"
    assert hits[0].payload["entity_type"] == "FRAME"
    assert hits[0].payload["frame_space"] == "CUSTOM"
    assert hits[0].score_kind == "higher_is_better"
    assert pytest.approx(hits[0].raw_score, rel=1e-3) == 1.0


def test_qwen_bge_candidate_scoping(mock_qwen_bge_env):
    provider = mock_qwen_bge_env

    # Scope to L21_V002
    hits = provider.search("motorcycle", candidate_video_ids=["L21_V002"])
    assert len(hits) == 1
    assert hits[0].video_id == "L21_V002"
    assert hits[0].payload["keyframe_uid"] == "CUSTOM:L21_V002:F300"

    # Empty scope
    assert provider.search("motorcycle", candidate_video_ids=[]) == []
