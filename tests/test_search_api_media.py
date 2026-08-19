"""Unit tests for Media BM25 search API endpoints (M4E)."""
from __future__ import annotations

import json
from http import HTTPStatus
from unittest.mock import MagicMock
import pytest

from aic2026.retrieval.providers.base import ProviderHit
from aic2026.search.api import AsrSearchApi


@pytest.fixture
def mock_search_api(tmp_path):
    db_file = tmp_path / "mock.sqlite"
    db_file.touch()

    api = AsrSearchApi(db_file)

    mock_media = MagicMock()
    mock_media.health.return_value = {
        "lane_id": "media_bm25",
        "status": "OK",
        "fts_rows": 873,
        "canonical_media_rows": 873,
        "entity_type": "VIDEO",
    }
    mock_media.search.return_value = [
        ProviderHit(
            provider="media_bm25",
            evidence_id="MEDIA:L21_V001",
            video_id="L21_V001",
            rank=1,
            start_sec=0.0,
            end_sec=0.0,
            anchor_sec=0.0,
            raw_score=-25.4,
            score_kind="bm25_lower_is_better",
            artifact_version="canonical_media_info_v1",
            source_video_relpath=None,
            payload={
                "title": "60 Giây Sáng - Ngày 01082024",
                "author": "60 Giây Official",
                "publish_date": "01/08/2024",
                "keywords": ["HTV Tin tức"],
                "entity_type": "VIDEO",
                "source_space": "MEDIA_INFO",
                "frame_space": "NONE",
            },
            provenance={"table": "media_fts"},
        )
    ]

    api.media_bm25_provider = mock_media
    return api


def test_media_bm25_api_health(mock_search_api):
    status, payload = mock_search_api.media_bm25_health()
    assert status == HTTPStatus.OK
    assert payload["lane_id"] == "media_bm25"
    assert payload["status"] == "OK"
    assert payload["fts_rows"] == 873


def test_media_bm25_api_search(mock_search_api):
    status, payload = mock_search_api.media_bm25_search({"query": "60 Giây", "top_k": 5})
    assert status == HTTPStatus.OK
    assert payload["lane"] == "media_bm25"
    assert payload["entity_type"] == "VIDEO"
    assert payload["count"] == 1
    assert payload["hits"][0]["evidence_id"] == "MEDIA:L21_V001"
    assert payload["hits"][0]["video_id"] == "L21_V001"
    assert payload["hits"][0]["payload"]["entity_type"] == "VIDEO"


def test_media_bm25_api_search_missing_query(mock_search_api):
    status, payload = mock_search_api.media_bm25_search({})
    assert status == HTTPStatus.BAD_REQUEST
    assert payload["status"] == "ERROR"
