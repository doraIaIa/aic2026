"""Qwen BM25 / Lexical Caption Retrieval Provider (M5B).

Reuses the existing canonical SQLite FTS5 index `qwen_caption_fts` in mapping.sqlite.
Returns FRAME evidence in CUSTOM frame space.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Sequence

from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

CANONICAL_QWEN_ROW_COUNT = 116767
DEFAULT_MAPPING_DB = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")


def _to_accentless(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).replace("đ", "d").replace("Đ", "D")


def _safe_fts5_query(query_text: str) -> str:
    """Build a safe FTS5 query string supporting unicode, punctuation, and accentless terms."""
    clean = re.sub(r'[^\w\s\d]', ' ', query_text, flags=re.UNICODE)
    tokens = [t.strip() for t in clean.split() if t.strip()]
    if not tokens:
        return ""
    # Safe quoted terms
    return " ".join(f'"{t}"' for t in tokens)


class QwenBm25Provider:
    """Provider for Qwen caption lexical retrieval using existing SQLite FTS5 table."""

    name = "qwen_bm25"

    def __init__(
        self,
        db_path: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_MAPPING_DB
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            if not self.db_path.exists():
                raise ProviderUnavailableError(f"Database not found at {self.db_path}")
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def close(self) -> None:
        """Close thread-local SQLite connection if open."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
            import gc
            gc.collect()

    def health(self) -> dict[str, Any]:
        """Check provider health and verify qwen_caption_fts integrity."""
        try:
            conn = self._get_conn()
            c = conn.cursor()

            # Verify qwen_caption_fts exists and count matches
            fts_count = c.execute("SELECT COUNT(*) FROM qwen_caption_fts").fetchone()[0]
            qwen_count = c.execute("SELECT COUNT(*) FROM qwen_frames").fetchone()[0]

            if fts_count != CANONICAL_QWEN_ROW_COUNT:
                return {
                    "lane_id": self.name,
                    "status": "UNHEALTHY",
                    "error": f"FTS count {fts_count} != expected {CANONICAL_QWEN_ROW_COUNT}",
                }

            if qwen_count != CANONICAL_QWEN_ROW_COUNT:
                return {
                    "lane_id": self.name,
                    "status": "UNHEALTHY",
                    "error": f"Qwen frames count {qwen_count} != expected {CANONICAL_QWEN_ROW_COUNT}",
                }

            # Check orphan count
            orphan_count = c.execute("""
                SELECT COUNT(*) FROM qwen_caption_fts fts
                LEFT JOIN qwen_frames qf ON fts.keyframe_uid = qf.keyframe_uid
                WHERE qf.keyframe_uid IS NULL
            """).fetchone()[0]

            if orphan_count > 0:
                return {
                    "lane_id": self.name,
                    "status": "UNHEALTHY",
                    "error": f"Found {orphan_count} orphan FTS rows",
                }

            return {
                "lane_id": self.name,
                "status": "OK",
                "entity_type": "FRAME",
                "frame_space": "CUSTOM",
                "score_type": "sqlite_fts5_bm25",
                "score_direction": "LOWER_IS_BETTER",
                "qwen_fts_rows": fts_count,
                "canonical_qwen_rows": qwen_count,
                "orphan_rows": 0,
                "indexed_fields": ["caption_raw", "caption_norm", "caption_accentless"],
                "tokenizer": "unicode61",
                "normalizer": "v1_nfc_accentless",
            }
        except Exception as exc:
            return {
                "lane_id": self.name,
                "status": "UNHEALTHY",
                "error": str(exc),
            }

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            lane_id=self.name,
            entity_type="FRAME",
            frame_space="CUSTOM",
            score_type="sqlite_fts5_bm25",
            score_direction="LOWER_IS_BETTER",
            supports_candidate_filter=True,
        )

    def search(
        self,
        query: str | ProviderQuery,
        *,
        top_k: int = 50,
        candidate_video_ids: Sequence[str] | None = None,
        query_id: str | None = None,
    ) -> list[ProviderHit]:
        """Search Qwen captions using SQLite FTS5 BM25 ranking."""
        scoped_vids: list[str] | None = None
        if isinstance(query, ProviderQuery):
            q_text = query.query_text
            top_k = query.top_k or top_k
            if query.video_ids and len(query.video_ids) > 0:
                scoped_vids = [v.strip() for v in query.video_ids if v and v.strip()]
                if not scoped_vids:
                    return []
            query_id = getattr(query, "query_id", query_id)
        else:
            q_text = str(query)
            if candidate_video_ids is not None:
                scoped_vids = [v.strip() for v in candidate_video_ids if v and v.strip()]
                if not scoped_vids:
                    return []

        q_text = (q_text or "").strip()
        if not q_text:
            return []

        safe_q = _safe_fts5_query(q_text)
        accentless_q = _safe_fts5_query(_to_accentless(q_text))


        if not safe_q and not accentless_q:
            return []

        conn = self._get_conn()
        c = conn.cursor()

        # Build FTS match expression: search across raw, norm, and accentless columns
        # If accentless differs, include OR for accentless
        if accentless_q and accentless_q != safe_q:
            match_clause = f"({safe_q}) OR (caption_accentless: {accentless_q})"
        else:
            match_clause = safe_q

        params: list[Any] = [match_clause]
        where_extra = ""
        if scoped_vids is not None:
            placeholders = ",".join("?" for _ in scoped_vids)
            where_extra = f"AND fts.video_id IN ({placeholders})"
            params.extend(scoped_vids)

        params.append(top_k)

        sql = f"""
            SELECT 
                fts.keyframe_uid,
                fts.video_id,
                fts.caption_raw,
                bm25(qwen_caption_fts, 0.0, 0.0, 10.0, 10.0, 8.0) AS bm25_score,
                qf.frame_idx,
                qf.timestamp_ms,
                qf.raw_pts_time,
                qf.objects_json,
                qf.attributes_json,
                qf.scene_json,
                qf.visible_actions_json,
                qf.semantic_status
            FROM qwen_caption_fts fts
            JOIN qwen_frames qf ON fts.keyframe_uid = qf.keyframe_uid
            WHERE qwen_caption_fts MATCH ?
            {where_extra}
            ORDER BY bm25_score ASC, fts.keyframe_uid ASC
            LIMIT ?
        """

        try:
            rows = c.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("FTS query failed (%s) for query '%s'", exc, match_clause)
            return []

        hits: list[ProviderHit] = []
        for rank, r in enumerate(rows, 1):
            ts_ms = r["timestamp_ms"]
            start_sec = ts_ms / 1000.0
            end_sec = start_sec

            # Parse JSON fields safely
            def _load_json(val: Any) -> list[str]:
                if not val:
                    return []
                try:
                    res = json.loads(val)
                    return res if isinstance(res, list) else [str(res)]
                except Exception:
                    return []

            payload = {
                "lane": self.name,
                "lane_id": self.name,
                "entity_type": "FRAME",
                "frame_space": "CUSTOM",
                "keyframe_uid": r["keyframe_uid"],
                "video_id": r["video_id"],
                "frame_idx": r["frame_idx"],
                "timestamp_ms": ts_ms,
                "caption": r["caption_raw"],
                "objects": _load_json(r["objects_json"]),
                "attributes": _load_json(r["attributes_json"]),
                "scene": _load_json(r["scene_json"]),
                "visible_actions": _load_json(r["visible_actions_json"]),
                "semantic_status": r["semantic_status"],
                "score_type": "sqlite_fts5_bm25",
                "score_direction": "LOWER_IS_BETTER",
            }

            raw_score = float(r["bm25_score"])
            uid = r["keyframe_uid"]
            ev_id = f"QWEN:{uid}" if uid.startswith("CUSTOM:") else f"QWEN:CUSTOM:{uid}"
            hit = ProviderHit(
                provider=self.name,
                evidence_id=ev_id,
                video_id=r["video_id"],
                rank=rank,

                start_sec=round(start_sec, 3),
                end_sec=round(end_sec, 3),
                anchor_sec=round(start_sec, 3),
                raw_score=round(raw_score, 4),
                score_kind="lower_is_better",
                artifact_version="qwen_caption_fts_v1",
                payload=payload,
                provenance={
                    "lane": self.name,
                    "score_type": "sqlite_fts5_bm25",
                    "score_direction": "LOWER_IS_BETTER",
                    "query_id": query_id,
                },
            )
            hits.append(hit)

        return hits

