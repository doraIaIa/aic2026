"""Tests for versioned ASR search strategies (Phase 6).

Covers:
- strict_and_v1 unchanged behavior
- relaxed_v1 deterministic OR-based compilation
- stopword handling
- quoted phrase preservation
- long query token cap
- empty / boilerplate-only query safety
- SQL/FTS injection safety
- Vietnamese unicode handling
- strategy dispatch
- provider strategy integration
"""
from __future__ import annotations

import pytest

from aic2026.retrieval.contract import (
    ASR_STRATEGIES,
    DEFAULT_ASR_STRATEGY,
    EVAL_ASR_STRATEGY,
    RetrievalContractError,
    compile_fts_query,
    compile_product_fts_query,
    compile_relaxed_fts_query,
    compile_strict_and_fts_query,
    _VIETNAMESE_STOPWORDS,
)


# ─── strict_and_v1 unchanged ─────────────────────────────────────────────

class TestStrictAndV1:
    """Ensure strict_and_v1 matches the original compile_product_fts_query."""

    def test_all_tokens_and_joined(self):
        result = compile_strict_and_fts_query("bão lũ miền Trung")
        assert result == '"bão" AND "lũ" AND "miền" AND "Trung"'

    def test_preserves_quoted_phrases(self):
        result = compile_strict_and_fts_query('thành phố "hồ chí minh"')
        assert result == '"thành" AND "phố" AND "hồ chí minh"'

    def test_strips_fts_operators(self):
        result = compile_strict_and_fts_query("bão OR lũ*")
        assert result == '"bão" AND "OR" AND "lũ"'

    def test_backward_compatible_alias(self):
        """compile_product_fts_query must be identical to strict_and_v1."""
        assert compile_product_fts_query is compile_strict_and_fts_query

    def test_rejects_unmatched_quote(self):
        with pytest.raises(RetrievalContractError, match="ngoặc kép"):
            compile_strict_and_fts_query('"phrase chưa đóng')

    def test_rejects_empty(self):
        with pytest.raises(RetrievalContractError):
            compile_strict_and_fts_query("***")


# ─── relaxed_v1 ──────────────────────────────────────────────────────────

class TestRelaxedV1:
    """Relaxed OR-based strategy for product search."""

    def test_or_joined_output(self):
        result = compile_relaxed_fts_query("bão lũ miền Trung")
        assert "OR" in result
        assert "AND" not in result

    def test_stopwords_removed(self):
        result = compile_relaxed_fts_query("Đoạn video về bão lũ")
        # "Đoạn", "video", "về" are stopwords
        assert '"Đoạn"' not in result
        assert '"video"' not in result
        assert '"về"' not in result
        # "bão", "lũ" should remain
        assert '"bão"' in result
        assert '"lũ"' in result

    def test_stopword_case_insensitive(self):
        result = compile_relaxed_fts_query("VIDEO cảnh bão")
        assert '"VIDEO"' not in result
        assert '"cảnh"' not in result
        assert '"bão"' in result

    def test_preserves_quoted_phrases(self):
        result = compile_relaxed_fts_query('Đoạn video "hồ chí minh" đẹp')
        assert '"hồ chí minh"' in result
        assert '"đẹp"' in result

    def test_deterministic_output(self):
        query = "Đoạn video múa rồng mặc trang phục bóng đá"
        r1 = compile_relaxed_fts_query(query)
        r2 = compile_relaxed_fts_query(query)
        assert r1 == r2

    def test_long_query_capped_at_max_tokens(self):
        # Generate query with many tokens
        tokens = [f"word{i}" for i in range(30)]
        query = " ".join(tokens)
        result = compile_relaxed_fts_query(query, max_tokens=12)
        # Should have at most 12 OR terms
        assert result.count("OR") <= 11  # 12 terms = 11 OR separators

    def test_boilerplate_only_fails_closed(self):
        """Generic scaffolding must not fan out into an unhelpful corpus query."""
        with pytest.raises(RetrievalContractError, match="token literal"):
            compile_relaxed_fts_query("đoạn video trong cảnh")

    def test_rejects_truly_empty(self):
        with pytest.raises(RetrievalContractError):
            compile_relaxed_fts_query("***")

    def test_rejects_unmatched_quote(self):
        with pytest.raises(RetrievalContractError, match="ngoặc kép"):
            compile_relaxed_fts_query('"phrase chưa đóng')

    def test_real_query_from_dev15(self):
        """Real DEV15 query should produce meaningful relaxed FTS."""
        query = (
            "Đoạn video múa rồng, những người biểu diễn múa rồng "
            "mặc trang phục của các vận động viên bóng đá."
        )
        result = compile_relaxed_fts_query(query)
        # Key content words should survive
        assert '"múa"' in result or '"rồng"' in result
        assert "OR" in result
        # Stopwords should be gone
        assert '"Đoạn"' not in result
        assert '"của"' not in result

    def test_vietnamese_diacritics_preserved(self):
        result = compile_relaxed_fts_query("Nguyễn Phú Trọng")
        assert '"Nguyễn"' in result
        assert '"Phú"' in result
        assert '"Trọng"' in result

    def test_sql_injection_safe(self):
        """Malicious input should not break FTS syntax."""
        # All special chars get stripped by \w+ regex
        result = compile_relaxed_fts_query("test'; DROP TABLE--")
        assert "DROP" not in result or '"DROP"' in result  # quoted = safe
        assert "'" not in result.replace('"', "")


# ─── Strategy dispatch ────────────────────────────────────────────────────

class TestStrategyDispatch:
    def test_strict_dispatch(self):
        result = compile_fts_query("bão lũ", strategy="strict_and_v1")
        assert "AND" in result

    def test_relaxed_dispatch(self):
        result = compile_fts_query("bão lũ", strategy="relaxed_v1")
        assert "OR" in result

    def test_default_is_relaxed(self):
        assert DEFAULT_ASR_STRATEGY == "relaxed_v1"
        result = compile_fts_query("bão lũ")
        assert "OR" in result

    def test_eval_strategy_is_strict(self):
        assert EVAL_ASR_STRATEGY == "strict_and_v1"

    def test_invalid_strategy_rejected(self):
        with pytest.raises(RetrievalContractError, match="ASR strategy"):
            compile_fts_query("test", strategy="nonexistent_v1")

    def test_strategy_constants(self):
        assert "strict_and_v1" in ASR_STRATEGIES
        assert "relaxed_v1" in ASR_STRATEGIES


# ─── Stopword set integrity ──────────────────────────────────────────────

class TestStopwords:
    def test_stopwords_are_lowercase(self):
        for word in _VIETNAMESE_STOPWORDS:
            assert word == word.lower(), f"Stopword '{word}' should be lowercase"

    def test_stopwords_no_duplicates(self):
        assert len(_VIETNAMESE_STOPWORDS) == len(set(_VIETNAMESE_STOPWORDS))

    def test_meaningful_words_not_in_stopwords(self):
        """Key domain words must NOT be in stopwords."""
        domain_words = [
            "bão", "lũ", "cháy", "xe", "tàu", "rồng", "múa",
            "tôm", "cá", "bóng", "đá", "sầu", "riêng",
            "Trump", "vaccine", "virus",
        ]
        for word in domain_words:
            assert word.lower() not in _VIETNAMESE_STOPWORDS, f"'{word}' should not be a stopword"
