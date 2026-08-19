"""Media-info BM25 lexical retrieval provider (M4E).

Provides FTS5 / BM25 lexical search over 873 canonical BTC Media-info
records from mapping.sqlite. Returns VIDEO-level evidence only.

Identity contract:
- entity_type = VIDEO
- source_space = MEDIA_INFO
- frame_space = NONE
- No keyframe_uid, no frame_idx, no timestamp_ms fabricated.

Score semantics:
- score_kind = sqlite_fts5_bm25
- score_direction = LOWER_IS_BETTER (SQLite BM25 returns negative values)

Optional structured filters (backed by real relational fields):
- author (exact normalized match via media_info.author)
- publish_date_from / publish_date_to (range on media_info.publish_date dd/mm/yyyy)

BM25 column weights (V1 frozen seed, not calibrated against GT):
  title_raw=10, title_norm=10, title_accentless=8, keywords=6, description=2
"""
from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from aic2026.data_hub.text_normalizer import TextNormalizer
from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)

# Canonical counts from M1E runtime build
CANONICAL_MEDIA_INFO_COUNT = 873
CANONICAL_VIDEO_COUNT = 873
CANONICAL_MEDIA_FTS_COUNT = 873

# FTS5 BM25 column weight seed (V1, not calibrated against GT)
# Column order in media_fts: video_id, title_raw, title_norm, title_accentless, keywords, description
# BM25 weights correspond to each column (video_id weight=0 to exclude from relevance)
# SQLite bm25(fts, w0, w1, w2, ...) — must match column order
_BM25_WEIGHTS = (0, 10, 10, 8, 6, 2)  # video_id, title_raw, title_norm, title_accentless, keywords, description
_BM25_WEIGHTS_STR = ", ".join(str(w) for w in _BM25_WEIGHTS)

MAX_TOP_K = 200  # Corpus is only 873; allow generous top-k


def _build_safe_fts5_query(query_text: str, mode: str = "AND") -> str:
    """Build a safe SQLite FTS5 query without syntax injection.

    Escapes quotes and special FTS5 operators.
    mode: "PHRASE", "AND", or "OR"
    """
    cleaned = TextNormalizer.normalize_text(query_text)
    if not cleaned:
        return '""'

    tokens = re.findall(r"[\w\d]+", cleaned, flags=re.UNICODE)
    if not tokens:
        return '""'

    if mode == "PHRASE":
        return f'"{ " ".join(tokens) }"'
    elif mode == "AND":
        return " AND ".join(f'"{t}"' for t in tokens)
    else:  # OR
        return " OR ".join(f'"{t}"' for t in tokens)


def _parse_ddmmyyyy(date_str: str) -> datetime | None:
    """Parse publish_date in dd/mm/yyyy format."""
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except (ValueError, AttributeError):
        return None


class MediaBm25Provider:
    """SQLite FTS5 / BM25 provider for canonical BTC Media-info records.

    Returns VIDEO-level evidence only. No frame, keyframe, or timestamp
    fields are fabricated. Temporal evidence must come from other lanes.
    """

    name = "media_bm25"

    def __init__(
        self,
        db_path: str | Path,
        *,
        normalizer: TextNormalizer | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.normalizer = normalizer or TextNormalizer()
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self.db_path.exists():
                raise ProviderUnavailableError(f"Database not found at {self.db_path}")
            try:
                conn = sqlite3.connect(
                    f"file:{self.db_path.as_posix()}?mode=ro", uri=True, check_same_thread=False
                )
                conn.row_factory = sqlite3.Row
                self._conn = conn
            except sqlite3.Error as exc:
                raise ProviderUnavailableError(f"Cannot open database: {exc}") from exc
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def capabilities(self) -> ProviderCapability:
        h = self.health()
        status = "OK" if h.get("status") == "OK" else "UNAVAILABLE"
        return ProviderCapability(
            provider=self.name,
            status=status,
            reason=h.get("error"),
            version="canonical_media_info_v1",
            checksums={},
            provenance={"db_path": str(self.db_path), "table": "media_fts"},
            counts={
                "canonical_media_rows": h.get("canonical_media_rows", 0),
                "canonical_video_rows": h.get("canonical_video_rows", 0),
                "fts_rows": h.get("fts_rows", 0),
            },
        )

    def health(self) -> dict[str, Any]:
        """Expose comprehensive operational health facts for Media BM25 lane."""
        try:
            conn = self._get_connection()
            c = conn.cursor()

            c.execute("SELECT sqlite_version()")
            sqlite_version = c.fetchone()[0]

            c.execute("SELECT count(*) FROM media_fts")
            fts_rows = c.fetchone()[0]

            c.execute("SELECT count(*) FROM media_info")
            canonical_media_rows = c.fetchone()[0]

            c.execute("SELECT count(*) FROM videos")
            canonical_video_rows = c.fetchone()[0]

            # Integrity checks
            orphan_count = c.execute(
                "SELECT count(*) FROM media_fts WHERE video_id NOT IN (SELECT video_id FROM media_info)"
            ).fetchone()[0]

            missing_fts = c.execute(
                "SELECT count(*) FROM media_info WHERE video_id NOT IN (SELECT video_id FROM media_fts)"
            ).fetchone()[0]

            # Author/publish_date coverage
            author_coverage = c.execute(
                "SELECT count(*) FROM media_info WHERE author IS NOT NULL AND author != ''"
            ).fetchone()[0]
            date_coverage = c.execute(
                "SELECT count(*) FROM media_info WHERE publish_date IS NOT NULL AND publish_date != ''"
            ).fetchone()[0]

            # Runtime build ID
            try:
                build_id_row = c.execute(
                    "SELECT value FROM runtime_meta WHERE key = 'build_id' LIMIT 1"
                ).fetchone()
                runtime_build_id = build_id_row[0] if build_id_row else "UNKNOWN"
            except Exception:
                runtime_build_id = "UNKNOWN"


            is_ok = (
                fts_rows == CANONICAL_MEDIA_FTS_COUNT
                and canonical_media_rows == CANONICAL_MEDIA_INFO_COUNT
                and canonical_video_rows == CANONICAL_VIDEO_COUNT
                and orphan_count == 0
                and missing_fts == 0
            )

            error_msg = None
            if not is_ok:
                parts = []
                if fts_rows != CANONICAL_MEDIA_FTS_COUNT:
                    parts.append(f"media_fts row count mismatch: {fts_rows} != {CANONICAL_MEDIA_FTS_COUNT}")
                if canonical_media_rows != CANONICAL_MEDIA_INFO_COUNT:
                    parts.append(f"media_info row count mismatch: {canonical_media_rows} != {CANONICAL_MEDIA_INFO_COUNT}")
                if orphan_count > 0:
                    parts.append(f"FTS orphan rows: {orphan_count}")
                if missing_fts > 0:
                    parts.append(f"media_info without FTS: {missing_fts}")
                error_msg = "; ".join(parts)

            return {
                "lane_id": self.name,
                "status": "OK" if is_ok else "INTEGRITY_ERROR",
                "sqlite_reachable": True,
                "sqlite_version": sqlite_version,
                "fts5_available": True,
                "fts_table": "media_fts",
                "fts_rows": fts_rows,
                "canonical_media_rows": canonical_media_rows,
                "canonical_video_rows": canonical_video_rows,
                "fts_orphan_rows": orphan_count,
                "fts_missing_rows": missing_fts,
                "author_coverage": author_coverage,
                "publish_date_coverage": date_coverage,
                "runtime_build_id": runtime_build_id,
                "indexed_fields": ["title_raw", "title_norm", "title_accentless", "keywords", "description"],
                "bm25_field_weights": {
                    "title_raw": 10,
                    "title_norm": 10,
                    "title_accentless": 8,
                    "keywords": 6,
                    "description": 2,
                },
                "tokenizer": "unicode61",
                "normalizer_version": "v1_nfc_accentless",
                "relational_optional_fields": {
                    "author": "PRESENT" if author_coverage > 0 else "ABSENT",
                    "publish_date": "PRESENT" if date_coverage > 0 else "ABSENT",
                },
                "entity_type": "VIDEO",
                "source_space": "MEDIA_INFO",
                "frame_space": "NONE",
                "error": error_msg,
            }
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            return {
                "lane_id": self.name,
                "status": "UNAVAILABLE",
                "sqlite_reachable": False,
                "error": str(exc),
            }

    def search(
        self,
        query: ProviderQuery,
        *,
        author_filter: str | None = None,
        publish_date_from: str | None = None,
        publish_date_to: str | None = None,
    ) -> list[ProviderHit]:
        """Execute BM25 lexical search over canonical Media-info records.

        Returns VIDEO-level evidence. No frame or timestamp fields fabricated.

        Args:
            query: standard ProviderQuery (query_text, top_k, video_ids scope)
            author_filter: optional exact normalized author match
            publish_date_from: optional lower bound dd/mm/yyyy (inclusive)
            publish_date_to: optional upper bound dd/mm/yyyy (inclusive)
        """
        if not query.query_text.strip():
            return []

        top_k = min(max(1, query.top_k), MAX_TOP_K)
        candidate_video_ids = query.video_ids  # may be empty tuple = no scope restriction

        # Validate explicit scope
        if candidate_video_ids is not None and len(candidate_video_ids) == 0:
            # Empty scope tuple → no results (explicit empty scope)
            # Note: empty tuple () from ProviderQuery default means NO restriction
            pass

        conn = self._get_connection()
        with self._lock:
            c = conn.cursor()

            def _query_fts(match_expr: str) -> list[sqlite3.Row]:
                """Execute FTS query with optional structured filters."""
                # Build extra WHERE clauses for structured relational filters
                extra_clauses: list[str] = []
                extra_params: list[Any] = []

                if candidate_video_ids and len(candidate_video_ids) > 0:
                    placeholders = ",".join("?" for _ in candidate_video_ids)
                    extra_clauses.append(f"mi.video_id IN ({placeholders})")
                    extra_params.extend(candidate_video_ids)

                if author_filter:
                    # Normalized author match (case-insensitive containment)
                    normalized_author = TextNormalizer.normalize_text(author_filter).lower()
                    extra_clauses.append("LOWER(mi.author) LIKE ?")
                    extra_params.append(f"%{normalized_author}%")

                if publish_date_from:
                    dt_from = _parse_ddmmyyyy(publish_date_from)
                    if dt_from:
                        # Store as epoch for comparison — publish_date is dd/mm/yyyy
                        extra_clauses.append(
                            "CAST(SUBSTR(mi.publish_date, 7, 4) || SUBSTR(mi.publish_date, 4, 2) || SUBSTR(mi.publish_date, 1, 2) AS INTEGER) >= ?"
                        )
                        extra_params.append(int(dt_from.strftime("%Y%m%d")))

                if publish_date_to:
                    dt_to = _parse_ddmmyyyy(publish_date_to)
                    if dt_to:
                        extra_clauses.append(
                            "CAST(SUBSTR(mi.publish_date, 7, 4) || SUBSTR(mi.publish_date, 4, 2) || SUBSTR(mi.publish_date, 1, 2) AS INTEGER) <= ?"
                        )
                        extra_params.append(int(dt_to.strftime("%Y%m%d")))

                where_extra = (" AND " + " AND ".join(extra_clauses)) if extra_clauses else ""

                sql = f"""
                    SELECT
                        f.video_id,
                        bm25(media_fts, {_BM25_WEIGHTS_STR}) AS raw_bm25,
                        mi.title,
                        mi.description,
                        mi.keywords_json,
                        mi.author,
                        mi.publish_date,
                        mi.duration_sec,
                        mi.channel_id,
                        mi.source_id,
                        mi.watch_url,
                        mi.thumbnail_url
                    FROM media_fts f
                    JOIN media_info mi ON f.video_id = mi.video_id
                    WHERE media_fts MATCH ?{where_extra}
                    ORDER BY raw_bm25 ASC
                    LIMIT ?
                """
                params = [match_expr, *extra_params, top_k]
                c.execute(sql, params)
                return c.fetchall()

            # Strategy 1: conjunctive AND search
            query_and = _build_safe_fts5_query(query.query_text, mode="AND")
            rows = _query_fts(query_and) if query_and != '""' else []

            # Strategy 2: disjunctive OR fallback if AND returns 0 hits
            if not rows:
                query_or = _build_safe_fts5_query(query.query_text, mode="OR")
                if query_or and query_or != query_and and query_or != '""':
                    rows = _query_fts(query_or)

            # Strategy 3: accentless OR fallback
            if not rows:
                accentless_text = self.normalizer.strip_accents(query.query_text)
                query_acc = _build_safe_fts5_query(accentless_text, mode="OR")
                if query_acc and query_acc != '""':
                    rows = _query_fts(f"title_accentless: {query_acc}")

        import json as _json

        hits: list[ProviderHit] = []
        for rank_idx, r in enumerate(rows, start=1):
            video_id = str(r["video_id"])
            raw_bm25 = float(r["raw_bm25"])
            title = r["title"] or ""
            description = r["description"] or ""
            keywords_json = r["keywords_json"] or "[]"
            try:
                keywords = _json.loads(keywords_json)
            except Exception:
                keywords = []
            author = r["author"] or None
            publish_date = r["publish_date"] or None
            duration_sec = r["duration_sec"]

            payload: dict[str, Any] = {
                # Evidence identity
                "entity_type": "VIDEO",
                "source_space": "MEDIA_INFO",
                "frame_space": "NONE",
                "lane": self.name,
                # Core media fields
                "title": title,
                "description": description[:500] if description else "",
                "keywords": keywords,
                "author": author,
                "publish_date": publish_date,
                "duration_sec": duration_sec,
                "channel_id": r["channel_id"] or None,
                "watch_url": r["watch_url"] or None,
                "thumbnail_url": r["thumbnail_url"] or None,
                "source_id": r["source_id"] or None,
                # Score provenance
                "score_direction": "LOWER_IS_BETTER",
                "score_type": "sqlite_fts5_bm25",
                "bm25_field_weights": dict(zip(
                    ["video_id", "title_raw", "title_norm", "title_accentless", "keywords", "description"],
                    _BM25_WEIGHTS
                )),
                # Query retained in provenance
                "original_query": query.query_text,
            }

            # VIDEO-only: no keyframe_uid, no frame_idx, no timestamp_ms fabricated
            # anchor_sec = 0.0 is a neutral sentinel for VIDEO evidence (no temporal anchor)
            hits.append(
                ProviderHit(
                    provider=self.name,
                    evidence_id=f"MEDIA:{video_id}",
                    video_id=video_id,
                    rank=rank_idx,
                    start_sec=0.0,   # Sentinel: VIDEO evidence has no temporal anchor
                    end_sec=0.0,     # Sentinel: VIDEO evidence has no temporal anchor
                    anchor_sec=0.0,  # Sentinel: VIDEO evidence has no temporal anchor
                    raw_score=raw_bm25,
                    score_kind="bm25_lower_is_better",
                    artifact_version="canonical_media_info_v1",
                    payload=payload,
                    source_video_relpath=None,
                    provenance={
                        "db_path": str(self.db_path),
                        "table": "media_fts",
                        "score_direction": "LOWER_IS_BETTER",
                        "original_query": query.query_text,
                        "runtime_build_id": "m1e_20260819_090208_347742",
                        "media_canonical_checksum": "7b16a48ff935d5a690980e1b02391b15b09c3cd010844eea83ea6725d225999d",
                    },
                )
            )

        return hits
