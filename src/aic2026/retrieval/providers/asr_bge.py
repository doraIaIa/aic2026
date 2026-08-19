"""ASR BGE-M3 dense semantic retrieval provider.

Provides text-to-speech segment dense semantic search over 107,540 canonical
Whisper-medium Vietnamese ASR segments via FAISS IndexFlatIP (1024D, float32, normalized).
Follows the SearchProvider protocol.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from aic2026.retrieval.asr_bge_index import (
    BGE_DENSE_DIMENSION,
    BGE_MODEL_ID,
    CANONICAL_ASR_TOTAL,
    AsrBgeIndex,
)
from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

CANONICAL_ZERO_ASR_VIDEOS = 14
MAX_TOP_K = 300


class AsrBgeProvider:
    """Cached BGE-M3 / FAISS provider for canonical Vietnamese ASR dense semantic search."""

    name = "asr_bge"

    def __init__(
        self,
        artifact_dir: str | Path,
        *,
        model_id: str = BGE_MODEL_ID,
        device: str = "auto",
        hub: Any | None = None,
        model_loader: Callable[[], tuple[Any, Any]] | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.model_id = model_id
        self.device = device
        self.hub = hub
        self._model_loader = model_loader or self._default_model_loader
        self._init_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self._loaded = False
        self._index: AsrBgeIndex | None = None
        self._model: Any = None
        self._tokenizer: Any = None
        self._device_str: str = "cpu"

    def _default_model_loader(self) -> tuple[Any, Any]:
        """Load BGE-M3 model and tokenizer via transformers."""
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise ProviderUnavailableError("TRANSFORMERS_DEPENDENCY_MISSING: transformers, torch") from exc

        device = self.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._device_str = device

        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            model = AutoModel.from_pretrained(self.model_id)
            model.eval()
            if device != "cpu":
                model.to(device)
            return model, tokenizer
        except Exception as exc:
            raise ProviderUnavailableError(f"Failed to load BGE-M3 model ({self.model_id}): {exc}") from exc

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._init_lock:
            if self._loaded:
                return

            if not self.artifact_dir.exists():
                raise ProviderUnavailableError(
                    f"ASR BGE artifact directory not found at {self.artifact_dir}"
                )

            faiss_path = self.artifact_dir / "asr_bge.faiss"
            rowmap_path = self.artifact_dir / "asr_bge_rowmap.jsonl"
            if not faiss_path.exists() or not rowmap_path.exists():
                raise ProviderUnavailableError(
                    f"ASR BGE index files missing in {self.artifact_dir}"
                )

            index = AsrBgeIndex(self.artifact_dir)
            index.load()

            if index.total_rows != CANONICAL_ASR_TOTAL:
                raise ProviderIntegrityError(
                    f"ASR BGE index row count mismatch: expected {CANONICAL_ASR_TOTAL}, got {index.total_rows}"
                )

            model, tokenizer = self._model_loader()
            self._index = index
            self._model = model
            self._tokenizer = tokenizer
            self._loaded = True

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        """Encode a batch of query texts into normalized 1024D float32 vectors."""
        self._ensure_loaded()
        if not queries:
            return np.zeros((0, BGE_DENSE_DIMENSION), dtype=np.float32)

        import torch

        encoded = self._tokenizer(
            queries,
            padding=True,
            truncation=True,
            max_length=128,
            return_tensors="pt",
        )
        if self._device_str != "cpu":
            encoded = {k: v.to(self._device_str) for k, v in encoded.items()}

        with torch.no_grad():
            output = self._model(**encoded)
            cls_token = output[0][:, 0]
            normalized = torch.nn.functional.normalize(cls_token, p=2, dim=1)
            vecs = normalized.cpu().numpy().astype(np.float32)

        return vecs

    def capabilities(self) -> ProviderCapability:
        h = self.health()
        status = "OK" if h.get("status") == "OK" else "UNAVAILABLE"
        passport = h.get("passport") or {}
        return ProviderCapability(
            provider=self.name,
            status=status,
            reason=h.get("error"),
            version="asr_bge_v1",
            checksums={
                "index_sha256": h.get("index_checksum", ""),
                "rowmap_sha256": h.get("rowmap_checksum", ""),
            },
            provenance={
                "model_id": self.model_id,
                "dimension": BGE_DENSE_DIMENSION,
                "index_type": "IndexFlatIP",
            },
            counts={
                "index_rows": h.get("index_rows", 0),
                "rowmap_rows": h.get("rowmap_rows", 0),
                "zero_asr_videos": CANONICAL_ZERO_ASR_VIDEOS,
            },
        )

    def health(self) -> dict[str, Any]:
        """Expose operational health facts for ASR BGE lane."""
        try:
            self._ensure_loaded()
            assert self._index is not None
            passport = self._index.passport
            is_ok = self._index.total_rows == CANONICAL_ASR_TOTAL

            return {
                "lane_id": self.name,
                "status": "OK" if is_ok else "INTEGRITY_ERROR",
                "model_loaded": self._model is not None,
                "tokenizer_loaded": self._tokenizer is not None,
                "index_loaded": True,
                "index_id": passport.get("index_id", "asr_bge_v1"),
                "index_rows": self._index.total_rows,
                "rowmap_rows": self._index.total_rows,
                "dimension": BGE_DENSE_DIMENSION,
                "entity_space": "ASR_SEGMENT",
                "model_id": self.model_id,
                "device": self._device_str,
                "index_checksum": passport.get("index_sha256", ""),
                "rowmap_checksum": passport.get("rowmap_sha256", ""),
                "metric": "cosine_via_normalized_inner_product",
                "zero_asr_videos": CANONICAL_ZERO_ASR_VIDEOS,
                "error": None if is_ok else f"Row count mismatch {self._index.total_rows} != {CANONICAL_ASR_TOTAL}",
            }
        except Exception as exc:
            return {
                "lane_id": self.name,
                "status": "UNAVAILABLE",
                "model_loaded": False,
                "index_loaded": False,
                "error": str(exc),
            }

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        """Execute dense semantic search over canonical ASR segments."""
        if not query.query_text.strip():
            return []

        top_k = min(max(1, query.top_k), MAX_TOP_K)
        candidate_video_ids = query.video_ids

        if candidate_video_ids is not None and len(candidate_video_ids) == 0 and isinstance(query.video_ids, tuple) and len(query.video_ids) > 0:
            return []

        self._ensure_loaded()
        assert self._index is not None

        # Encode query text
        query_vec = self.encode_queries([query.query_text])[0]

        # Search index
        raw_results = self._index.search_dense(
            query_vec,
            top_k=top_k,
            candidate_video_ids=candidate_video_ids if candidate_video_ids else None,
        )

        hits: list[ProviderHit] = []
        passport = self._index.passport

        for rank_idx, (row_idx, score, entry) in enumerate(raw_results, start=1):
            start_sec = float(entry["start_sec"])
            end_sec = float(entry["end_sec"])
            anchor_sec = round((start_sec + end_sec) / 2.0, 3)
            video_id = str(entry["video_id"])
            mid_ms = int((entry["start_ms"] + entry["end_ms"]) // 2)

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
                "segment_uid": entry["segment_uid"],
                "source_segment_id": entry["source_segment_id"],
                "video_ordinal": entry["video_ordinal"],
                "start_ms": entry["start_ms"],
                "end_ms": entry["end_ms"],
                "text_raw": entry["text"],
                "text_norm": entry["text"],
                "language": entry["language"],
                "model": entry["model"],
                "lane": self.name,
                "evidence_type": "SEGMENT",
                "source_space": "ASR_SEGMENT",
                "frame_space": "NONE",
                "faiss_row": row_idx,
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
                    evidence_id=entry["segment_uid"],
                    video_id=video_id,
                    rank=rank_idx,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    anchor_sec=anchor_sec,
                    raw_score=round(float(score), 4),
                    score_kind="cosine_ip_higher_is_better",
                    artifact_version="asr_bge_v1",
                    payload=payload,
                    source_video_relpath=None,
                    provenance={
                        "index_sha256": passport.get("index_sha256", ""),
                        "rowmap_sha256": passport.get("rowmap_sha256", ""),
                        "model_id": self.model_id,
                    },
                )
            )

        return hits
