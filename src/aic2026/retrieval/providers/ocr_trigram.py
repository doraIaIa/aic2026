"""OCR Trigram typo-tolerant retrieval provider.

Provides character 3-gram search over 676,925 canonical raw OCR items from derived ocr_trigram.sqlite.
Follows the SearchProvider protocol.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Sequence

from aic2026.retrieval.ocr_trigram_index import OcrTrigramIndex
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


class OcrTrigramProvider:
    """Character trigram / typo-tolerant provider for canonical OCR text items."""

    name = "ocr_trigram"

    def __init__(
        self,
        artifact_dir: str | Path,
        canonical_db_path: str | Path | None = None,
        *,
        hub: Any | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.canonical_db_path = Path(canonical_db_path) if canonical_db_path else Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
        self.hub = hub
        self.index = OcrTrigramIndex(self.artifact_dir)
        self._lock = threading.Lock()
        self._canonical_conn: sqlite3.Connection | None = None

    def _get_canonical_conn(self) -> sqlite3.Connection:
        if self._canonical_conn is None:
            if not self.canonical_db_path.exists():
                raise ProviderUnavailableError(f"Canonical database not found at {self.canonical_db_path}")
            try:
                conn = sqlite3.connect(f"file:{self.canonical_db_path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self._canonical_conn = conn
            except sqlite3.Error as exc:
                raise ProviderUnavailableError(f"Cannot open canonical database: {exc}") from exc
        return self._canonical_conn

    def capability(self) -> ProviderCapability:
        h = self.health()
        if h.get("status") != "OK":
            return ProviderCapability(
                lane_id=self.name,
                status="UNAVAILABLE",
                reason=h.get("error", "Trigram index unavailable"),
            )
        return ProviderCapability(
            lane_id=self.name,
            status="OK",
            reason=f"SQLite FTS5 Trigram ready ({h.get('indexed_rows', 0):,} items)",
        )

    def health(self) -> dict[str, Any]:
        return self.index.health()

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        """Execute character 3-gram typo-tolerant search over canonical OCR items."""
        query_text = (query.query_text or "").strip()
        if not query_text:
            return []

        top_k = min(query.top_k or 20, MAX_TOP_K)
        video_ids = query.video_ids if query.video_ids else ()

        trigram_hits = self.index.search(query_text, top_k=top_k, video_ids=video_ids)
        if not trigram_hits:
            return []

        # Batch resolve metadata from canonical ocr_items table
        uids = [h.ocr_uid for h in trigram_hits]
        placeholders = ",".join("?" for _ in uids)

        conn = self._get_canonical_conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT ocr_uid, text_raw, text_norm, bbox_json, ocr_confidence FROM ocr_items WHERE ocr_uid IN ({placeholders})",
            uids,
        )
        meta_by_uid = {r["ocr_uid"]: r for r in cur.fetchall()}

        hits = []
        for rank, th in enumerate(trigram_hits, start=1):
            m = meta_by_uid.get(th.ocr_uid)
            text_raw = m["text_raw"] if m else ""
            text_norm = m["text_norm"] if m else ""
            bbox = json.loads(m["bbox_json"]) if (m and m["bbox_json"]) else []
            ocr_conf = float(m["ocr_confidence"]) if (m and m["ocr_confidence"] is not None) else 1.0
            pts_sec = th.timestamp_ms / 1000.0

            hit = ProviderHit(
                provider=self.name,
                evidence_id=th.ocr_uid,
                video_id=th.video_id,
                rank=rank,
                start_sec=pts_sec,
                end_sec=pts_sec,
                anchor_sec=pts_sec,
                raw_score=th.raw_score,
                score_kind=th.score_kind,
                artifact_version="ocr_trigram_v1",
                source_video_relpath=None,
                payload={
                    "evidence_type": "OCR_ITEM",
                    "ocr_uid": th.ocr_uid,
                    "keyframe_uid": th.keyframe_uid,
                    "frame_space": "CUSTOM",
                    "frame_idx": th.frame_idx,
                    "timestamp_ms": th.timestamp_ms,
                    "text_raw": text_raw,
                    "text_norm": text_norm,
                    "bbox": bbox,
                    "ocr_confidence": ocr_conf,
                    "lane": self.name,
                },
                provenance={
                    "table": "ocr_trigram_fts",
                    "score_direction": "LOWER_IS_BETTER",
                    "artifact_dir": self.artifact_dir.as_posix(),
                },
            )
            hits.append(hit)
        return hits
