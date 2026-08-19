"""Unit tests for Qwen Structured Retrieval HTTP Endpoints (M5A)."""
import json
import sqlite3
import tempfile
from http import HTTPStatus
from pathlib import Path

import pytest
from aic2026.retrieval.providers.qwen_structured import QwenStructuredProvider
from aic2026.search.api import AsrSearchApi


@pytest.fixture
def mock_api():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "qwen_facets.sqlite"
        dummy_mapping = tmp_path / "mapping.sqlite"
        dummy_mapping.touch()

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

        # Add 116,767 dummy rows in frame_registry for health check
        dummy_frames = [(i, f"UID:{i}", "L21_V001", i, i * 1000, "sample caption", "OK") for i in range(1, 116768)]
        conn.executemany("INSERT INTO frame_registry VALUES (?, ?, ?, ?, ?, ?, ?)", dummy_frames)
        conn.execute("INSERT INTO facet_dictionary VALUES (1, 'object/motorcycle', 'object', 'motorcycle', 10, 2)")
        conn.execute("INSERT INTO facet_fts VALUES (1, 'object/motorcycle', 'object', 'motorcycle', 'motorcycle', 'motorcycle')")
        conn.execute("INSERT INTO frame_facets VALUES (1, 1, 'motorcycle', 'objects_json')")
        conn.commit()
        conn.close()

        provider = QwenStructuredProvider(db_path)
        api = AsrSearchApi(database=dummy_mapping, qwen_structured_provider=provider)
        yield api
        provider.close()



def test_api_qwen_structured_health(mock_api):
    status, payload = mock_api.qwen_structured_health()
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["lane_id"] == "qwen_structured"
    assert payload["frame_registry_rows"] == 116767


def test_api_qwen_structured_search_plain_and_explicit(mock_api):
    # Plain text search
    status, payload = mock_api.qwen_structured_search({"query": "motorcycle", "top_k": 5})
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["lane"] == "qwen_structured"
    assert payload["entity_type"] == "FRAME"
    assert payload["frame_space"] == "CUSTOM"
    assert len(payload["hits"]) == 1

    # Explicit facet search
    status2, payload2 = mock_api.qwen_structured_search({"objects": ["motorcycle"], "top_k": 5})
    assert status2 == HTTPStatus.OK
    assert len(payload2["hits"]) == 1


def test_api_qwen_structured_search_validation(mock_api):
    # Empty request (neither query nor facet)
    status, payload = mock_api.qwen_structured_search({})
    assert status == HTTPStatus.BAD_REQUEST
    assert "error" in payload
