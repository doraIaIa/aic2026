from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class VectorIndexRecord:
    """Descriptor for a vector embedding matrix or FAISS index in the Vector/Index Registry."""

    index_id: str
    artifact_type: str  # 'RAW_EMBEDDING_MATRIX' | 'SHARDED_EMBEDDINGS' | 'FAISS_INDEX' | 'ROWMAP'
    entity_space: str  # 'KEYFRAME' | 'OCR_ITEM' | 'ASR_SEGMENT' | 'VIDEO'
    frame_space: Optional[str]  # 'BTC' | 'CUSTOM' | None
    model_id: str
    dimension: int
    dtype: str
    normalized: bool
    row_count: int
    status: str  # 'READY' | 'EMBEDDINGS_READY_INDEX_NOT_BUILT' | 'NOT_BUILT'
    logical_ref: str
    built_from: str
    model_revision: Optional[str] = None
    metric: Optional[str] = None
    rowmap_count: Optional[int] = None
    rowmap_checksum: Optional[str] = None
    artifact_checksum: Optional[str] = None
    query_preprocessing_version: Optional[str] = None
    ordinal_space_id: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VectorIndexRecord:
        return cls(
            index_id=data["index_id"],
            artifact_type=data["artifact_type"],
            entity_space=data["entity_space"],
            frame_space=data.get("frame_space"),
            model_id=data["model_id"],
            dimension=int(data["dimension"]),
            dtype=data["dtype"],
            normalized=bool(data["normalized"]),
            row_count=int(data["row_count"]),
            status=data["status"],
            logical_ref=data["logical_ref"],
            built_from=data["built_from"],
            model_revision=data.get("model_revision"),
            metric=data.get("metric"),
            rowmap_count=int(data["rowmap_count"]) if data.get("rowmap_count") is not None else None,
            rowmap_checksum=data.get("rowmap_checksum"),
            artifact_checksum=data.get("artifact_checksum"),
            query_preprocessing_version=data.get("query_preprocessing_version"),
            ordinal_space_id=data.get("ordinal_space_id"),
            notes=data.get("notes", []),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class ArtifactRegistryRecord:
    """Descriptor for a canonical file artifact registered in the Data Hub Artifact Registry."""

    artifact_id: str
    artifact_type: str  # 'JSONL_ENTITY_TABLE' | 'JSON_METADATA_SPACE' | 'ZIP_ARCHIVE' | 'SQLITE_DATABASE' | 'INDEX_BINARY'
    schema_version: str
    entity_space: str  # 'VIDEO' | 'CUSTOM_KEYFRAME' | 'BTC_KEYFRAME' | 'ASR_SEGMENT' | 'OCR_ITEM' | 'BTC_OBJECT_DETECTION' | 'TAXONOMY' | 'RUNTIME'
    logical_ref: str
    record_count: int
    checksum: str
    status: str  # 'READY' | 'READY_EXTERNAL' | 'PROMOTED'
    built_from: str
    producer: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ArtifactRegistryRecord:
        return cls(
            artifact_id=data["artifact_id"],
            artifact_type=data["artifact_type"],
            schema_version=data["schema_version"],
            entity_space=data["entity_space"],
            logical_ref=data["logical_ref"],
            record_count=int(data["record_count"]),
            checksum=data["checksum"],
            status=data["status"],
            built_from=data["built_from"],
            producer=data.get("producer"),
            notes=data.get("notes", []),
        )
