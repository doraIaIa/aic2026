"""OCR BGE-M3 Dense Semantic Retrieval Provider.

Provides semantic vector retrieval over 612,813 canonical OCR items using BAAI/bge-m3 + FAISS IndexFlatIP.
Follows the SearchProvider protocol.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Sequence

from aic2026.retrieval.ocr_bge_index import OcrBgeIndex
from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)

CANONICAL_DENSE_ROWS = 612813
MAX_TOP_K = 300


class OcrBgeProvider:
    """BAAI/bge-m3 FAISS IndexFlatIP dense semantic provider for canonical OCR items."""

    name = "ocr_bge"

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
        self.index = OcrBgeIndex(self.artifact_dir)
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
                reason=h.get("error", "OCR BGE index unavailable"),
            )
        return ProviderCapability(
            lane_id=self.name,
            status="OK",
            reason=f"OCR BGE-M3 FAISS FlatIP ready ({h.get('index_rows', 0):,} items)",
        )

    def health(self) -> dict[str, Any]:
        return self.index.health()

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        """Execute dense semantic search over canonical OCR items."""
        query_text = (query.query_text or "").strip()
        if not query_text:
            return []

        top_k = min(query.top_k or 20, MAX_TOP_K)
        video_ids = query.video_ids if query.video_ids else ()

        bge_hits = self.index.search(query_text, top_k=top_k, video_ids=video_ids)
        if not bge_hits:
            return []

        # Batch resolve metadata from canonical ocr_items table
        uids = [h.ocr_uid for h in bge_hits]
        placeholders = ",".join("?" for _ in uids)

        conn = self._get_canonical_conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT ocr_uid, text_raw, text_norm, bbox_json, ocr_confidence FROM ocr_items WHERE ocr_uid IN ({placeholders})",
            uids,
        )
        meta_by_uid = {r["ocr_uid"]: r for r in cur.fetchall()}

        hits = []
        for rank, bh in enumerate(bge_hits, start=1):
            m = meta_by_uid.get(bh.ocr_uid)
            text_raw = m["text_raw"] if m else ""
            text_norm = m["text_norm"] if m else ""
            bbox = json.loads(m["bbox_json"]) if (m and m["bbox_json"]) else []
            ocr_conf = float(m["ocr_confidence"]) if (m and m["ocr_confidence"] is not None) else 1.0
            pts_sec = bh.timestamp_ms / 1000.0

            hit = ProviderHit(
                provider=self.name,
                evidence_id=bh.ocr_uid,
                video_id=bh.video_id,
                rank=rank,
                start_sec=pts_sec,
                end_sec=pts_sec,
                anchor_sec=pts_sec,
                raw_score=bh.raw_score,
                score_kind=bh.score_kind,
                artifact_version="ocr_bge_v1",
                source_video_relpath=None,
                payload={
                    "evidence_type": "OCR_ITEM",
                    "ocr_uid": bh.ocr_uid,
                    "keyframe_uid": bh.keyframe_uid,
                    "frame_space": "CUSTOM",
                    "frame_idx": bh.frame_idx,
                    "timestamp_ms": bh.timestamp_ms,
                    "text_raw": text_raw,
                    "text_norm": text_norm,
                    "bbox": bbox,
                    "ocr_confidence": ocr_conf,
                    "lane": self.name,
                    "faiss_row": bh.faiss_row,
                },
                provenance={
                    "index_sha256": self.index.passport.get("index_sha256", ""),
                    "model_id": "BAAI/bge-m3",
                    "artifact_dir": self.artifact_dir.as_posix(),
                },
            )
            hits.append(hit)
        return hits
