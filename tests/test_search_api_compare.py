"""Unit tests for Search API Compare Endpoints (M6)."""

from __future__ import annotations

import tempfile
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aic2026.search.api import AsrSearchApi


@pytest.fixture
def mock_api():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dummy_db = Path(tmp_dir) / "dummy.sqlite"
        dummy_db.touch()
        api = AsrSearchApi(dummy_db)
        # Mock providers on api
        api.siglip_search = MagicMock(return_value=(200, {
            "status": "OK",
            "lane": "siglip_custom",
            "hits": [{"video_id": "L21_V001", "raw_score": 0.82}],
        }))
        api.asr_bm25_search = MagicMock(return_value=(200, {
            "status": "OK",
            "lane": "asr_bm25",
            "hits": [{"video_id": "L21_V001", "raw_score": 8.5}],
        }))
        yield api


def test_compare_health_endpoint(mock_api):
    status, payload = mock_api.compare_health()
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["mode"] == "COMPARE"
    assert "siglip_custom" in payload["lanes_supported"]
    assert "btc_objects" in payload["lanes_supported"]


def test_compare_search_validation_empty_lanes(mock_api):
    status, payload = mock_api.compare_search({"query": "test query", "lanes": []})
    assert status == HTTPStatus.BAD_REQUEST
    assert payload["status"] == "ERROR"
    assert "lanes list is required" in payload["error"]


def test_compare_search_success(mock_api):
    req = {
        "query": "người lái xe",
        "top_k": 10,
        "candidate_video_ids": ["L21_V001"],
        "lanes": [
            {"lane": "siglip_custom", "enabled": True},
            {"lane": "asr_bm25", "enabled": True},
        ],
    }
    status, payload = mock_api.compare_search(req)
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["mode"] == "COMPARE"
    assert payload["query"] == "người lái xe"
    assert len(payload["lanes"]) == 2
    assert "diagnostics" in payload
    assert payload["diagnostics"]["video_union_count"] == 1


def test_compare_search_string_lanes_format(mock_api):
    req = {
        "query": "hello world",
        "top_k": 5,
        "lanes": ["siglip_custom", "asr_bm25"],
    }
    status, payload = mock_api.compare_search(req)
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert len(payload["lanes"]) == 2
