"""Unit tests for Qwen Structured Facet Retrieval Provider Lane (M5A)."""
import sqlite3
import tempfile
from pathlib import Path

import pytest
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.qwen_structured import (
    QwenStructuredProvider,
    QwenStructuredQuery,
)


@pytest.fixture
def mock_qwen_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "qwen_facets.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE frame_registry (
                frame_ordinal INTEGER PRIMARY KEY,
                keyframe_uid TEXT UNIQUE NOT NULL,
                video_id TEXT NOT NULL,
                frame_idx INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                caption TEXT NOT NULL,
                semantic_status TEXT NOT NULL
            );

            CREATE TABLE facet_dictionary (
                facet_ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                facet_id TEXT UNIQUE NOT NULL,
                namespace TEXT NOT NULL,
                canonical_value TEXT NOT NULL,
                df_frames INTEGER NOT NULL,
                df_videos INTEGER NOT NULL
            );

            CREATE TABLE facet_aliases (
                alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
                facet_ordinal INTEGER NOT NULL,
                alias_value TEXT NOT NULL,
                normalization_method TEXT NOT NULL
            );

            CREATE TABLE frame_facets (
                frame_ordinal INTEGER NOT NULL,
                facet_ordinal INTEGER NOT NULL,
                raw_value TEXT NOT NULL,
                source_field TEXT NOT NULL,
                PRIMARY KEY (frame_ordinal, facet_ordinal, raw_value)
            );

            CREATE VIRTUAL TABLE facet_fts USING fts5(
                facet_ordinal UNINDEXED,
                facet_id UNINDEXED,
                namespace UNINDEXED,
                term_raw,
                term_norm,
                term_accentless,
                tokenize='unicode61'
            );
        """)

        # Insert frame registry (10 frames across 2 videos)
        frames = [
            (1, "CUSTOM:L21_V001:F100", "L21_V001", 100, 4000, "Man riding a motorcycle on street", "OK"),
            (2, "CUSTOM:L21_V001:F200", "L21_V001", 200, 8000, "Red car parked near building", "OK"),
            (3, "CUSTOM:L21_V002:F150", "L21_V002", 150, 6000, "Police officer in blue uniform", "OK"),
            (4, "CUSTOM:L21_V002:F250", "L21_V002", 250, 10000, "Motorcycle and car on city street", "OK"),
            (5, "CUSTOM:L21_V002:F350", "L21_V002", 350, 14000, "Empty road at sunset", "OK"),
        ]
        conn.executemany("INSERT INTO frame_registry VALUES (?, ?, ?, ?, ?, ?, ?)", frames)

        # Insert facet dictionary
        facets = [
            (1, "object/motorcycle", "object", "motorcycle", 2, 2),
            (2, "object/car", "object", "car", 2, 2),
            (3, "action/riding", "action", "riding", 1, 1),
            (4, "attribute/red color", "attribute", "red color", 1, 1),
            (5, "scene/city street", "scene", "city street", 2, 2),
        ]
        conn.executemany("INSERT INTO facet_dictionary VALUES (?, ?, ?, ?, ?, ?)", facets)

        # Insert FTS terms
        fts_rows = [
            (1, "object/motorcycle", "object", "motorcycle", "motorcycle", "motorcycle"),
            (2, "object/car", "object", "car", "car", "car"),
            (3, "action/riding", "action", "riding", "riding", "riding"),
            (4, "attribute/red color", "attribute", "red color", "red color", "red color"),
            (5, "scene/city street", "scene", "city street", "city street", "city street"),
        ]
        conn.executemany("INSERT INTO facet_fts VALUES (?, ?, ?, ?, ?, ?)", fts_rows)

        # Insert frame_facets postings
        postings = [
            (1, 1, "motorcycle", "objects_json"),
            (1, 3, "riding", "visible_actions_json"),
            (1, 5, "city street", "scene_json"),
            (2, 2, "car", "objects_json"),
            (2, 4, "red color", "attributes_json"),
            (4, 1, "motorcycle", "objects_json"),
            (4, 2, "car", "objects_json"),
            (4, 5, "city street", "scene_json"),
        ]
        conn.executemany("INSERT INTO frame_facets VALUES (?, ?, ?, ?)", postings)
        conn.commit()
        conn.close()
        provider = QwenStructuredProvider(db_path)
        yield provider
        provider.close()



def test_qwen_provider_explicit_query(mock_qwen_db):
    provider = mock_qwen_db
    
    # Query for motorcycle AND riding
    query = QwenStructuredQuery(objects=["motorcycle"], actions=["riding"])
    hits = provider.search(query, top_k=10)
    
    assert len(hits) == 2
    # Frame 1 has both motorcycle and riding, so it should rank #1
    assert hits[0].payload["keyframe_uid"] == "CUSTOM:L21_V001:F100"
    assert hits[0].rank == 1
    assert len(hits[0].payload["matched_facets"]) == 2
    assert hits[0].payload["entity_type"] == "FRAME"
    assert hits[0].payload["frame_space"] == "CUSTOM"

    # Frame 4 has only motorcycle, so it should rank #2
    assert hits[1].payload["keyframe_uid"] == "CUSTOM:L21_V002:F250"
    assert hits[1].rank == 2
    assert len(hits[1].payload["matched_facets"]) == 1


def test_qwen_provider_plain_query_discovery(mock_qwen_db):
    provider = mock_qwen_db
    
    hits = provider.search("city street", top_k=5)
    assert len(hits) == 2
    assert all(h.payload["frame_space"] == "CUSTOM" for h in hits)
    assert any("scene/city street" in [mf["facet_id"] for mf in h.payload["matched_facets"]] for h in hits)


def test_qwen_provider_candidate_scoping(mock_qwen_db):
    provider = mock_qwen_db
    
    # Restrict to L21_V002 only
    query = QwenStructuredQuery(objects=["motorcycle"], candidate_video_ids=["L21_V002"])
    hits = provider.search(query)
    
    assert len(hits) == 1
    assert hits[0].video_id == "L21_V002"
    assert hits[0].payload["keyframe_uid"] == "CUSTOM:L21_V002:F250"

    # Empty candidate scope -> 0 hits
    query_empty_scope = QwenStructuredQuery(objects=["motorcycle"], candidate_video_ids=[])
    hits_empty = provider.search(query_empty_scope)
    assert len(hits_empty) == 0


def test_qwen_provider_no_matched_facets(mock_qwen_db):
    provider = mock_qwen_db
    
    hits = provider.search("non_existent_unmatched_term_xyz", top_k=5)
    assert len(hits) == 0

