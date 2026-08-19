"""Unit tests for OCR Trigram typo-tolerant retrieval provider (M4C)."""
from __future__ import annotations

import json
import sqlite3
import pytest

from aic2026.retrieval.ocr_trigram_index import build_ocr_trigram_index, OcrTrigramIndex
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.ocr_trigram import OcrTrigramProvider


@pytest.fixture
def mock_canonical_db(tmp_path):
    db_path = tmp_path / "canonical.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE ocr_items (
        ocr_uid TEXT PRIMARY KEY,
        video_id TEXT NOT NULL,
        keyframe_uid TEXT NOT NULL,
        frame_idx INTEGER NOT NULL,
        timestamp_ms INTEGER NOT NULL,
        text_raw TEXT NOT NULL,
        text_norm TEXT NOT NULL,
        bbox_json TEXT,
        ocr_confidence REAL
    )
    """)

    item_data = [
        ("OCR:CUSTOM:L21_V001:F15:T0", "L21_V001", "CUSTOM:L21_V001:F15", 15, 500, "HTV9", "HTV9", json.dumps([[10, 10], [50, 10]]), 0.98),
        ("OCR:CUSTOM:L21_V001:F30:T0", "L21_V001", "CUSTOM:L21_V001:F30", 30, 1000, "Trường Đại học Cần Thơ", "Truong Dai hoc Can Tho", json.dumps([[10, 50], [50, 50]]), 0.92),
        ("OCR:CUSTOM:L24_V008:F45:T0", "L24_V008", "CUSTOM:L24_V008:F45", 45, 1500, "Bệnh viện Chợ Rẫy", "Benh vien Cho Ray", json.dumps([[10, 70], [50, 70]]), 0.88),
        ("OCR:CUSTOM:L24_V008:F60:T0", "L24_V008", "CUSTOM:L24_V008:F60", 60, 2000, "Cộng hòa Xã hội Chủ nghĩa Việt Nam", "Cong hoa Xa hoi Chu nghia Viet Nam", json.dumps([[10, 90], [50, 90]]), 0.99),
    ]
    cur.executemany("INSERT INTO ocr_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", item_data)
    conn.commit()
    conn.close()
    return db_path


def test_ocr_trigram_build_and_search(tmp_path, mock_canonical_db):
    out_dir = tmp_path / "trigram_out"
    passport = build_ocr_trigram_index(mock_canonical_db, out_dir, batch_size=2)
    assert passport["indexed_rows"] == 4
    assert passport["artifact_type"] == "SQLITE_FTS5_TRIGRAM"

    # Search via Index
    idx = OcrTrigramIndex(out_dir)
    h = idx.health()
    assert h["status"] == "OK"
    assert h["indexed_rows"] == 4

    hits = idx.search("HTV9", top_k=5)
    assert len(hits) == 1
    assert hits[0].ocr_uid == "OCR:CUSTOM:L21_V001:F15:T0"
    assert hits[0].score_kind == "bm25_lower_is_better"


def test_ocr_trigram_provider_typo_tolerance(tmp_path, mock_canonical_db):
    out_dir = tmp_path / "trigram_out"
    build_ocr_trigram_index(mock_canonical_db, out_dir, batch_size=2)

    provider = OcrTrigramProvider(out_dir, canonical_db_path=mock_canonical_db)
    
    # Substring / typo query
    hits = provider.search(ProviderQuery(query_text="Dai hoc Can Tho", top_k=5))
    assert len(hits) == 1
    assert hits[0].evidence_id == "OCR:CUSTOM:L21_V001:F30:T0"
    assert hits[0].payload["evidence_type"] == "OCR_ITEM"
    assert hits[0].payload["text_raw"] == "Trường Đại học Cần Thơ"
    assert hits[0].payload["ocr_confidence"] == 0.92

    # Scoped query
    hits_scoped = provider.search(ProviderQuery(query_text="Chợ Rẫy", top_k=5, video_ids=("L21_V001",)))
    assert len(hits_scoped) == 0

    hits_scoped_ok = provider.search(ProviderQuery(query_text="Chợ Rẫy", top_k=5, video_ids=("L24_V008",)))
    assert len(hits_scoped_ok) == 1
    assert hits_scoped_ok[0].video_id == "L24_V008"
