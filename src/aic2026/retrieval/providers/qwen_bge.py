"""Qwen BGE-M3 Dense Retrieval Provider (M5B).

Provides text-to-keyframe dense semantic search over eligible Qwen semantic core documents
via FAISS IndexFlatIP (1024D, float32, normalized).
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)
from aic2026.retrieval.qwen_bge_index import (
    BGE_DENSE_DIMENSION,
    BGE_MODEL_ID,
    CANONICAL_QWEN_TOTAL,
    DOCUMENT_POLICY_ID,
    QwenBgeIndex,
)

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_DIR = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\qwen_bge_v1")
DEFAULT_MAPPING_DB = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")


class QwenBgeProvider:
    """Cached BGE-M3 / FAISS provider for Qwen semantic document dense retrieval."""

    name = "qwen_bge"

    def __init__(
        self,
        artifact_dir: str | Path | None = None,
        *,
        model_id: str = BGE_MODEL_ID,
        device: str = "auto",
        canonical_db_path: str | Path | None = None,
        model_loader: Callable[[], tuple[Any, Any]] | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir) if artifact_dir else DEFAULT_ARTIFACT_DIR
        self.model_id = model_id
        self.device = device
        self.canonical_db_path = Path(canonical_db_path) if canonical_db_path else DEFAULT_MAPPING_DB
        self._model_loader = model_loader or self._default_model_loader
        self._init_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self._loaded = False
        self._index: QwenBgeIndex | None = None
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
            model = AutoModel.from_pretrained(self.model_id, use_safetensors=True)
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
                    f"Qwen BGE artifact directory not found at {self.artifact_dir}"
                )

            faiss_path = self.artifact_dir / "qwen_bge.faiss"
            rowmap_path = self.artifact_dir / "qwen_bge_rowmap.jsonl"
            if not faiss_path.exists() or not rowmap_path.exists():
                raise ProviderUnavailableError(
                    f"Qwen BGE index files missing in {self.artifact_dir}"
                )

            try:
                self._index = QwenBgeIndex(self.artifact_dir)
            except Exception as exc:
                raise ProviderIntegrityError(f"Failed to load Qwen BGE index: {exc}") from exc

            self._model, self._tokenizer = self._model_loader()
            self._loaded = True

    def close(self) -> None:
        """Release loaded model and FAISS index resources."""
        with self._init_lock:
            self._model = None
            self._tokenizer = None
            self._index = None
            self._loaded = False
            import gc
            gc.collect()

    def health(self) -> dict[str, Any]:
        """Verify Qwen BGE index health and report metrics."""
        try:
            self._ensure_loaded()
            assert self._index is not None

            passport_path = self.artifact_dir / "qwen_bge_passport.json"
            passport_data = {}
            if passport_path.exists():
                try:
                    import json
                    passport_data = json.loads(passport_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            return {
                "lane_id": self.name,
                "status": "OK",
                "entity_type": "FRAME",
                "frame_space": "CUSTOM",
                "score_type": "bge_m3_cosine_similarity",
                "score_direction": "HIGHER_IS_BETTER",
                "model_id": self.model_id,
                "device": self._device_str,
                "document_policy_id": DOCUMENT_POLICY_ID,
                "dimension": BGE_DENSE_DIMENSION,
                "metric": "INNER_PRODUCT",
                "index_type": "IndexFlatIP",
                "index_rows": self._index.total_rows,
                "rowmap_rows": self._index.total_rows,
                "canonical_qwen_rows": CANONICAL_QWEN_TOTAL,
                "eligible_dense_rows": self._index.total_rows,
                "empty_dense_rows": CANONICAL_QWEN_TOTAL - self._index.total_rows,
                "index_sha256": passport_data.get("index_sha256"),
                "rowmap_sha256": passport_data.get("rowmap_sha256"),
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
            score_type="bge_m3_cosine_similarity",
            score_direction="HIGHER_IS_BETTER",
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
        """Encode query into 1024D vector and search FAISS IndexFlatIP."""
        if isinstance(query, ProviderQuery):
            q_text = query.query_text
            top_k = query.top_k or top_k
            candidate_video_ids = query.video_ids if query.video_ids else candidate_video_ids
            query_id = getattr(query, "query_id", query_id)
        else:
            q_text = str(query)


        q_text = (q_text or "").strip()
        if not q_text:
            return []

        # Candidate video scoping
        if candidate_video_ids is not None:
            scoped_vids = [v.strip() for v in candidate_video_ids if v and v.strip()]
            if not scoped_vids:
                return []
        else:
            scoped_vids = None

        self._ensure_loaded()
        assert self._index is not None
        assert self._model is not None
        assert self._tokenizer is not None

        # Encode query text
        import torch

        with self._search_lock:
            inputs = self._tokenizer(
                [q_text],
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            if self._device_str != "cpu":
                inputs = {k: v.to(self._device_str) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                cls_token = outputs[0][:, 0]
                normalized = torch.nn.functional.normalize(cls_token, p=2, dim=1)
                q_vec = normalized.cpu().numpy().astype(np.float32)

            raw_results = self._index.search(
                q_vec,
                top_k=top_k,
                candidate_video_ids=scoped_vids,
            )

        hits: list[ProviderHit] = []
        for rank, (meta, score) in enumerate(raw_results, 1):
            ts_ms = meta["timestamp_ms"]
            start_sec = ts_ms / 1000.0
            end_sec = start_sec

            uid = meta["keyframe_uid"]
            ev_id = f"QWEN:{uid}" if uid.startswith("CUSTOM:") else f"QWEN:CUSTOM:{uid}"

            payload = {
                "lane": self.name,
                "lane_id": self.name,
                "entity_type": "FRAME",
                "frame_space": "CUSTOM",
                "keyframe_uid": uid,
                "video_id": meta["video_id"],
                "frame_idx": meta["frame_idx"],
                "timestamp_ms": ts_ms,
                "caption": meta.get("caption", ""),
                "document_policy_id": meta.get("document_policy_id", DOCUMENT_POLICY_ID),
                "semantic_status": "OK",
                "score_type": "bge_m3_cosine_similarity",
                "score_direction": "HIGHER_IS_BETTER",
            }

            hit = ProviderHit(
                provider=self.name,
                evidence_id=ev_id,
                video_id=meta["video_id"],
                rank=rank,
                start_sec=round(start_sec, 3),
                end_sec=round(end_sec, 3),
                anchor_sec=round(start_sec, 3),
                raw_score=round(float(score), 4),
                score_kind="higher_is_better",
                artifact_version="qwen_bge_v1",
                payload=payload,
                provenance={
                    "lane": self.name,
                    "model_id": self.model_id,
                    "score_type": "bge_m3_cosine_similarity",
                    "score_direction": "HIGHER_IS_BETTER",
                    "query_id": query_id,
                },
            )
            hits.append(hit)

        return hits
