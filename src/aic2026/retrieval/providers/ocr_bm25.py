"""OCR BM25 lexical retrieval provider.

Provides FTS5 / BM25 lexical search over 676,925 canonical raw OCR items from mapping.sqlite.
Follows the SearchProvider protocol.
"""
from __future__ import annotations

import json
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

CANONICAL_OCR_ITEMS = 676925
COVERED_CUSTOM_KEYFRAMES = 116767
COVERED_VIDEOS = 873
MAX_TOP_K = 300


def _build_safe_fts5_query(query_text: str, mode: str = "AND") -> str:
    """Build a safe SQLite FTS5 query without syntax injection."""
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


class OcrBm25Provider:
    """SQLite FTS5 / BM25 provider for canonical OCR text items."""

    name = "ocr_bm25"

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

    def capability(self) -> ProviderCapability:
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM ocr_fts")
            count = cur.fetchone()[0]
            if count != CANONICAL_OCR_ITEMS:
                return ProviderCapability(
                    lane_id="ocr_bm25",
                    status="UNAVAILABLE",
                    reason=f"ocr_fts row count mismatch: {count} != {CANONICAL_OCR_ITEMS}",
                )
            return ProviderCapability(
                lane_id="ocr_bm25",
                status="OK",
                reason=f"SQLite FTS5 BM25 ready ({count:,} canonical OCR items)",
            )
        except Exception as exc:
            return ProviderCapability(
                lane_id="ocr_bm25",
                status="UNAVAILABLE",
                reason=str(exc),
            )

    def health(self) -> dict[str, Any]:
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT sqlite_version()")
            sqlite_ver = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ocr_fts")
            fts_rows = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ocr_keyframes")
            kf_rows = cur.fetchone()[0]

            return {
                "lane_id": "ocr_bm25",
                "status": "OK",
                "sqlite_reachable": True,
                "sqlite_version": sqlite_ver,
                "fts5_available": True,
                "fts_table": "ocr_fts",
                "fts_rows": fts_rows,
                "canonical_ocr_items": CANONICAL_OCR_ITEMS,
                "covered_custom_keyframes": kf_rows,
                "covered_videos": COVERED_VIDEOS,
                "tokenizer": "unicode61",
                "normalizer_version": "v1_nfc_accentless",
                "error": None,
            }
        except Exception as exc:
            return {
                "lane_id": "ocr_bm25",
                "status": "ERROR",
                "sqlite_reachable": False,
                "error": str(exc),
            }

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        """Execute BM25 lexical search over canonical OCR items."""
        query_text = (query.query_text or "").strip()
        if not query_text:
            return []

        top_k = min(query.top_k or 20, MAX_TOP_K)
        candidate_vids = set(query.video_ids) if query.video_ids else set()

        conn = self._get_connection()
        norm_query = self.normalizer.normalize_text(query_text)
        accentless_query = self.normalizer.strip_accents(query_text)

        fts_match_and = _build_safe_fts5_query(norm_query, mode="AND")
        fts_match_accentless = _build_safe_fts5_query(accentless_query, mode="AND")

        hits = self._execute_fts(conn, fts_match_and, candidate_vids, top_k)
        
        # Fallback to accentless match if AND returned fewer than top_k
        if len(hits) < top_k and fts_match_accentless != fts_match_and:
            seen_uids = {h.evidence_id for h in hits}
            accentless_hits = self._execute_fts(conn, fts_match_accentless, candidate_vids, top_k)
            for h in accentless_hits:
                if h.evidence_id not in seen_uids:
                    hits.append(h)
                    seen_uids.add(h.evidence_id)
                if len(hits) >= top_k:
                    break

        # If still zero hits and query has multiple words, try OR search
        if len(hits) == 0:
            fts_match_or = _build_safe_fts5_query(norm_query, mode="OR")
            if fts_match_or != fts_match_and:
                hits = self._execute_fts(conn, fts_match_or, candidate_vids, top_k)
            if len(hits) < top_k:
                fts_match_or_acc = _build_safe_fts5_query(accentless_query, mode="OR")
                if fts_match_or_acc != fts_match_or:
                    seen_uids = {h.evidence_id for h in hits}
                    for h in self._execute_fts(conn, fts_match_or_acc, candidate_vids, top_k):
                        if h.evidence_id not in seen_uids:
                            hits.append(h)
                            seen_uids.add(h.evidence_id)
                        if len(hits) >= top_k:
                            break

        # Rerank to set consecutive 1-based ranks
        reranked = []
        for rank, h in enumerate(hits[:top_k], start=1):
            reranked.append(
                ProviderHit(
                    provider=self.name,
                    evidence_id=h.evidence_id,
                    video_id=h.video_id,
                    rank=rank,
                    start_sec=h.start_sec,
                    end_sec=h.end_sec,
                    anchor_sec=h.anchor_sec,
                    raw_score=h.raw_score,
                    score_kind=h.score_kind,
                    artifact_version=h.artifact_version,
                    source_video_relpath=h.source_video_relpath,
                    payload=h.payload,
                    provenance=h.provenance,
                )
            )
        return reranked

    def _execute_fts(
        self,
        conn: sqlite3.Connection,
        fts_match: str,
        candidate_vids: set[str],
        limit: int,
    ) -> list[ProviderHit]:
        if not fts_match or fts_match == '""':
            return []

        cur = conn.cursor()
        try:
            if candidate_vids:
                placeholders = ",".join("?" for _ in candidate_vids)
                sql = f"""
                SELECT
                    f.ocr_uid,
                    f.keyframe_uid,
                    f.video_id,
                    f.text_raw,
                    f.text_norm,
                    i.frame_idx,
                    i.timestamp_ms,
                    i.bbox_json,
                    i.ocr_confidence,
                    bm25(ocr_fts) as score
                FROM ocr_fts f
                JOIN ocr_items i ON f.ocr_uid = i.ocr_uid
                WHERE ocr_fts MATCH ? AND f.video_id IN ({placeholders})
                ORDER BY score ASC
                LIMIT ?
                """
                params = [fts_match, *candidate_vids, limit]
            else:
                sql = """
                SELECT
                    f.ocr_uid,
                    f.keyframe_uid,
                    f.video_id,
                    f.text_raw,
                    f.text_norm,
                    i.frame_idx,
                    i.timestamp_ms,
                    i.bbox_json,
                    i.ocr_confidence,
                    bm25(ocr_fts) as score
                FROM ocr_fts f
                JOIN ocr_items i ON f.ocr_uid = i.ocr_uid
                WHERE ocr_fts MATCH ?
                ORDER BY score ASC
                LIMIT ?
                """
                params = [fts_match, limit]

            cur.execute(sql, params)
            rows = cur.fetchall()

            hits = []
            for rank, r in enumerate(rows, start=1):
                ocr_uid = r["ocr_uid"]
                keyframe_uid = r["keyframe_uid"]
                video_id = r["video_id"]
                text_raw = r["text_raw"]
                text_norm = r["text_norm"]
                frame_idx = int(r["frame_idx"])
                timestamp_ms = int(r["timestamp_ms"])
                pts_sec = timestamp_ms / 1000.0
                bbox = json.loads(r["bbox_json"]) if r["bbox_json"] else []
                ocr_conf = float(r["ocr_confidence"]) if r["ocr_confidence"] is not None else 1.0
                raw_score = round(float(r["score"]), 4)

                hit = ProviderHit(
                    provider=self.name,
                    evidence_id=ocr_uid,
                    video_id=video_id,
                    rank=rank,
                    start_sec=pts_sec,
                    end_sec=pts_sec,
                    anchor_sec=pts_sec,
                    raw_score=raw_score,
                    score_kind="bm25_lower_is_better",
                    artifact_version="canonical_ocr_v1",
                    source_video_relpath=None,
                    payload={
                        "evidence_type": "OCR_ITEM",
                        "ocr_uid": ocr_uid,
                        "keyframe_uid": keyframe_uid,
                        "frame_space": "CUSTOM",
                        "frame_idx": frame_idx,
                        "timestamp_ms": timestamp_ms,
                        "text_raw": text_raw,
                        "text_norm": text_norm,
                        "bbox": bbox,
                        "ocr_confidence": ocr_conf,
                        "lane": self.name,
                    },
                    provenance={
                        "table": "ocr_fts",
                        "score_direction": "LOWER_IS_BETTER",
                        "db_path": self.db_path.as_posix(),
                    },
                )
                hits.append(hit)
            return hits
        except sqlite3.OperationalError as exc:
            # Handle malformed query gracefully
            return []
