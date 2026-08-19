"""SigLIP2 CUSTOM visual retrieval provider.

Provides standalone SigLIP2 text-to-image search over CUSTOM keyframes via
FAISS IndexFlatIP. Follows the existing SearchProvider protocol.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from aic2026.core.hashing import sha256_file
from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)

# Frozen SigLIP2 processor contract
SIGLIP_MODEL_ID = "google/siglip2-base-patch16-224"
SIGLIP_DIMENSION = 768
SIGLIP_MAX_LENGTH = 64
SIGLIP_PADDING = "max_length"
SIGLIP_TRUNCATION = True

# Maximum sane top_k
MAX_TOP_K = 300
# Maximum over-fetch multiplier for adaptive scope search
MAX_OVERFETCH_MULTIPLIER = 64


class SigLIPProvider:
    """Cached SigLIP2/FAISS provider for CUSTOM keyframe visual search.

    Implements the SearchProvider protocol with lazy model/index loading,
    adaptive candidate-video scope filtering, and thread-safe search.
    """

    name = "siglip_custom"

    def __init__(
        self,
        index_dir: str | Path,
        *,
        device: str = "auto",
        model_loader: Callable[[], tuple[Any, Any]] | None = None,
    ) -> None:
        self.index_dir = Path(index_dir)
        self.device = device
        self._model_loader = model_loader or self._default_model_loader
        self._init_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self._loaded = False
        self._index: Any = None
        self._model: Any = None
        self._processor: Any = None
        self._rowmap: list[dict[str, Any]] = []
        self._row_to_video: dict[int, str] = {}
        self._passport: dict[str, Any] = {}
        self._done: dict[str, Any] = {}
        self._capability: ProviderCapability | None = None
        self._device_str: str = "cpu"

    def _default_model_loader(self) -> tuple[Any, Any]:
        """Load SigLIP2 model and processor from HuggingFace transformers."""
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ImportError as exc:
            raise ProviderUnavailableError("SIGLIP_DEPENDENCY_MISSING: transformers") from exc

        device = self.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._device_str = device

        try:
            processor = AutoProcessor.from_pretrained(SIGLIP_MODEL_ID)
            model = AutoModel.from_pretrained(SIGLIP_MODEL_ID)
            model = model.to(device)
            model.eval()
        except Exception as exc:
            raise ProviderUnavailableError(f"SIGLIP_MODEL_UNAVAILABLE: {exc}") from exc

        return model, processor

    def _load_index_and_rowmap(self) -> tuple[Any, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        """Load FAISS index, rowmap, and passport from index_dir."""
        try:
            import faiss
        except ImportError as exc:
            raise ProviderUnavailableError("FAISS_DEPENDENCY_MISSING") from exc

        done_path = self.index_dir / "DONE.json"
        if not done_path.is_file():
            raise ProviderUnavailableError("SIGLIP_DONE_MARKER_MISSING")

        try:
            done = json.loads(done_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderIntegrityError(f"SIGLIP_DONE_MARKER_INVALID: {exc}") from exc

        if done.get("task") != "siglip_faiss_index" or done.get("schema_version") != 1:
            raise ProviderIntegrityError("SIGLIP_DONE_MARKER_CONTRACT_MISMATCH")

        index_path = self.index_dir / str(done.get("index_file", ""))
        rowmap_path = self.index_dir / str(done.get("rowmap_file", ""))

        if not index_path.is_file():
            raise ProviderUnavailableError(f"SIGLIP_INDEX_MISSING: {index_path}")
        if not rowmap_path.is_file():
            raise ProviderUnavailableError(f"SIGLIP_ROWMAP_MISSING: {rowmap_path}")

        # Verify checksums
        if sha256_file(index_path) != done.get("index_sha256"):
            raise ProviderIntegrityError("SIGLIP_INDEX_CHECKSUM_MISMATCH")
        if sha256_file(rowmap_path) != done.get("rowmap_sha256"):
            raise ProviderIntegrityError("SIGLIP_ROWMAP_CHECKSUM_MISMATCH")

        # Load FAISS index
        index = faiss.read_index(str(index_path))
        if int(index.ntotal) != done.get("row_count", -1):
            raise ProviderIntegrityError(
                f"SIGLIP_FAISS_COUNT_MISMATCH: {index.ntotal} != {done.get('row_count')}"
            )
        if int(index.d) != SIGLIP_DIMENSION:
            raise ProviderIntegrityError(
                f"SIGLIP_FAISS_DIMENSION_MISMATCH: {index.d} != {SIGLIP_DIMENSION}"
            )

        # Load rowmap
        rowmap: list[dict[str, Any]] = []
        seen_uids: set[str] = set()
        with open(rowmap_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ProviderIntegrityError(f"SIGLIP_ROWMAP_MALFORMED_LINE_{line_no}: {exc}") from exc
                uid = entry.get("keyframe_uid", "")
                if not uid.startswith("CUSTOM:"):
                    raise ProviderIntegrityError(f"SIGLIP_ROWMAP_NON_CUSTOM: {uid}")
                if uid in seen_uids:
                    raise ProviderIntegrityError(f"SIGLIP_ROWMAP_DUPLICATE: {uid}")
                seen_uids.add(uid)
                rowmap.append(entry)

        if len(rowmap) != int(index.ntotal):
            raise ProviderIntegrityError(
                f"SIGLIP_ROWMAP_COUNT_MISMATCH: {len(rowmap)} != {index.ntotal}"
            )

        # Load passport
        passport_path = self.index_dir / "siglip_custom_passport.json"
        passport = {}
        if passport_path.is_file():
            try:
                passport = json.loads(passport_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

        return index, rowmap, done, passport

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._init_lock:
            if self._loaded:
                return
            index, rowmap, done, passport = self._load_index_and_rowmap()
            model, processor = self._model_loader()
            self._index = index
            self._rowmap = rowmap
            self._row_to_video = {i: entry["video_id"] for i, entry in enumerate(rowmap)}
            self._done = done
            self._passport = passport
            self._model = model
            self._processor = processor
            self._loaded = True

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        """Encode text queries to SigLIP2 embedding vectors.

        Args:
            queries: List of text queries

        Returns:
            float32 array of shape (N, 768), L2-normalized
        """
        import torch

        self._ensure_loaded()

        if not queries:
            raise ValueError("SIGLIP_QUERY_INVALID: empty query list")
        for q in queries:
            if not isinstance(q, str) or not q.strip():
                raise ValueError(f"SIGLIP_QUERY_INVALID: empty/whitespace query")

        inputs = self._processor(
            text=queries,
            padding=SIGLIP_PADDING,
            truncation=SIGLIP_TRUNCATION,
            max_length=SIGLIP_MAX_LENGTH,
            return_tensors="pt",
        )
        inputs = {k: v.to(self._device_str) for k, v in inputs.items() if isinstance(v, torch.Tensor)}

        with torch.no_grad():
            out = self._model.get_text_features(**inputs)
            if hasattr(out, "pooler_output") and out.pooler_output is not None:
                text_features = out.pooler_output
            elif isinstance(out, torch.Tensor):
                text_features = out
            else:
                text_features = out[0]
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        result = text_features.cpu().numpy().astype(np.float32)
        assert result.shape == (len(queries), SIGLIP_DIMENSION), f"Bad shape: {result.shape}"

        if not np.isfinite(result).all():
            raise ProviderIntegrityError("SIGLIP_QUERY_VECTOR_NOT_FINITE")

        return result

    def health(self) -> dict[str, Any]:
        """Return health check for SigLIP lane."""
        try:
            self._ensure_loaded()
            return {
                "lane_id": self.name,
                "status": "OK",
                "model_loaded": True,
                "processor_loaded": True,
                "index_loaded": True,
                "index_id": self._passport.get("index_id", "siglip_custom_faiss_v1"),
                "index_rows": int(self._index.ntotal),
                "rowmap_rows": len(self._rowmap),
                "dimension": SIGLIP_DIMENSION,
                "frame_space": "CUSTOM",
                "model_id": SIGLIP_MODEL_ID,
                "device": self._device_str,
                "index_checksum": self._done.get("index_sha256", ""),
                "rowmap_checksum": self._done.get("rowmap_sha256", ""),
                "metric": "INNER_PRODUCT",
            }
        except ProviderUnavailableError as exc:
            return {
                "lane_id": self.name,
                "status": "UNAVAILABLE",
                "error": str(exc),
                "model_loaded": False,
                "processor_loaded": False,
                "index_loaded": False,
            }
        except ProviderIntegrityError as exc:
            return {
                "lane_id": self.name,
                "status": "ERROR",
                "error": str(exc),
                "model_loaded": False,
                "processor_loaded": False,
                "index_loaded": False,
            }

    def capabilities(self) -> ProviderCapability:
        """Return ProviderCapability (SearchProvider protocol)."""
        if self._capability is not None:
            return self._capability
        try:
            self._ensure_loaded()
            self._capability = ProviderCapability(
                self.name,
                "OK",
                None,
                self.index_dir.name,
                {
                    "index_sha256": self._done.get("index_sha256", ""),
                    "rowmap_sha256": self._done.get("rowmap_sha256", ""),
                },
                {
                    "model_id": SIGLIP_MODEL_ID,
                    "frame_space": "CUSTOM",
                    "metric": "INNER_PRODUCT",
                    "device": self._device_str,
                },
                {
                    "vectors": int(self._index.ntotal),
                    "dimension": SIGLIP_DIMENSION,
                },
            )
        except ProviderUnavailableError as exc:
            self._capability = ProviderCapability(
                self.name, "UNAVAILABLE", str(exc), self.index_dir.name,
                {}, {"model_id": SIGLIP_MODEL_ID}, {},
            )
        except (ProviderIntegrityError, OSError, ValueError) as exc:
            self._capability = ProviderCapability(
                self.name, "INTEGRITY_ERROR", str(exc), self.index_dir.name,
                {}, {"model_id": SIGLIP_MODEL_ID}, {},
            )
        return self._capability

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        """Search SigLIP CUSTOM index with optional candidate video scope.

        Uses adaptive over-fetch for scoped queries: global FAISS search with
        increasing K until enough in-scope results are found.
        """
        cap = self.capabilities()
        if cap.status != "OK":
            raise ProviderUnavailableError(cap.reason or cap.status)

        # Encode query
        query_vec = self.encode_queries([query.query_text])

        # Determine scope
        allowed = set(query.video_ids) if query.video_ids else set()
        top_k = min(query.top_k, MAX_TOP_K)

        with self._search_lock:
            if not allowed:
                # Unscoped: simple FAISS search
                search_k = min(top_k, int(self._index.ntotal))
                scores, ids = self._index.search(query_vec, search_k)
                hits = self._build_hits(scores[0], ids[0], top_k=top_k)
            else:
                # Scoped: adaptive over-fetch
                hits = self._scoped_search(query_vec, allowed, top_k)

        return hits

    def _scoped_search(
        self,
        query_vec: np.ndarray,
        allowed: set[str],
        top_k: int,
    ) -> list[ProviderHit]:
        """Adaptive over-fetch scoped search."""
        fetch_k = min(top_k * 4, int(self._index.ntotal))
        multiplier = 4

        while True:
            scores, ids = self._index.search(query_vec, fetch_k)
            hits = self._build_hits(scores[0], ids[0], top_k=top_k, allowed=allowed)

            if len(hits) >= top_k or fetch_k >= int(self._index.ntotal):
                return hits

            # Expand
            multiplier *= 2
            if multiplier > MAX_OVERFETCH_MULTIPLIER:
                return hits
            fetch_k = min(top_k * multiplier, int(self._index.ntotal))

    def _build_hits(
        self,
        scores: np.ndarray,
        ids: np.ndarray,
        *,
        top_k: int,
        allowed: set[str] | None = None,
    ) -> list[ProviderHit]:
        """Build ProviderHit list from FAISS results."""
        hits: list[ProviderHit] = []
        for faiss_id, score in zip(ids, scores):
            faiss_id = int(faiss_id)
            if faiss_id < 0:
                continue

            if faiss_id >= len(self._rowmap):
                raise ProviderIntegrityError(f"SIGLIP_ROW_MAPPING_ERROR: {faiss_id}")

            entry = self._rowmap[faiss_id]
            video_id = entry["video_id"]

            if allowed and video_id not in allowed:
                continue

            rank = len(hits) + 1
            pts_time = float(entry["raw_pts_time"])
            hits.append(ProviderHit(
                provider=self.name,
                evidence_id=entry["keyframe_uid"],
                video_id=video_id,
                rank=rank,
                start_sec=pts_time,
                end_sec=pts_time,
                anchor_sec=pts_time,
                raw_score=float(score),
                score_kind="cosine_ip_higher_is_better",
                artifact_version=self.index_dir.name,
                source_video_relpath=None,
                payload={
                    "keyframe_uid": entry["keyframe_uid"],
                    "frame_idx": entry["frame_idx"],
                    "timestamp_ms": entry["timestamp_ms"],
                    "image_relpath": entry["image_relpath"],
                    "faiss_row": faiss_id,
                    "lane": self.name,
                    "frame_space": "CUSTOM",
                },
                provenance={
                    "index_sha256": self._done.get("index_sha256", ""),
                    "rowmap_sha256": self._done.get("rowmap_sha256", ""),
                    "model_id": SIGLIP_MODEL_ID,
                },
            ))

            if len(hits) >= top_k:
                break

        return hits
