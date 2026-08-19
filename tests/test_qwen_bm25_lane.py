"""Unit tests for Qwen BM25 Caption / Text Retrieval Provider Lane (M5B)."""
import sqlite3
import tempfile
from pathlib import Path

import pytest
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.qwen_bm25 import (
    CANONICAL_QWEN_ROW_COUNT,
    QwenBm25Provider,
    _safe_fts5_query,
    _to_accentless,
)


def test_accentless_and_safe_fts_query():
    assert _to_accentless("xe máy") == "xe may"
    assert _to_accentless("đường phố") == "duong pho"
    assert _safe_fts5_query("motorcycle riding") == '"motorcycle" "riding"'
    assert _safe_fts5_query("xe máy, đường phố!") == '"xe" "máy" "đường" "phố"'
    assert _safe_fts5_query("") == ""


@pytest.fixture
def mock_qwen_bm25_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "mapping.sqlite"
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

        # Insert 10 sample frames across 2 videos
        rows = [
            (
                f"CUSTOM:L21_V001:F{i}",
                "L21_V001",
                i,
                i * 1000,
                float(i),
                '["motorcycle"]' if i % 2 == 0 else '["car"]',
                '["red"]' if i % 2 == 0 else '["blue"]',
                '[]',
                '[]',
                '["city street"]',
                '["riding"]' if i % 2 == 0 else '["driving"]',
                f"A person riding a motorcycle on city street frame {i}" if i % 2 == 0 else f"A blue car driving on highway frame {i}",
                "OK",
            )
            for i in range(10)
        ]
        conn.executemany("INSERT INTO qwen_frames VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", rows)

        fts_rows = [
            (
                f"CUSTOM:L21_V001:F{i}",
                "L21_V001",
                f"A person riding a motorcycle on city street frame {i}" if i % 2 == 0 else f"A blue car driving on highway frame {i}",
                f"a person riding a motorcycle on city street frame {i}" if i % 2 == 0 else f"a blue car driving on highway frame {i}",
                f"a person riding a motorcycle on city street frame {i}" if i % 2 == 0 else f"a blue car driving on highway frame {i}",
            )
            for i in range(10)
        ]
        conn.executemany("INSERT INTO qwen_caption_fts VALUES (?, ?, ?, ?, ?)", fts_rows)
        conn.commit()
        conn.close()

        provider = QwenBm25Provider(db_path)
        try:
            yield provider, db_path
        finally:
            provider.close()


def test_qwen_bm25_search_query(mock_qwen_bm25_db):
    provider, _ = mock_qwen_bm25_db

    hits = provider.search("motorcycle riding", top_k=5)
    assert len(hits) == 5
    assert hits[0].rank == 1
    assert hits[0].payload["entity_type"] == "FRAME"
    assert hits[0].payload["frame_space"] == "CUSTOM"
    assert "motorcycle" in hits[0].payload["caption"].lower()
    assert hits[0].score_kind == "lower_is_better"
    assert hits[0].raw_score is not None and hits[0].raw_score <= 0



def test_qwen_bm25_candidate_scoping(mock_qwen_bm25_db):
    provider, _ = mock_qwen_bm25_db

    # Scoped to valid video
    hits = provider.search("motorcycle", candidate_video_ids=["L21_V001"])
    assert len(hits) == 5
    assert all(h.video_id == "L21_V001" for h in hits)

    # Scoped to non-existent video
    hits_none = provider.search("motorcycle", candidate_video_ids=["NON_EXISTENT"])
    assert len(hits_none) == 0

    # Scoped to empty list
    hits_empty = provider.search("motorcycle", candidate_video_ids=[])
    assert len(hits_empty) == 0


def test_qwen_bm25_empty_query(mock_qwen_bm25_db):
    provider, _ = mock_qwen_bm25_db
    assert provider.search("") == []
    assert provider.search("   ") == []
