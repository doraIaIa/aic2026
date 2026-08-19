import sqlite3
import pytest
from pathlib import Path
from aic2026.retrieval.providers.asr_bm25 import (
    AsrBm25Provider,
    _build_safe_fts5_query,
    CANONICAL_ASR_COUNT,
    CANONICAL_ASR_VIDEOS_WITH_SEGMENTS,
    CANONICAL_ZERO_ASR_VIDEOS,
)
from aic2026.retrieval.providers.base import ProviderQuery, ProviderUnavailableError
from aic2026.data_hub.text_normalizer import TextNormalizer


DB_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")


@pytest.fixture
def bm25_provider():
    if not DB_PATH.exists():
        pytest.skip(f"Database not found at {DB_PATH}")
    return AsrBm25Provider(DB_PATH)


def test_fts5_table_and_canonical_count(bm25_provider):
    health = bm25_provider.health()
    assert health["status"] == "OK"
    assert health["sqlite_reachable"] is True
    assert health["fts5_available"] is True
    assert health["fts_table"] == "asr_fts"
    assert health["fts_rows"] == CANONICAL_ASR_COUNT
    assert health["canonical_asr_segments"] == CANONICAL_ASR_COUNT
    assert health["videos_with_segments"] == CANONICAL_ASR_VIDEOS_WITH_SEGMENTS
    assert health["zero_asr_videos"] == CANONICAL_ZERO_ASR_VIDEOS


def test_safe_fts5_query_builder():
    # Test escaping special FTS5 syntax
    q1 = _build_safe_fts5_query('giá "xăng" dầu')
    assert '"giá"' in q1
    assert '"xăng"' in q1
    assert '"dầu"' in q1

    # Empty query handling
    assert _build_safe_fts5_query("") == '""'
    assert _build_safe_fts5_query("   ") == '""'
    assert _build_safe_fts5_query("!@#$%^&*()") == '""'

    # Vietnamese unicode & NFC
    q2 = _build_safe_fts5_query("thành phố Hồ Chí Minh", mode="AND")
    assert " AND " in q2
    assert '"thành"' in q2

    q3 = _build_safe_fts5_query("thành phố Hồ Chí Minh", mode="OR")
    assert " OR " in q3


def test_bm25_search_returns_canonical_segment(bm25_provider):
    hits = bm25_provider.search(ProviderQuery(query_text="giá xăng", top_k=5))
    assert len(hits) > 0
    assert len(hits) <= 5

    hit = hits[0]
    assert hit.provider == "asr_bm25"
    assert hit.evidence_id.startswith("ASR:")
    assert hit.video_id.startswith("L")
    assert hit.rank == 1
    assert hit.score_kind == "bm25_lower_is_better"
    assert isinstance(hit.raw_score, float)
    assert hit.raw_score < 0.0  # SQLite BM25 returns negative values
    assert hit.start_sec >= 0
    assert hit.end_sec >= hit.start_sec
    assert hit.anchor_sec == pytest.approx((hit.start_sec + hit.end_sec) / 2.0, abs=0.01)

    payload = hit.payload
    assert payload["evidence_type"] == "SEGMENT"
    assert payload["source_space"] == "ASR_SEGMENT"
    assert payload["frame_space"] == "NONE"
    assert "text_raw" in payload
    assert len(payload["text_raw"]) > 0


def test_bm25_score_semantics_never_labeled_confidence(bm25_provider):
    hits = bm25_provider.search(ProviderQuery(query_text="bệnh viện", top_k=10))
    for h in hits:
        assert h.score_kind == "bm25_lower_is_better"
        assert "confidence" not in h.score_kind.lower()
        # Verify rank order: lower raw_bm25 is better (more negative is better)
    scores = [h.raw_score for h in hits]
    assert scores == sorted(scores), "BM25 hits must be sorted in ascending order of raw score"


def test_candidate_scope_isolation(bm25_provider):
    scope = ("L21_V001", "L21_V002")
    hits = bm25_provider.search(ProviderQuery(query_text="chương trình", top_k=10, video_ids=scope))
    assert len(hits) > 0
    for h in hits:
        assert h.video_id in scope


def test_empty_or_invalid_candidate_scope(bm25_provider):
    # Non-existent video in scope
    hits = bm25_provider.search(ProviderQuery(query_text="chương trình", top_k=5, video_ids=("NON_EXISTENT_VIDEO",)))
    assert len(hits) == 0


def test_zero_asr_videos_coverage_validity(bm25_provider):
    # The 14 zero-ASR videos must be validly tracked in coverage, but return 0 segment evidence
    zero_asr_video = "L24_V008"
    hits = bm25_provider.search(ProviderQuery(query_text="tin tức", top_k=5, video_ids=(zero_asr_video,)))
    assert len(hits) == 0


def test_accentless_fallback(bm25_provider):
    # Query without accents should still retrieve relevant segments
    hits = bm25_provider.search(ProviderQuery(query_text="thanh pho Ho Chi Minh", top_k=5))
    assert len(hits) > 0
    assert any("Hồ Chí Minh" in h.payload["text_raw"] or "Ho Chi Minh" in h.payload["text_raw"] for h in hits)
