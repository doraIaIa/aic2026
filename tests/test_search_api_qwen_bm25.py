"""Unit tests for Qwen BM25 HTTP Search API Endpoints (M5B1)."""
import json
import sqlite3
import tempfile
from http import HTTPStatus
from pathlib import Path

import pytest
from aic2026.search.api import AsrSearchApi


@pytest.fixture
def mock_api_qwen_bm25():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "mapping.sqlite"

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

        # Canonical count 116767
        for i in range(116767):
            conn.execute(
                "INSERT INTO qwen_frames (keyframe_uid, video_id, frame_idx, timestamp_ms, raw_pts_time, caption) VALUES (?, ?, ?, ?, ?, ?)",
                (f"CUSTOM:L21_V001:F{i}", "L21_V001", i, i * 100, i * 0.1, "người đi xe máy" if i == 0 else "phong cảnh"),
            )
            conn.execute(
                "INSERT INTO qwen_caption_fts (keyframe_uid, video_id, caption_raw, caption_norm, caption_accentless) VALUES (?, ?, ?, ?, ?)",
                (f"CUSTOM:L21_V001:F{i}", "L21_V001", "người đi xe máy" if i == 0 else "phong cảnh", "nguoi di xe may" if i == 0 else "phong canh", "nguoi di xe may" if i == 0 else "phong canh"),
            )
        conn.commit()
        conn.close()

        api = AsrSearchApi(db_path)
        try:
            yield api
        finally:
            api.close()



def test_qwen_bm25_api_health(mock_api_qwen_bm25):
    api = mock_api_qwen_bm25
    code, payload = api.qwen_bm25_health()
    assert code == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["qwen_fts_rows"] == 116767
    assert payload["canonical_qwen_rows"] == 116767


def test_qwen_bm25_api_search(mock_api_qwen_bm25):
    api = mock_api_qwen_bm25
    code, payload = api.qwen_bm25_search({"query": "xe máy", "top_k": 5})
    assert code == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["lane"] == "qwen_bm25"
    assert payload["count"] > 0
    assert payload["hits"][0]["video_id"] == "L21_V001"


def test_qwen_bm25_api_validation(mock_api_qwen_bm25):
    api = mock_api_qwen_bm25
    code, payload = api.qwen_bm25_search({"query": ""})
    assert code == HTTPStatus.BAD_REQUEST
    assert payload["status"] == "ERROR"

    code, payload = api.qwen_bm25_search({"query": "   "})
    assert code == HTTPStatus.BAD_REQUEST
    assert payload["status"] == "ERROR"
