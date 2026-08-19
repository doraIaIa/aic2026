"""BTC CLIP visual retrieval provider.

Provides standalone OpenCLIP ViT-B-32/openai text-to-image search over BTC keyframes
via existing IndexIDMap2(IndexFlatIP) FAISS index. Follows the SearchProvider protocol.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from aic2026.core.hashing import sha256_file
from aic2026.core.paths import PathContractError, normalize_relpath
from aic2026.retrieval.clip_faiss import stable_embedding_id
from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)

# Frozen BTC CLIP model contract
BTC_CLIP_MODEL_NAME = "ViT-B-32"
BTC_CLIP_PRETRAINED = "openai"
BTC_CLIP_DIMENSION = 512
BTC_CLIP_METRIC = "cosine_via_normalized_inner_product"

# Maximum sane top_k
MAX_TOP_K = 300
# Maximum over-fetch multiplier for adaptive scope search
MAX_OVERFETCH_MULTIPLIER = 64


class BtcClipProvider:
    """Cached OpenCLIP/FAISS provider for canonical BTC keyframe visual search.

    Implements the SearchProvider protocol with lazy model/index loading,
    adaptive candidate-video scope filtering, and thread-safe search.
    """

    name = "btc_clip"

    def __init__(
        self,
        artifact_dir: str | Path,
        *,
        model_name: str = BTC_CLIP_MODEL_NAME,
        pretrained: str = BTC_CLIP_PRETRAINED,
        device: str = "auto",
        model_loader: Callable[[], tuple[Any, Any]] | None = None,
        index_loader: Callable[[Path], Any] | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.model_name = model_name
        self.pretrained = pretrained
        self.device = device
        self._model_loader = model_loader or self._default_model_loader
        self._index_loader = index_loader or self._default_index_loader
        self._init_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self._loaded = False
        self._index: Any = None
        self._model: Any = None
        self._tokenizer: Any = None
        self._metadata: dict[int, dict[str, Any]] = {}
        self._embedding_ids_by_video: dict[str, list[int]] = {}
        self._done: dict[str, Any] = {}
        self._capability: ProviderCapability | None = None
        self._device_str: str = "cpu"

    @staticmethod
    def _default_index_loader(path: Path) -> Any:
        try:
            import faiss
        except ImportError as exc:
            raise ProviderUnavailableError("FAISS_DEPENDENCY_MISSING") from exc
        return faiss.read_index(str(path))

    def _default_model_loader(self) -> tuple[Any, Any]:
        """Load OpenCLIP model and tokenizer."""
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise ProviderUnavailableError("OPENCLIP_DEPENDENCY_MISSING: open-clip-torch") from exc

        device = self.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._device_str = device

        try:
            model, _, _ = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained,
                device=device,
            )
            tokenizer = open_clip.get_tokenizer(self.model_name)
            model.eval()
        except Exception as exc:
            raise ProviderUnavailableError(f"OPENCLIP_MODEL_UNAVAILABLE: {exc}") from exc

        return model, tokenizer

    def _load_marker_and_metadata(self) -> tuple[dict[str, Any], dict[int, dict[str, Any]], Path]:
        """Load and validate DONE.json marker, metadata.jsonl, and index path."""
        marker_path = self.artifact_dir / "DONE.json"
        if not marker_path.is_file():
            raise ProviderUnavailableError("BTC_CLIP_DONE_MARKER_MISSING")

        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderIntegrityError(f"BTC_CLIP_DONE_MARKER_INVALID: {exc}") from exc

        if marker.get("task") != "clip_faiss_index" or marker.get("schema_version") != 1:
            raise ProviderIntegrityError("BTC_CLIP_DONE_MARKER_CONTRACT_MISMATCH")

        index_path = self.artifact_dir / str(marker.get("index_file", ""))
        metadata_path = self.artifact_dir / str(marker.get("metadata_file", ""))

        if not index_path.is_file() or not metadata_path.is_file():
            raise ProviderUnavailableError("BTC_CLIP_INDEX_OR_METADATA_MISSING")

        # Verify SHA256 checksums
        if sha256_file(index_path) != marker.get("index_sha256"):
            raise ProviderIntegrityError("BTC_CLIP_INDEX_CHECKSUM_MISMATCH")
        if sha256_file(metadata_path) != marker.get("metadata_sha256"):
            raise ProviderIntegrityError("BTC_CLIP_METADATA_CHECKSUM_MISMATCH")

        metadata: dict[int, dict[str, Any]] = {}
        with metadata_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                try:
                    row = json.loads(line)
                    embedding_id = int(row["embedding_id"])
                    video_id = str(row["video_id"])
                    csv_n = int(row["csv_n"])
                    clip_row = int(row["clip_row"])
                    frame_idx = int(row["frame_idx"])
                    pts_time = float(row["pts_time"])
                    keyframe_id = str(row["keyframe_id"])
                    relpath = normalize_relpath(str(row["keyframe_relpath"]))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError, PathContractError) as exc:
                    raise ProviderIntegrityError(
                        f"BTC_CLIP_METADATA_MALFORMED_LINE_{line_number}: {exc}"
                    ) from exc

                expected_keyframe_id = f"{video_id}:{csv_n}"
                expected_name = f"{csv_n:03d}.jpg"
                if csv_n < 1 or clip_row != csv_n - 1 or frame_idx < 0 or pts_time < 0:
                    raise ProviderIntegrityError(f"BTC_CLIP_MAPPING_INVALID_LINE_{line_number}")
                if keyframe_id != expected_keyframe_id or Path(relpath).name != expected_name:
                    raise ProviderIntegrityError(f"BTC_CLIP_KEYFRAME_ORDINAL_INVALID_LINE_{line_number}")
                if embedding_id != stable_embedding_id(keyframe_id) or embedding_id in metadata:
                    raise ProviderIntegrityError(f"BTC_CLIP_STABLE_ID_INVALID_LINE_{line_number}")

                # Strict canonical BTC keyframe UID format: BTC:<video_id>:KF<csv_n:06d>
                canonical_uid = f"BTC:{video_id}:KF{csv_n:06d}"
                timestamp_ms = int(round(pts_time * 1000))

                metadata[embedding_id] = {
                    "embedding_id": embedding_id,
                    "keyframe_id": keyframe_id,
                    "keyframe_uid": canonical_uid,
                    "video_id": video_id,
                    "csv_n": csv_n,
                    "clip_row": clip_row,
                    "frame_idx": frame_idx,
                    "pts_time": pts_time,
                    "timestamp_ms": timestamp_ms,
                    "keyframe_relpath": relpath,
                }

        expected_count = marker.get("expected_count")
        if len(metadata) != expected_count or len(metadata) != marker.get("processed_count"):
            raise ProviderIntegrityError("BTC_CLIP_METADATA_COUNT_MISMATCH")

        return marker, metadata, index_path

    def _ensure_loaded(self) -> None:
        """Thread-safe lazy initialization of FAISS index, metadata, and encoder."""
        if self._loaded:
            return
        with self._init_lock:
            if self._loaded:
                return

            # 1. Load marker and metadata
            marker, metadata, index_path = self._load_marker_and_metadata()

            # 2. Load FAISS index
            index = self._index_loader(index_path)
            if int(getattr(index, "ntotal", -1)) != len(metadata):
                raise ProviderIntegrityError(
                    f"BTC_CLIP_FAISS_COUNT_MISMATCH: {getattr(index, 'ntotal', -1)} != {len(metadata)}"
                )
            if int(getattr(index, "d", -1)) != BTC_CLIP_DIMENSION:
                raise ProviderIntegrityError(
                    f"BTC_CLIP_FAISS_DIMENSION_MISMATCH: {getattr(index, 'd', -1)} != {BTC_CLIP_DIMENSION}"
                )

            # 3. Load model and tokenizer
            model, tokenizer = self._model_loader()

            # 4. Build video-to-embedding_ids map
            by_video: dict[str, list[int]] = {}
            for emb_id, row in metadata.items():
                vid = row["video_id"]
                by_video.setdefault(vid, []).append(emb_id)

            self._done = marker
            self._metadata = metadata
            self._embedding_ids_by_video = by_video
            self._index = index
            self._model = model
            self._tokenizer = tokenizer
            self._loaded = True

    def health(self) -> dict[str, Any]:
        """Return health status dictionary."""
        try:
            self._ensure_loaded()
            return {
                "lane_id": self.name,
                "status": "OK",
                "model_loaded": self._model is not None,
                "tokenizer_loaded": self._tokenizer is not None,
                "index_loaded": self._index is not None,
                "index_id": "clip-faiss-btc-v1",
                "index_rows": len(self._metadata),
                "metadata_rows": len(self._metadata),
                "dimension": BTC_CLIP_DIMENSION,
                "frame_space": "BTC",
                "model_name": self.model_name,
                "pretrained": self.pretrained,
                "device": self._device_str,
                "index_checksum": self._done.get("index_sha256"),
                "metadata_checksum": self._done.get("metadata_sha256"),
                "metric": BTC_CLIP_METRIC,
                "error": None,
            }
        except ProviderUnavailableError as exc:
            return {
                "lane_id": self.name,
                "status": "UNAVAILABLE",
                "error": str(exc),
                "model_loaded": False,
                "tokenizer_loaded": False,
                "index_loaded": False,
            }
        except (ProviderIntegrityError, OSError, ValueError) as exc:
            return {
                "lane_id": self.name,
                "status": "ERROR",
                "error": str(exc),
                "model_loaded": False,
                "tokenizer_loaded": False,
                "index_loaded": False,
            }

    def capabilities(self) -> ProviderCapability:
        """Return ProviderCapability for orchestrator compatibility."""
        if self._capability is not None:
            return self._capability
        h = self.health()
        status = h["status"]
        if status == "OK":
            self._capability = ProviderCapability(
                self.name,
                "OK",
                None,
                self.artifact_dir.name,
                {
                    "index_sha256": h.get("index_checksum", ""),
                    "metadata_sha256": h.get("metadata_checksum", ""),
                },
                {
                    "model_name": self.model_name,
                    "pretrained": self.pretrained,
                    "frame_space": "BTC",
                    "metric": BTC_CLIP_METRIC,
                    "quality_status": "BLOCKED_BY_GROUND_TRUTH",
                },
                {"vectors": h.get("index_rows", 0), "dimension": BTC_CLIP_DIMENSION},
            )
        elif status == "UNAVAILABLE":
            self._capability = ProviderCapability(
                self.name,
                "UNAVAILABLE",
                h.get("error"),
                self.artifact_dir.name,
                {},
                {"model_name": self.model_name, "pretrained": self.pretrained},
                {},
            )
        else:
            self._capability = ProviderCapability(
                self.name,
                "INTEGRITY_ERROR",
                h.get("error"),
                self.artifact_dir.name,
                {},
                {"model_name": self.model_name, "pretrained": self.pretrained},
                {},
            )
        return self._capability

    def encode_text(self, text: str) -> np.ndarray:
        """Encode a single text query into a 512D unit-normalized float32 vector."""
        return self.encode_queries([text])[0]

    def encode_queries(self, queries: Sequence[str]) -> np.ndarray:
        """Encode multiple text queries into [N, 512] unit-normalized float32 vectors."""
        self._ensure_loaded()
        if not queries:
            return np.empty((0, BTC_CLIP_DIMENSION), dtype=np.float32)

        for i, q in enumerate(queries):
            if not isinstance(q, str) or not q.strip():
                raise ValueError(f"BTC CLIP query at index {i} must be a non-empty string.")

        import torch

        # Tokenize using OpenCLIP tokenizer
        tokens = self._tokenizer(list(queries)).to(self._device_str)

        with self._search_lock:
            with torch.no_grad():
                vectors = self._model.encode_text(tokens)
                # Unit L2 normalization
                vectors = vectors / vectors.norm(dim=-1, keepdim=True)
                np_vectors = vectors.cpu().numpy().astype(np.float32)

        if not np.isfinite(np_vectors).all():
            raise ProviderIntegrityError("BTC CLIP query vector contains NaN or Inf.")

        return np_vectors

    def search(
        self,
        query: str | ProviderQuery,
        *,
        top_k: int = 20,
        candidate_video_ids: set[str] | Sequence[str] | None = None,
        query_id: str | None = None,
        query_variant_id: str | None = None,
    ) -> list[ProviderHit]:
        """Perform visual search over BTC keyframes with optional candidate scope filtering."""
        # Unpack query argument
        if isinstance(query, ProviderQuery):
            query_text = query.query_text
            k = query.top_k or top_k
            allowed_videos = set(query.video_ids) if query.video_ids else None
            q_id = query_id
        else:
            query_text = query
            k = top_k
            allowed_videos = set(candidate_video_ids) if candidate_video_ids is not None else None
            q_id = query_id

        if not query_text or not query_text.strip():
            raise ValueError("Query text cannot be empty.")
        if k < 1:
            raise ValueError(f"top_k must be >= 1, got {k}")
        k = min(k, MAX_TOP_K)

        self._ensure_loaded()
        ntotal = int(self._index.ntotal)

        # Handle empty candidate video set
        if allowed_videos is not None and len(allowed_videos) == 0:
            return []

        # Filter allowed videos to those actually present in metadata
        if allowed_videos is not None:
            valid_videos = allowed_videos.intersection(self._embedding_ids_by_video.keys())
            if not valid_videos:
                return []

        # Encode query to 512D unit vector
        query_vec = self.encode_text(query_text).reshape(1, -1)

        # Adaptive over-fetch loop
        hits: list[ProviderHit] = []
        multiplier = 1
        seen_embs: set[int] = set()

        while len(hits) < k:
            search_k = min(ntotal, k * multiplier if allowed_videos is not None else k)
            with self._search_lock:
                scores, ids = self._index.search(query_vec, search_k)

            scores_row = scores[0]
            ids_row = ids[0]

            for score, emb_id_int in zip(scores_row, ids_row):
                emb_id = int(emb_id_int)
                if emb_id < 0 or emb_id in seen_embs:
                    continue
                seen_embs.add(emb_id)

                row = self._metadata.get(emb_id)
                if row is None:
                    raise ProviderIntegrityError(f"BTC_CLIP_FAISS_ID_NOT_IN_METADATA: {emb_id}")

                if allowed_videos is not None and row["video_id"] not in allowed_videos:
                    continue

                rank = len(hits) + 1
                hit = ProviderHit(
                    provider=self.name,
                    evidence_id=row["keyframe_uid"],
                    video_id=row["video_id"],
                    rank=rank,
                    start_sec=row["pts_time"],
                    end_sec=row["pts_time"],
                    anchor_sec=row["pts_time"],
                    raw_score=float(score),
                    score_kind="cosine_ip_higher_is_better",
                    artifact_version=self.artifact_dir.name,
                    source_video_relpath=None,
                    payload={
                        "keyframe_uid": row["keyframe_uid"],
                        "keyframe_id": row["keyframe_id"],
                        "csv_n": row["csv_n"],
                        "clip_row": row["clip_row"],
                        "frame_idx": row["frame_idx"],
                        "pts_time": row["pts_time"],
                        "timestamp_ms": row["timestamp_ms"],
                        "keyframe_relpath": row["keyframe_relpath"],
                        "embedding_id": row["embedding_id"],
                        "lane": self.name,
                        "frame_space": "BTC",
                    },
                    provenance={
                        "index_sha256": self._done.get("index_sha256", ""),
                        "metadata_sha256": self._done.get("metadata_sha256", ""),
                        "model": self.model_name,
                        "pretrained": self.pretrained,
                    },
                )
                hits.append(hit)
                if len(hits) >= k:
                    break

            if allowed_videos is None or search_k >= ntotal or multiplier >= MAX_OVERFETCH_MULTIPLIER:
                break
            multiplier *= 2

        return hits
