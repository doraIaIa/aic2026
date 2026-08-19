"""Unit tests for Qwen BM25 and Qwen BGE HTTP API endpoints (M5B)."""
import json
import sqlite3
import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
import numpy as np
from aic2026.retrieval.providers.qwen_bge import QwenBgeProvider
from aic2026.retrieval.providers.qwen_bm25 import QwenBm25Provider
from aic2026.retrieval.qwen_bge_index import DOCUMENT_POLICY_ID
from aic2026.search.api import AsrSearchApi



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
def mock_api_qwen_text():
    import faiss

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "mapping.sqlite"
        bge_dir = tmp_path / "bge_index"
        bge_dir.mkdir()

        # 1. SQLite mapping with qwen_caption_fts
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
                "motorcycle on road" if i == 1 else "other scene",
                "OK",
            )
            for i in range(1, 116768)
        ]
        fts_rows = [
            (
                f"CUSTOM:L21_V001:F{i}",
                "L21_V001",
                "motorcycle on road" if i == 1 else "other scene",
                "motorcycle on road" if i == 1 else "other scene",
                "motorcycle on road" if i == 1 else "other scene",
            )
            for i in range(1, 116768)
        ]
        conn.executemany("INSERT INTO qwen_frames VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", frames)
        conn.executemany("INSERT INTO qwen_caption_fts VALUES (?, ?, ?, ?, ?)", fts_rows)
        conn.commit()
        conn.close()


        # 2. FAISS index
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
                "caption": "motorcycle on road",
            }) + "\n")

        with open(bge_dir / "qwen_bge_passport.json", "w", encoding="utf-8") as f:
            json.dump({"status": "PASS", "index_rows": 1}, f)

        bm25_prov = QwenBm25Provider(db_path)
        mock_loader = lambda: (MockEncoder(dim), MockTokenizer())
        bge_prov = QwenBgeProvider(bge_dir, model_loader=mock_loader)

        api = AsrSearchApi(
            database=db_path,
            qwen_bm25_provider=bm25_prov,
            qwen_bge_provider=bge_prov,
        )
        try:
            yield api
        finally:
            bm25_prov.close()
            bge_prov.close()


def test_api_qwen_bm25_endpoints(mock_api_qwen_text):
    api = mock_api_qwen_text

    # Health
    status, payload = api.qwen_bm25_health()
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["lane_id"] == "qwen_bm25"
    assert payload["qwen_fts_rows"] == 116767

    # Search
    status, payload = api.qwen_bm25_search({"query": "motorcycle", "top_k": 5})
    assert status == HTTPStatus.OK
    assert payload["lane"] == "qwen_bm25"
    assert payload["entity_type"] == "FRAME"
    assert payload["frame_space"] == "CUSTOM"
    assert len(payload["hits"]) == 1

    # Empty query validation
    status, payload = api.qwen_bm25_search({"query": ""})
    assert status == HTTPStatus.BAD_REQUEST


def test_api_qwen_bge_endpoints(mock_api_qwen_text):
    api = mock_api_qwen_text

    # Health
    status, payload = api.qwen_bge_health()
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["lane_id"] == "qwen_bge"
    assert payload["index_rows"] == 1

    # Search
    status, payload = api.qwen_bge_search({"query": "motorcycle", "top_k": 5})
    assert status == HTTPStatus.OK
    assert payload["lane"] == "qwen_bge"
    assert payload["entity_type"] == "FRAME"
    assert payload["frame_space"] == "CUSTOM"
    assert len(payload["hits"]) == 1

    # Empty query validation
    status, payload = api.qwen_bge_search({})
    assert status == HTTPStatus.BAD_REQUEST
