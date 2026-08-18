from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

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


IndexLoader = Callable[[Path], Any]
EncoderLoader = Callable[[], Callable[[str], np.ndarray]]


class VisualProvider:
    """Cached CLIP/FAISS provider giữ nguyên canonical keyframe mapping."""

    name = "visual"

    def __init__(
        self,
        artifact_dir: str | Path,
        *,
        model_name: str = "ViT-B-32",
        pretrained: str = "openai",
        device: str = "auto",
        index_loader: IndexLoader | None = None,
        encoder_loader: EncoderLoader | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.model_name = model_name
        self.pretrained = pretrained
        self.device = device
        self._index_loader = index_loader or self._default_index_loader
        self._encoder_loader = encoder_loader or self._default_encoder_loader
        self._init_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self._loaded = False
        self._load_count = 0
        self._index: Any = None
        self._encoder: Callable[[str], np.ndarray] | None = None
        self._metadata: dict[int, dict[str, Any]] = {}
        self._marker: dict[str, Any] = {}
        self._capability: ProviderCapability | None = None

    @property
    def load_count(self) -> int:
        return self._load_count

    @staticmethod
    def _default_index_loader(path: Path) -> Any:
        try:
            import faiss
        except ImportError as exc:
            raise ProviderUnavailableError("FAISS_DEPENDENCY_MISSING") from exc
        return faiss.read_index(str(path))

    def _default_encoder_loader(self) -> Callable[[str], np.ndarray]:
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise ProviderUnavailableError("OPENCLIP_DEPENDENCY_MISSING") from exc
        selected_device = self.device
        if selected_device == "auto":
            selected_device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            model, _, _ = open_clip.create_model_and_transforms(
                self.model_name, pretrained=self.pretrained, device=selected_device
            )
            tokenizer = open_clip.get_tokenizer(self.model_name)
            model.eval()
        except Exception as exc:
            raise ProviderUnavailableError(f"OPENCLIP_MODEL_UNAVAILABLE: {exc}") from exc

        def encode(text: str) -> np.ndarray:
            tokens = tokenizer([text]).to(selected_device)
            with torch.no_grad():
                vector = model.encode_text(tokens)
                vector = vector / vector.norm(dim=-1, keepdim=True)
            return vector.cpu().numpy()[0].astype(np.float32)

        return encode

    def _load_marker_and_metadata(self) -> tuple[dict[str, Any], dict[int, dict[str, Any]], Path]:
        marker_path = self.artifact_dir / "DONE.json"
        if not marker_path.is_file():
            raise ProviderUnavailableError("VISUAL_DONE_MARKER_MISSING")
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderIntegrityError(f"VISUAL_DONE_MARKER_INVALID: {exc}") from exc
        if marker.get("task") != "clip_faiss_index" or marker.get("schema_version") != 1:
            raise ProviderIntegrityError("VISUAL_DONE_MARKER_CONTRACT_MISMATCH")
        index_path = self.artifact_dir / str(marker.get("index_file", ""))
        metadata_path = self.artifact_dir / str(marker.get("metadata_file", ""))
        if not index_path.is_file() or not metadata_path.is_file():
            raise ProviderUnavailableError("VISUAL_INDEX_OR_METADATA_MISSING")
        if sha256_file(index_path) != marker.get("index_sha256"):
            raise ProviderIntegrityError("VISUAL_INDEX_CHECKSUM_MISMATCH")
        if sha256_file(metadata_path) != marker.get("metadata_sha256"):
            raise ProviderIntegrityError("VISUAL_METADATA_CHECKSUM_MISMATCH")

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
                    raise ProviderIntegrityError(f"VISUAL_METADATA_MALFORMED_LINE_{line_number}: {exc}") from exc
                expected_keyframe_id = f"{video_id}:{csv_n}"
                expected_name = f"{csv_n:03d}.jpg"
                if csv_n < 1 or clip_row != csv_n - 1 or frame_idx < 0 or pts_time < 0:
                    raise ProviderIntegrityError(f"VISUAL_MAPPING_INVALID_LINE_{line_number}")
                if keyframe_id != expected_keyframe_id or Path(relpath).name != expected_name:
                    raise ProviderIntegrityError(f"VISUAL_KEYFRAME_ORDINAL_INVALID_LINE_{line_number}")
                if embedding_id != stable_embedding_id(keyframe_id) or embedding_id in metadata:
                    raise ProviderIntegrityError(f"VISUAL_STABLE_ID_INVALID_LINE_{line_number}")
                normalized = dict(row)
                normalized["keyframe_relpath"] = relpath
                metadata[embedding_id] = normalized
        expected_count = marker.get("expected_count")
        if len(metadata) != expected_count or len(metadata) != marker.get("processed_count"):
            raise ProviderIntegrityError("VISUAL_METADATA_COUNT_MISMATCH")
        return marker, metadata, index_path

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._init_lock:
            if self._loaded:
                return
            marker, metadata, index_path = self._load_marker_and_metadata()
            index = self._index_loader(index_path)
            if int(getattr(index, "ntotal", -1)) != len(metadata):
                raise ProviderIntegrityError("VISUAL_FAISS_COUNT_MISMATCH")
            if int(getattr(index, "d", -1)) != int(marker.get("vector_dim", -2)):
                raise ProviderIntegrityError("VISUAL_FAISS_DIMENSION_MISMATCH")
            encoder = self._encoder_loader()
            self._marker, self._metadata, self._index, self._encoder = marker, metadata, index, encoder
            self._loaded = True
            self._load_count += 1

    def capabilities(self) -> ProviderCapability:
        if self._capability is not None:
            return self._capability
        try:
            self._ensure_loaded()
            self._capability = ProviderCapability(
                self.name, "OK", None, self.artifact_dir.name,
                {"index_sha256": self._marker["index_sha256"], "metadata_sha256": self._marker["metadata_sha256"]},
                {"artifact_model": self._marker.get("model"), "artifact_model_revision": self._marker.get("model_revision"), "text_encoder": self.model_name, "pretrained": self.pretrained, "metric": self._marker.get("metric"), "quality_status": "BLOCKED_BY_GROUND_TRUTH"},
                {"vectors": len(self._metadata), "dimension": int(self._marker["vector_dim"])},
            )
        except ProviderUnavailableError as exc:
            self._capability = ProviderCapability(self.name, "UNAVAILABLE", str(exc), self.artifact_dir.name, {}, {"text_encoder": self.model_name, "pretrained": self.pretrained}, {})
        except (ProviderIntegrityError, OSError, ValueError) as exc:
            self._capability = ProviderCapability(self.name, "INTEGRITY_ERROR", str(exc), self.artifact_dir.name, {}, {"text_encoder": self.model_name, "pretrained": self.pretrained}, {})
        return self._capability

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        capability = self.capabilities()
        if capability.status != "OK" or self._encoder is None:
            raise ProviderUnavailableError(capability.reason or capability.status)
        with self._search_lock:
            vector = np.asarray(self._encoder(query.query_text), dtype=np.float32).reshape(1, -1)
            if vector.shape[1] != int(self._index.d) or not np.isfinite(vector).all():
                raise ProviderIntegrityError("VISUAL_QUERY_VECTOR_INVALID")
            norm = np.linalg.norm(vector, axis=1, keepdims=True)
            if np.any(norm == 0):
                raise ProviderIntegrityError("VISUAL_QUERY_VECTOR_ZERO_NORM")
            vector = np.ascontiguousarray(vector / norm, dtype=np.float32)
            search_k = min(query.top_k, int(self._index.ntotal))
            scores, ids = self._index.search(vector, search_k)
        allowed = set(query.video_ids)
        hits: list[ProviderHit] = []
        for embedding_id, score in zip(ids[0], scores[0]):
            if int(embedding_id) < 0:
                continue
            row = self._metadata.get(int(embedding_id))
            if row is None:
                raise ProviderIntegrityError(f"VISUAL_FAISS_ID_MISSING_METADATA: {int(embedding_id)}")
            if allowed and row["video_id"] not in allowed:
                continue
            rank = len(hits) + 1
            pts_time = float(row["pts_time"])
            hits.append(ProviderHit(
                provider=self.name, evidence_id=str(row["keyframe_id"]), video_id=str(row["video_id"]),
                rank=rank, start_sec=pts_time, end_sec=pts_time, anchor_sec=pts_time,
                raw_score=float(score), score_kind="cosine_ip_higher_is_better",
                artifact_version=self.artifact_dir.name, source_video_relpath=None,
                payload={"embedding_id": int(row["embedding_id"]), "keyframe_id": row["keyframe_id"], "csv_n": int(row["csv_n"]), "clip_row": int(row["clip_row"]), "frame_idx": int(row["frame_idx"]), "pts_time": pts_time, "keyframe_relpath": row["keyframe_relpath"]},
                provenance={"index_sha256": self._marker["index_sha256"], "metadata_sha256": self._marker["metadata_sha256"], "model_name": self.model_name, "pretrained": self.pretrained},
            ))
            if len(hits) >= query.top_k:
                break
        return hits
