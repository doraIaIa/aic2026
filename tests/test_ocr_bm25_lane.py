"""Unit tests for OCR BM25 lexical retrieval provider (M4C)."""
from __future__ import annotations

import json
import sqlite3
import pytest

from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.ocr_bm25 import OcrBm25Provider


@pytest.fixture
def mock_ocr_sqlite_db(tmp_path):
    db_path = tmp_path / "mock_mapping.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE ocr_keyframes (
        keyframe_uid TEXT PRIMARY KEY,
        video_id TEXT NOT NULL,
        frame_idx INTEGER NOT NULL,
        timestamp_ms INTEGER NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE ocr_items (
        ocr_uid TEXT PRIMARY KEY,
        keyframe_uid TEXT NOT NULL,
        video_id TEXT NOT NULL,
        frame_idx INTEGER NOT NULL,
        timestamp_ms INTEGER NOT NULL,
        text_raw TEXT NOT NULL,
        text_norm TEXT NOT NULL,
        bbox_json TEXT,
        ocr_confidence REAL
    )
    """)

    cur.execute("""
    CREATE VIRTUAL TABLE ocr_fts USING fts5(
        ocr_uid UNINDEXED,
        keyframe_uid UNINDEXED,
        video_id UNINDEXED,
        text_raw,
        text_norm,
        text_accentless,
        tokenize = 'unicode61'
    )
    """)

    # Populate mock rows
    kf_data = [
        ("CUSTOM:L21_V001:F15", "L21_V001", 15, 500),
        ("CUSTOM:L21_V001:F30", "L21_V001", 30, 1000),
        ("CUSTOM:L24_V008:F45", "L24_V008", 45, 1500),
    ]
    cur.executemany("INSERT INTO ocr_keyframes VALUES (?, ?, ?, ?)", kf_data)

    item_data = [
        ("OCR:CUSTOM:L21_V001:F15:T0", "CUSTOM:L21_V001:F15", "L21_V001", 15, 500, "HTV9", "HTV9", json.dumps([[10, 10], [50, 10], [50, 20], [10, 20]]), 0.98),
        ("OCR:CUSTOM:L21_V001:F15:T1", "CUSTOM:L21_V001:F15", "L21_V001", 15, 500, "Thời sự 19h", "Thoi su 19h", json.dumps([[10, 30], [50, 30], [50, 40], [10, 40]]), 0.95),
        ("OCR:CUSTOM:L21_V001:F30:T0", "CUSTOM:L21_V001:F30", "L21_V001", 30, 1000, "Trường Đại học Cần Thơ", "Truong Dai hoc Can Tho", json.dumps([[10, 50], [50, 50], [50, 60], [10, 60]]), 0.92),
        ("OCR:CUSTOM:L24_V008:F45:T0", "CUSTOM:L24_V008:F45", "L24_V008", 45, 1500, "Bệnh viện Chợ Rẫy", "Benh vien Cho Ray", json.dumps([[10, 70], [50, 70], [50, 80], [10, 80]]), 0.88),
    ]
    cur.executemany("INSERT INTO ocr_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", item_data)

    fts_data = [
        ("OCR:CUSTOM:L21_V001:F15:T0", "CUSTOM:L21_V001:F15", "L21_V001", "HTV9", "HTV9", "HTV9"),
        ("OCR:CUSTOM:L21_V001:F15:T1", "CUSTOM:L21_V001:F15", "L21_V001", "Thời sự 19h", "Thoi su 19h", "Thoi su 19h"),
        ("OCR:CUSTOM:L21_V001:F30:T0", "CUSTOM:L21_V001:F30", "L21_V001", "Trường Đại học Cần Thơ", "Truong Dai hoc Can Tho", "Truong Dai hoc Can Tho"),
        ("OCR:CUSTOM:L24_V008:F45:T0", "CUSTOM:L24_V008:F45", "L24_V008", "Bệnh viện Chợ Rẫy", "Benh vien Cho Ray", "Benh vien Cho Ray"),
    ]
    cur.executemany("INSERT INTO ocr_fts VALUES (?, ?, ?, ?, ?, ?)", fts_data)
    conn.commit()
    conn.close()

    return db_path


def test_ocr_bm25_search_exact_and_accentless(mock_ocr_sqlite_db):
    provider = OcrBm25Provider(mock_ocr_sqlite_db)
    
    # 1. Exact query
    res = provider.search(ProviderQuery(query_text="HTV9", top_k=10))
    assert len(res) == 1
    assert res[0].evidence_id == "OCR:CUSTOM:L21_V001:F15:T0"
    assert res[0].score_kind == "bm25_lower_is_better"
    assert res[0].payload["evidence_type"] == "OCR_ITEM"
    assert res[0].payload["frame_space"] == "CUSTOM"
    assert res[0].payload["frame_idx"] == 15
    assert res[0].payload["ocr_confidence"] == 0.98

    # 2. Accentless query matches accented item
    res_acc = provider.search(ProviderQuery(query_text="Benh vien Cho Ray", top_k=10))
    assert len(res_acc) == 1
    assert res_acc[0].evidence_id == "OCR:CUSTOM:L24_V008:F45:T0"
    assert res_acc[0].payload["text_raw"] == "Bệnh viện Chợ Rẫy"


def test_ocr_bm25_video_scoping(mock_ocr_sqlite_db):
    provider = OcrBm25Provider(mock_ocr_sqlite_db)

    # Scoped to L21_V001 -> should find Cần Thơ
    res = provider.search(ProviderQuery(query_text="Cần Thơ", top_k=10, video_ids=("L21_V001",)))
    assert len(res) == 1
    assert res[0].video_id == "L21_V001"

    # Scoped to L24_V008 -> should return 0 hits
    res_none = provider.search(ProviderQuery(query_text="Cần Thơ", top_k=10, video_ids=("L24_V008",)))
    assert len(res_none) == 0


def test_ocr_bm25_empty_query(mock_ocr_sqlite_db):
    provider = OcrBm25Provider(mock_ocr_sqlite_db)
    with pytest.raises(ValueError, match="query_text phải là chuỗi không rỗng"):
        ProviderQuery(query_text="", top_k=10)
    with pytest.raises(ValueError, match="query_text phải là chuỗi không rỗng"):
        ProviderQuery(query_text="   ", top_k=10)

