"""Qwen Field-Aware BGE-Large Dense Retrieval Provider (M5B2).

Provides text-to-keyframe dense semantic search over accepted external Qwen field-aware
BGE-Large FAISS indexes (1024D, float32, normalized, IndexFlatIP, METRIC_INNER_PRODUCT).
Model: BAAI/bge-large-en-v1.5 with CLS pooling, L2 normalization, and max_length 512.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

BGE_LARGE_MODEL_ID = "BAAI/bge-large-en-v1.5"
BGE_DENSE_DIMENSION = 1024
DEFAULT_MAX_LENGTH = 512

ACCEPTED_FIELDS = (
    "caption",
    "objects_attributes",
    "spatial_relations",
    "counts",
    "scene",
    "visible_actions",
    "full_text",
)

EXPECTED_FIELD_COUNTS = {
    "caption": 116298,
    "objects_attributes": 116577,
    "spatial_relations": 116243,
    "counts": 116231,
    "scene": 116322,
    "visible_actions": 96423,
    "full_text": 116649,
}

DEFAULT_ARTIFACT_DIR = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\qwen_field_bge_large_external_v1\source")
DEFAULT_MAPPING_DB = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")


class QwenBgeProvider:
    """Cached field-aware BGE-Large / FAISS provider for Qwen dense semantic retrieval."""

    name = "qwen_bge"

    def __init__(
        self,
        artifact_dir: str | Path | None = None,
        *,
        model_id: str = BGE_LARGE_MODEL_ID,
        device: str = "auto",
        canonical_db_path: str | Path | None = None,
        model_loader: Callable[[], tuple[Any, Any]] | None = None,
    ) -> None:
        raw_dir = Path(artifact_dir) if artifact_dir else DEFAULT_ARTIFACT_DIR
        # Support root dir or source sub-dir
        if (raw_dir / "source").is_dir():
            self.artifact_dir = raw_dir / "source"
        else:
            self.artifact_dir = raw_dir

        self.model_id = model_id
        self.device = device
        self.canonical_db_path = Path(canonical_db_path) if canonical_db_path else DEFAULT_MAPPING_DB
        self._model_loader = model_loader or self._default_model_loader
        self._init_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self._model_loaded = False
        self._model: Any = None
        self._tokenizer: Any = None

        configured_dev = os.environ.get("AIC_QWEN_BGE_DEVICE", self.device).lower()
        if configured_dev == "cuda":
            resolved_dev = "cuda"
        elif configured_dev == "cpu":
            resolved_dev = "cpu"
        elif configured_dev == "auto":
            try:
                import torch
                resolved_dev = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                resolved_dev = "cpu"
        else:
            resolved_dev = configured_dev
        self._device_str = resolved_dev

        self._field_indexes: dict[str, tuple[Any, pd.DataFrame]] = {}
        self._local = threading.local()


    def _default_model_loader(self) -> tuple[Any, Any]:
        """Load BAAI/bge-large-en-v1.5 model and tokenizer via transformers."""
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise ProviderUnavailableError("TRANSFORMERS_DEPENDENCY_MISSING: transformers, torch") from exc

        # Determine configured vs resolved device
        configured_dev = os.environ.get("AIC_QWEN_BGE_DEVICE", self.device).lower()
        if configured_dev == "cuda":
            if not torch.cuda.is_available():
                raise ProviderUnavailableError("CUDA configured for Qwen BGE but torch.cuda.is_available() is False")
            resolved_dev = "cuda"
        elif configured_dev == "cpu":
            resolved_dev = "cpu"
        elif configured_dev == "auto":
            resolved_dev = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            resolved_dev = configured_dev

        self._device_str = resolved_dev

        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            model = AutoModel.from_pretrained(self.model_id, use_safetensors=True)
            model.eval()
            if resolved_dev != "cpu":
                model.to(resolved_dev)
            return model, tokenizer
        except Exception as exc:
            raise ProviderUnavailableError(f"Failed to load BGE-Large model ({self.model_id}): {exc}") from exc

    def _ensure_model_loaded(self) -> None:
        if self._model_loaded:
            return
        with self._init_lock:
            if self._model_loaded:
                return
            self._model, self._tokenizer = self._model_loader()
            self._model_loaded = True

    def _get_field_index(self, field: str) -> tuple[Any, pd.DataFrame]:
        """Lazy load FAISS index and Parquet mapping for a specific field."""
        if field not in ACCEPTED_FIELDS:
            raise ValueError(f"Invalid field '{field}'. Allowed fields: {ACCEPTED_FIELDS}")

        if field in self._field_indexes:
            return self._field_indexes[field]

        with self._init_lock:
            if field in self._field_indexes:
                return self._field_indexes[field]

            import faiss

            faiss_path = self.artifact_dir / "faiss" / f"{field}.faiss"
            mapping_path = self.artifact_dir / "mappings" / f"{field}.parquet"

            if not faiss_path.exists():
                if (self.artifact_dir / f"{field}.faiss").exists():
                    faiss_path = self.artifact_dir / f"{field}.faiss"
                elif (self.artifact_dir / "qwen_bge.faiss").exists():
                    faiss_path = self.artifact_dir / "qwen_bge.faiss"
                else:
                    raise ProviderUnavailableError(f"FAISS index for field '{field}' not found at {faiss_path}")

            if not mapping_path.exists():
                if (self.artifact_dir / f"{field}.parquet").exists():
                    mapping_path = self.artifact_dir / f"{field}.parquet"
                elif (self.artifact_dir / "rowmap.parquet").exists():
                    mapping_path = self.artifact_dir / "rowmap.parquet"
                elif (self.artifact_dir / "rowmap.json").exists():
                    mapping_path = self.artifact_dir / "rowmap.json"
                else:
                    raise ProviderUnavailableError(f"Mapping for field '{field}' not found at {mapping_path}")

            index = faiss.read_index(str(faiss_path))
            if mapping_path.suffix == ".parquet":
                df = pd.read_parquet(mapping_path)
            else:
                with open(mapping_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                df = pd.DataFrame(data)

            if index.ntotal != len(df):
                raise ProviderIntegrityError(
                    f"Row count mismatch for field '{field}': FAISS ntotal={index.ntotal} != Mapping rows={len(df)}"
                )

            self._field_indexes[field] = (index, df)
            return self._field_indexes[field]

    def _get_db_conn(self) -> sqlite3.Connection | None:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            if self.canonical_db_path.exists():
                conn = sqlite3.connect(f"file:{self.canonical_db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                self._local.conn = conn
            else:
                self._local.conn = None
        return self._local.conn

    def close(self) -> None:
        """Close SQLite and free caches."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def health(self) -> dict[str, Any]:
        """Check provider health, artifact integrity, and model configuration."""
        try:
            faiss_dir = self.artifact_dir / "faiss"
            mappings_dir = self.artifact_dir / "mappings"

            is_standard = self.artifact_dir.exists() and faiss_dir.exists() and mappings_dir.exists()
            is_legacy = self.artifact_dir.exists() and (self.artifact_dir / "qwen_bge.faiss").exists()

            if not is_standard and not is_legacy:
                return {
                    "lane_id": self.name,
                    "status": "UNAVAILABLE",
                    "error": f"Artifact root or subdirectories missing at {self.artifact_dir}",
                }

            field_status: dict[str, Any] = {}
            for fld in ACCEPTED_FIELDS:
                f_path = faiss_dir / f"{fld}.faiss"
                m_path = mappings_dir / f"{fld}.parquet"
                expected_cnt = EXPECTED_FIELD_COUNTS.get(fld, 0)
                exists = (f_path.exists() and m_path.exists()) or is_legacy
                field_status[fld] = {
                    "expected_rows": expected_cnt,
                    "faiss_file_exists": f_path.exists() or is_legacy,
                    "mapping_file_exists": m_path.exists() or is_legacy,
                    "status": "OK" if exists else "MISSING",
                }

            return {
                "lane_id": self.name,
                "status": "OK",
                "model_id": self.model_id,
                "dimension": BGE_DENSE_DIMENSION,
                "pooling": "CLS",
                "max_length": DEFAULT_MAX_LENGTH,
                "normalization": "L2",
                "faiss_class": "IndexFlatIP",
                "faiss_metric": "METRIC_INNER_PRODUCT",
                "score_type": "faiss_inner_product_l2norm",
                "score_direction": "HIGHER_IS_BETTER",
                "configured_device": self.device,
                "resolved_device": self._device_str,
                "model_loaded": self._model_loaded,
                "index_rows": 1 if is_legacy else 116649,
                "fields": field_status,
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
            score_type="faiss_inner_product_l2norm",
            score_direction="HIGHER_IS_BETTER",
            supports_candidate_filter=True,
        )

    def encode_query(self, text: str) -> np.ndarray:
        """Encode query string into 1024D L2-normalized float32 embedding."""
        self._ensure_model_loaded()
        import torch
        import torch.nn.functional as F

        inputs = self._tokenizer(
            [text],
            padding=True,
            truncation=True,
            max_length=DEFAULT_MAX_LENGTH,
            return_tensors="pt",
        )
        if self._device_str != "cpu":
            inputs = {k: v.to(self._device_str) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)
            # CLS token pooling
            cls_rep = outputs[0][:, 0]
            # L2 normalize
            normed = F.normalize(cls_rep, p=2, dim=1)
            vec = normed.cpu().to(torch.float32).numpy()

        if np.isnan(vec).any() or np.isinf(vec).any():
            raise ProviderIntegrityError("Query embedding contains NaN or Inf values")

        return vec

    def search(
        self,
        query: str | ProviderQuery,
        *,
        field: str = "full_text",
        embedding_query: str | None = None,
        top_k: int = 50,
        candidate_video_ids: Sequence[str] | None = None,
        query_id: str | None = None,
    ) -> list[ProviderHit]:
        """Execute dense FAISS search on a single explicit field."""
        if field not in ACCEPTED_FIELDS:
            raise ValueError(f"Invalid field '{field}'. Allowed fields: {ACCEPTED_FIELDS}")

        scoped_vids: set[str] | None = None
        if isinstance(query, ProviderQuery):
            original_q = query.query_text
            top_k = query.top_k or top_k
            if query.video_ids and len(query.video_ids) > 0:
                scoped_vids = {v.strip() for v in query.video_ids if v and v.strip()}
                if not scoped_vids:
                    return []
            query_id = getattr(query, "query_id", query_id)
        else:
            original_q = str(query)
            if candidate_video_ids is not None:
                scoped_vids = {v.strip() for v in candidate_video_ids if v and v.strip()}
                if not scoped_vids:
                    return []

        original_q = (original_q or "").strip()
        if not original_q:
            return []

        # Determine embedded query
        embed_q = (embedding_query or "").strip() if embedding_query else original_q

        index, df_mapping = self._get_field_index(field)
        ntotal = index.ntotal
        if ntotal == 0:
            return []

        # Encode query
        q_vec = self.encode_query(embed_q)

        # Scoped vs Unscoped search with adaptive over-fetch
        t0 = time.perf_counter()
        hits_indices: list[int] = []
        hits_scores: list[float] = []

        with self._search_lock:
            if scoped_vids is None:
                k = min(top_k, ntotal)
                scores, indices = index.search(q_vec, k)
                for score, idx in zip(scores[0], indices[0]):
                    if idx >= 0:
                        hits_indices.append(int(idx))
                        hits_scores.append(float(score))
            else:
                # Adaptive over-fetch
                search_k = min(max(top_k * 4, 64), ntotal)
                matched_pairs: list[tuple[float, int]] = []
                already_seen: set[int] = set()

                while search_k <= ntotal:
                    scores, indices = index.search(q_vec, search_k)
                    for score, idx in zip(scores[0], indices[0]):
                        if idx < 0 or idx in already_seen:
                            continue
                        already_seen.add(idx)
                        row = df_mapping.iloc[idx]
                        if row["video_id"] in scoped_vids:
                            matched_pairs.append((float(score), int(idx)))
                            if len(matched_pairs) >= top_k:
                                break

                    if len(matched_pairs) >= top_k or search_k == ntotal:
                        break
                    search_k = min(search_k * 4, ntotal)

                for s, idx in matched_pairs[:top_k]:
                    hits_scores.append(s)
                    hits_indices.append(idx)

        # Build ProviderHit items
        hits: list[ProviderHit] = []
        db_conn = self._get_db_conn()

        for rank, (idx, score) in enumerate(zip(hits_indices, hits_scores), 1):
            row = df_mapping.iloc[idx]
            vid = str(row["video_id"])
            frame_idx = int(row["frame_idx"])
            if "pts_time" in row:
                pts_time = float(row["pts_time"])
            elif "raw_pts_time" in row:
                pts_time = float(row["raw_pts_time"])
            elif "timestamp_ms" in row:
                pts_time = float(row["timestamp_ms"]) / 1000.0
            else:
                pts_time = 0.0
            keyframe_uid = f"CUSTOM:{vid}:F{frame_idx}"
            ts_ms = int(round(pts_time * 1000.0))


            # Optional read-only enrichment from qwen_frames
            caption_text = ""
            if db_conn is not None:
                try:
                    c = db_conn.cursor()
                    qf_row = c.execute(
                        "SELECT caption FROM qwen_frames WHERE keyframe_uid = ?", (keyframe_uid,)
                    ).fetchone()
                    if qf_row:
                        caption_text = qf_row["caption"] or ""
                except Exception:
                    pass

            payload = {
                "lane": self.name,
                "lane_id": self.name,
                "field": field,
                "entity_type": "FRAME",
                "frame_space": "CUSTOM",
                "keyframe_uid": keyframe_uid,
                "video_id": vid,
                "frame_idx": frame_idx,
                "timestamp_ms": ts_ms,
                "pts_time": pts_time,
                "caption": caption_text,
                "score_type": "faiss_inner_product_l2norm",
                "score_direction": "HIGHER_IS_BETTER",
            }

            ev_id = f"QWEN:{keyframe_uid}"
            hit = ProviderHit(
                provider=self.name,
                evidence_id=ev_id,
                video_id=vid,
                rank=rank,
                start_sec=round(pts_time, 3),
                end_sec=round(pts_time, 3),
                anchor_sec=round(pts_time, 3),
                raw_score=round(score, 4),
                score_kind="higher_is_better",
                artifact_version="qwen_field_bge_large_external_v1",
                payload=payload,
                provenance={
                    "lane": self.name,
                    "field": field,
                    "model_id": self.model_id,
                    "pooling": "CLS",
                    "normalization": "L2",
                    "max_length": DEFAULT_MAX_LENGTH,
                    "index_type": "IndexFlatIP",
                    "metric": "METRIC_INNER_PRODUCT",
                    "score_type": "faiss_inner_product_l2norm",
                    "score_direction": "HIGHER_IS_BETTER",
                    "original_query": original_q,
                    "embedding_query": embed_q,
                    "query_id": query_id,
                    "device": self._device_str,
                },
            )
            hits.append(hit)

        return hits
