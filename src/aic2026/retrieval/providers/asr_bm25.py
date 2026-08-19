"""ASR BM25 lexical retrieval provider.

Provides FTS5 / BM25 lexical search over 107,540 canonical Whisper-medium
Vietnamese ASR segments from mapping.sqlite. Follows the SearchProvider protocol.
"""
from __future__ import annotations

import re
import sqlite3
import threading
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

CANONICAL_ASR_COUNT = 107540
CANONICAL_ASR_VIDEOS_WITH_SEGMENTS = 859
CANONICAL_ZERO_ASR_VIDEOS = 14
MAX_TOP_K = 300


def _build_safe_fts5_query(query_text: str, mode: str = "AND") -> str:
    """Build a safe SQLite FTS5 query without syntax injection.
    
    Escapes quotes and special FTS5 operators.
    mode: "PHRASE", "AND", or "OR"
    """
    cleaned = TextNormalizer.normalize_text(query_text)
    if not cleaned:
        return '""'
    
    tokens = re.findall(r'[\w\d]+', cleaned, flags=re.UNICODE)
    if not tokens:
        return '""'
    
    if mode == "PHRASE":
        return f'"{ " ".join(tokens) }"'
    elif mode == "AND":
        return " AND ".join(f'"{t}"' for t in tokens)
    else:  # OR
        return " OR ".join(f'"{t}"' for t in tokens)


class AsrBm25Provider:
    """SQLite FTS5 / BM25 provider for canonical Vietnamese ASR segments."""

    name = "asr_bm25"

    def __init__(
        self,
        db_path: str | Path,
        *,
        normalizer: TextNormalizer | None = None,
        hub: Any | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.normalizer = normalizer or TextNormalizer()
        self.hub = hub
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self.db_path.exists():
                raise ProviderUnavailableError(f"Database not found at {self.db_path}")
            try:
                conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
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
            version="canonical_asr_v1",
            checksums={},
            provenance={"db_path": str(self.db_path), "table": "asr_fts"},
            counts={
                "canonical_asr_segments": h.get("canonical_asr_segments", 0),
                "fts_rows": h.get("fts_rows", 0),
                "videos_with_segments": h.get("videos_with_segments", 0),
                "zero_asr_videos": h.get("zero_asr_videos", 0),
            },
        )

    def health(self) -> dict[str, Any]:
        """Expose comprehensive operational health facts for ASR BM25 lane."""
        try:
            conn = self._get_connection()
            c = conn.cursor()
            
            # Check SQLite version & FTS5
            c.execute("SELECT sqlite_version()")
            sqlite_version = c.fetchone()[0]
            
            c.execute("SELECT count(*) FROM asr_fts")
            fts_rows = c.fetchone()[0]
            
            c.execute("SELECT count(*) FROM canonical_asr_segments")
            canonical_rows = c.fetchone()[0]
            
            c.execute("SELECT count(*) FROM asr_video_coverage WHERE asr_status = 'HAS_SEGMENTS'")
            videos_with_segments = c.fetchone()[0]
            
            c.execute("SELECT count(*) FROM asr_video_coverage WHERE asr_status = 'ZERO_ASR_SEGMENTS'")
            zero_asr_videos = c.fetchone()[0]
            
            is_ok = (
                fts_rows == CANONICAL_ASR_COUNT
                and canonical_rows == CANONICAL_ASR_COUNT
                and videos_with_segments == CANONICAL_ASR_VIDEOS_WITH_SEGMENTS
                and zero_asr_videos == CANONICAL_ZERO_ASR_VIDEOS
            )
            
            return {
                "lane_id": self.name,
                "status": "OK" if is_ok else "INTEGRITY_ERROR",
                "sqlite_reachable": True,
                "sqlite_version": sqlite_version,
                "fts5_available": True,
                "fts_table": "asr_fts",
                "fts_rows": fts_rows,
                "canonical_asr_segments": canonical_rows,
                "videos_with_segments": videos_with_segments,
                "zero_asr_videos": zero_asr_videos,
                "tokenizer": "unicode61",
                "normalizer_version": "v1_nfc_accentless",
                "error": None if is_ok else "Row count mismatch in ASR FTS / canonical segments",
            }
        except Exception as exc:
            return {
                "lane_id": self.name,
                "status": "UNAVAILABLE",
                "sqlite_reachable": False,
                "error": str(exc),
            }

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        """Execute BM25 lexical search over canonical ASR segments."""
        if not query.query_text.strip():
            return []
        
        top_k = min(max(1, query.top_k), MAX_TOP_K)
        candidate_video_ids = query.video_ids
        
        if candidate_video_ids is not None and len(candidate_video_ids) == 0 and isinstance(query.video_ids, tuple) and len(query.video_ids) > 0:
            return []

        conn = self._get_connection()
        with self._lock:
            c = conn.cursor()
            
            # Helper to execute FTS query
            def _query_fts(match_expr: str) -> list[Any]:
                if candidate_video_ids and len(candidate_video_ids) > 0:
                    placeholders = ",".join("?" for _ in candidate_video_ids)
                    sql = f"""
                        SELECT 
                            f.segment_uid,
                            f.video_id,
                            bm25(asr_fts) AS raw_bm25,
                            s.start_ms,
                            s.end_ms,
                            s.start_sec,
                            s.end_sec,
                            s.text_raw,
                            s.text_norm,
                            s.language,
                            s.model,
                            s.video_ordinal,
                            s.source_segment_id
                        FROM asr_fts f
                        JOIN canonical_asr_segments s ON f.segment_uid = s.segment_uid
                        WHERE asr_fts MATCH ? AND f.video_id IN ({placeholders})
                        ORDER BY raw_bm25 ASC
                        LIMIT ?
                    """
                    c.execute(sql, [match_expr, *candidate_video_ids, top_k])
                else:
                    sql = """
                        SELECT 
                            f.segment_uid,
                            f.video_id,
                            bm25(asr_fts) AS raw_bm25,
                            s.start_ms,
                            s.end_ms,
                            s.start_sec,
                            s.end_sec,
                            s.text_raw,
                            s.text_norm,
                            s.language,
                            s.model,
                            s.video_ordinal,
                            s.source_segment_id
                        FROM asr_fts f
                        JOIN canonical_asr_segments s ON f.segment_uid = s.segment_uid
                        WHERE asr_fts MATCH ?
                        ORDER BY raw_bm25 ASC
                        LIMIT ?
                    """
                    c.execute(sql, [match_expr, top_k])
                return c.fetchall()

            # 1. Try conjunctive AND search
            query_and = _build_safe_fts5_query(query.query_text, mode="AND")
            rows = _query_fts(query_and) if query_and != '""' else []

            # 2. If 0 hits, try disjunctive OR search
            if not rows:
                query_or = _build_safe_fts5_query(query.query_text, mode="OR")
                if query_or and query_or != query_and:
                    rows = _query_fts(query_or)

            # 3. If still 0 hits, try accentless OR search
            if not rows:
                accentless_text = self.normalizer.strip_accents(query.query_text)
                query_acc = _build_safe_fts5_query(accentless_text, mode="OR")
                if query_acc and query_acc != '""':
                    rows = _query_fts(f"text_accentless: {query_acc}")

        hits: list[ProviderHit] = []
        for rank_idx, r in enumerate(rows, start=1):
            start_sec = float(r["start_sec"])
            end_sec = float(r["end_sec"])
            anchor_sec = round((start_sec + end_sec) / 2.0, 3)
            raw_bm25 = float(r["raw_bm25"])
            video_id = str(r["video_id"])
            mid_ms = int((r["start_ms"] + r["end_ms"]) // 2)

            # Optional derived nearest keyframes
            nearest_btc = None
            nearest_custom = None
            if self.hub is not None:
                try:
                    nearest_btc = self.hub.nearest_keyframe(video_id, mid_ms, frame_space="BTC")
                except Exception:
                    pass
                try:
                    nearest_custom = self.hub.nearest_keyframe(video_id, mid_ms, frame_space="CUSTOM")
                except Exception:
                    pass

            payload: dict[str, Any] = {
                "segment_uid": r["segment_uid"],
                "source_segment_id": r["source_segment_id"],
                "video_ordinal": r["video_ordinal"],
                "start_ms": r["start_ms"],
                "end_ms": r["end_ms"],
                "text_raw": r["text_raw"],
                "text_norm": r["text_norm"],
                "language": r["language"],
                "model": r["model"],
                "lane": self.name,
                "evidence_type": "SEGMENT",
                "source_space": "ASR_SEGMENT",
                "frame_space": "NONE",
            }
            if nearest_btc:
                payload["nearest_btc_keyframe"] = {
                    "keyframe_uid": nearest_btc.get("keyframe_uid"),
                    "timestamp_ms": nearest_btc.get("timestamp_ms"),
                    "delta_ms": nearest_btc.get("delta_ms"),
                    "derivation": "DERIVED_NEAREST_TIMELINE",
                }
            if nearest_custom:
                payload["nearest_custom_keyframe"] = {
                    "keyframe_uid": nearest_custom.get("keyframe_uid"),
                    "timestamp_ms": nearest_custom.get("timestamp_ms"),
                    "delta_ms": nearest_custom.get("delta_ms"),
                    "derivation": "DERIVED_NEAREST_TIMELINE",
                }

            hits.append(
                ProviderHit(
                    provider=self.name,
                    evidence_id=r["segment_uid"],
                    video_id=video_id,
                    rank=rank_idx,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    anchor_sec=anchor_sec,
                    raw_score=raw_bm25,
                    score_kind="bm25_lower_is_better",
                    artifact_version="canonical_asr_v1",
                    payload=payload,
                    source_video_relpath=None,
                    provenance={
                        "db_path": str(self.db_path),
                        "table": "asr_fts",
                        "score_direction": "LOWER_IS_BETTER",
                    },
                )
            )

        return hits
