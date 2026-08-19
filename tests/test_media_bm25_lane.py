import sqlite3
import pytest
from pathlib import Path

from aic2026.retrieval.providers.media_bm25 import (
    MediaBm25Provider,
    _build_safe_fts5_query,
    _parse_ddmmyyyy,
    CANONICAL_MEDIA_INFO_COUNT,
    CANONICAL_VIDEO_COUNT,
    CANONICAL_MEDIA_FTS_COUNT,
)
from aic2026.retrieval.providers.base import ProviderQuery, ProviderUnavailableError


DB_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")


@pytest.fixture
def media_provider():
    if not DB_PATH.exists():
        pytest.skip(f"Database not found at {DB_PATH}")
    provider = MediaBm25Provider(DB_PATH)
    yield provider
    provider.close()


def test_media_health_and_canonical_counts(media_provider):
    h = media_provider.health()
    assert h["status"] == "OK"
    assert h["sqlite_reachable"] is True
    assert h["fts5_available"] is True
    assert h["fts_table"] == "media_fts"
    assert h["fts_rows"] == CANONICAL_MEDIA_FTS_COUNT
    assert h["canonical_media_rows"] == CANONICAL_MEDIA_INFO_COUNT
    assert h["canonical_video_rows"] == CANONICAL_VIDEO_COUNT
    assert h["fts_orphan_rows"] == 0
    assert h["fts_missing_rows"] == 0
    assert h["author_coverage"] == 873
    assert h["publish_date_coverage"] == 873
    assert h["entity_type"] == "VIDEO"
    assert h["source_space"] == "MEDIA_INFO"
    assert h["frame_space"] == "NONE"
    assert h["tokenizer"] == "unicode61"
    assert h["normalizer_version"] == "v1_nfc_accentless"
    assert h["runtime_build_id"] == "m1e_20260819_090208_347742"


def test_media_provider_capabilities(media_provider):
    cap = media_provider.capabilities()
    assert cap.provider == "media_bm25"
    assert cap.status == "OK"
    assert cap.version == "canonical_media_info_v1"
    assert cap.counts["canonical_media_rows"] == 873
    assert cap.counts["fts_rows"] == 873


def test_safe_fts5_query_builder():
    q1 = _build_safe_fts5_query('HTV "Tin tức" 2024')
    assert '"HTV"' in q1
    assert '"Tin"' in q1
    assert '"tức"' in q1
    assert '"2024"' in q1

    # Empty query handling
    assert _build_safe_fts5_query("") == '""'
    assert _build_safe_fts5_query("   ") == '""'
    assert _build_safe_fts5_query("!@#$%^&*()") == '""'

    # Conjunction and disjunction
    q_and = _build_safe_fts5_query("Món Ngon Mỗi Ngày", mode="AND")
    assert " AND " in q_and
    q_or = _build_safe_fts5_query("Món Ngon Mỗi Ngày", mode="OR")
    assert " OR " in q_or


def test_date_parser():
    dt = _parse_ddmmyyyy("15/01/2024")
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 15

    assert _parse_ddmmyyyy("invalid") is None
    assert _parse_ddmmyyyy("") is None


def test_media_bm25_search_returns_video_evidence(media_provider):
    hits = media_provider.search(ProviderQuery(query_text="60 Giây", top_k=5))
    assert len(hits) > 0
    assert len(hits) <= 5

    hit = hits[0]
    assert hit.provider == "media_bm25"
    assert hit.evidence_id.startswith("MEDIA:")
    assert hit.video_id.startswith("L")
    assert hit.rank == 1
    assert hit.score_kind == "bm25_lower_is_better"
    assert isinstance(hit.raw_score, float)
    assert hit.raw_score < 0.0

    # Invariants: VIDEO evidence only
    payload = hit.payload
    assert payload["entity_type"] == "VIDEO"
    assert payload["source_space"] == "MEDIA_INFO"
    assert payload["frame_space"] == "NONE"
    assert "title" in payload
    assert "description" in payload
    assert "keywords" in payload
    assert "author" in payload
    assert "publish_date" in payload
    assert "keyframe_uid" not in payload
    assert "frame_idx" not in payload
    assert "timestamp_ms" not in payload
    assert payload["original_query"] == "60 Giây"


def test_score_semantics_never_labeled_confidence(media_provider):
    hits = media_provider.search(ProviderQuery(query_text="nấu ăn món ngon", top_k=10))
    for h in hits:
        assert h.score_kind == "bm25_lower_is_better"
        assert "confidence" not in h.score_kind.lower()
    scores = [h.raw_score for h in hits]
    assert scores == sorted(scores), "BM25 hits must be sorted in ascending order of raw score"


def test_vietnamese_unicode_and_accentless_fallback(media_provider):
    # Accented query
    hits_accent = media_provider.search(ProviderQuery(query_text="Bí quyết ôn thi", top_k=5))
    assert len(hits_accent) > 0

    # Accentless query
    hits_plain = media_provider.search(ProviderQuery(query_text="Bi quyet on thi", top_k=5))
    assert len(hits_plain) > 0


def test_candidate_scope_isolation(media_provider):
    scope = ("L21_V001", "L21_V002")
    hits = media_provider.search(ProviderQuery(query_text="HTV Tin tức", top_k=10, video_ids=scope))
    assert len(hits) > 0
    for h in hits:
        assert h.video_id in scope


def test_empty_or_invalid_candidate_scope(media_provider):
    hits = media_provider.search(ProviderQuery(query_text="HTV", top_k=5, video_ids=("NON_EXISTENT_VIDEO",)))
    assert len(hits) == 0


def test_author_filter(media_provider):
    hits = media_provider.search(
        ProviderQuery(query_text="Tin tức", top_k=10),
        author_filter="60 Giây Official",
    )
    assert len(hits) > 0
    for h in hits:
        assert "60 Giây" in (h.payload.get("author") or "")


def test_publish_date_range_filter(media_provider):
    hits = media_provider.search(
        ProviderQuery(query_text="60 Giây", top_k=20),
        publish_date_from="01/08/2024",
        publish_date_to="05/08/2024",
    )
    assert len(hits) > 0
    for h in hits:
        pub = h.payload.get("publish_date")
        assert pub is not None
        # Format is dd/mm/yyyy
        day, month, year = [int(x) for x in pub.split("/")]
        assert year == 2024
        assert month == 8
        assert 1 <= day <= 5


def test_distinctive_title_keyword_probe(media_provider):
    # Distinctive title query should retrieve source video at rank 1
    hits = media_provider.search(ProviderQuery(query_text="Ấn tượng với Lân lên Mai Hoa Thung tại Cúp Chợ Lớn", top_k=5))
    assert len(hits) > 0
    assert hits[0].video_id == "L24_V017"
