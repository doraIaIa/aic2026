import json
from pathlib import Path
import pytest
from aic2026.search.api import AsrSearchApi
from aic2026.retrieval.providers.asr_bm25 import AsrBm25Provider
from aic2026.retrieval.providers.asr_bge import AsrBgeProvider

DB_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
BGE_DIR = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\asr_bge_v1")


@pytest.fixture
def search_api():
    if not DB_PATH.exists() or not BGE_DIR.exists():
        pytest.skip("Prerequisites missing for search API test")
    return AsrSearchApi(DB_PATH)


def test_asr_bm25_api_health(search_api):
    status, payload = search_api.asr_bm25_health()
    assert status == 200
    assert payload["status"] == "OK"
    assert payload["canonical_asr_segments"] == 107540


def test_asr_bm25_api_search(search_api):
    status, payload = search_api.asr_bm25_search({"query": "thành phố Hồ Chí Minh", "top_k": 3})
    assert status == 200
    assert payload["status"] == "OK"
    assert payload["lane"] == "asr_bm25"
    assert payload["count"] == 3
    assert len(payload["hits"]) == 3
    assert payload["hits"][0]["provider"] == "asr_bm25"


def test_asr_bge_api_health(search_api):
    status, payload = search_api.asr_bge_health()
    assert status == 200
    assert payload["status"] == "OK"
    assert payload["index_rows"] == 107540


def test_asr_bge_api_search(search_api):
    status, payload = search_api.asr_bge_search({"query": "sông Mê Kông", "top_k": 3})
    assert status == 200
    assert payload["status"] == "OK"
    assert payload["lane"] == "asr_bge"
    assert payload["count"] == 3
    assert len(payload["hits"]) == 3
    assert payload["hits"][0]["provider"] == "asr_bge"


def test_asr_search_api_validation(search_api):
    status, payload = search_api.asr_bm25_search({"query": ""})
    assert status == 400
    assert payload["status"] == "ERROR"

    status, payload = search_api.asr_bge_search({"query": "   "})
    assert status == 400
    assert payload["status"] == "ERROR"
