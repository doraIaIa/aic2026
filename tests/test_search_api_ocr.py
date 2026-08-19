"""Unit tests for OCR search API endpoints (M4C)."""
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

    # Mock OCR providers
    mock_bm25 = MagicMock()
    mock_bm25.health.return_value = {"lane_id": "ocr_bm25", "status": "OK", "fts_rows": 676925}
    mock_bm25.search.return_value = [
        ProviderHit(
            provider="ocr_bm25",
            evidence_id="OCR:CUSTOM:L21_V001:F15:T0",
            video_id="L21_V001",
            rank=1,
            start_sec=0.5,
            end_sec=0.5,
            anchor_sec=0.5,
            raw_score=-15.2,
            score_kind="bm25_lower_is_better",
            artifact_version="canonical_ocr_v1",
            source_video_relpath=None,
            payload={"text_raw": "HTV9", "ocr_confidence": 0.98},
            provenance={"table": "ocr_fts"},
        )
    ]

    mock_trigram = MagicMock()
    mock_trigram.health.return_value = {"lane_id": "ocr_trigram", "status": "OK", "indexed_rows": 676925}
    mock_trigram.search.return_value = [
        ProviderHit(
            provider="ocr_trigram",
            evidence_id="OCR:CUSTOM:L21_V001:F30:T0",
            video_id="L21_V001",
            rank=1,
            start_sec=1.0,
            end_sec=1.0,
            anchor_sec=1.0,
            raw_score=-18.4,
            score_kind="bm25_lower_is_better",
            artifact_version="ocr_trigram_v1",
            source_video_relpath=None,
            payload={"text_raw": "Cần Thơ", "ocr_confidence": 0.95},
            provenance={"table": "ocr_trigram_fts"},
        )
    ]

    mock_bge = MagicMock()
    mock_bge.health.return_value = {"lane_id": "ocr_bge", "status": "OK", "index_rows": 612813}
    mock_bge.search.return_value = [
        ProviderHit(
            provider="ocr_bge",
            evidence_id="OCR:CUSTOM:L24_V008:F45:T0",
            video_id="L24_V008",
            rank=1,
            start_sec=1.5,
            end_sec=1.5,
            anchor_sec=1.5,
            raw_score=0.82,
            score_kind="cosine_ip_higher_is_better",
            artifact_version="ocr_bge_v1",
            source_video_relpath=None,
            payload={"text_raw": "Bệnh viện", "ocr_confidence": 0.91},
            provenance={"model_id": "BAAI/bge-m3"},
        )
    ]

    api.ocr_bm25_provider = mock_bm25
    api.ocr_trigram_provider = mock_trigram
    api.ocr_bge_provider = mock_bge

    return api


def test_ocr_bm25_api_endpoints(mock_search_api):
    # Health
    status, payload = mock_search_api.ocr_bm25_health()
    assert status == HTTPStatus.OK
    assert payload["lane_id"] == "ocr_bm25"
    assert payload["status"] == "OK"

    # Search
    status, payload = mock_search_api.ocr_bm25_search({"query": "HTV9", "top_k": 5})
    assert status == HTTPStatus.OK
    assert payload["lane"] == "ocr_bm25"
    assert payload["count"] == 1
    assert payload["hits"][0]["evidence_id"] == "OCR:CUSTOM:L21_V001:F15:T0"


def test_ocr_trigram_api_endpoints(mock_search_api):
    # Health
    status, payload = mock_search_api.ocr_trigram_health()
    assert status == HTTPStatus.OK
    assert payload["lane_id"] == "ocr_trigram"
    assert payload["status"] == "OK"

    # Search
    status, payload = mock_search_api.ocr_trigram_search({"query": "Can Tho", "top_k": 5})
    assert status == HTTPStatus.OK
    assert payload["lane"] == "ocr_trigram"
    assert payload["count"] == 1
    assert payload["hits"][0]["evidence_id"] == "OCR:CUSTOM:L21_V001:F30:T0"


def test_ocr_bge_api_endpoints(mock_search_api):
    # Health
    status, payload = mock_search_api.ocr_bge_health()
    assert status == HTTPStatus.OK
    assert payload["lane_id"] == "ocr_bge"
    assert payload["status"] == "OK"

    # Search
    status, payload = mock_search_api.ocr_bge_search({"query": "bệnh viện", "top_k": 5})
    assert status == HTTPStatus.OK
    assert payload["lane"] == "ocr_bge"
    assert payload["count"] == 1
    assert payload["hits"][0]["evidence_id"] == "OCR:CUSTOM:L24_V008:F45:T0"
