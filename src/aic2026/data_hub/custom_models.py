from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CustomKeyframeRecord:
    """Canonical representation of a single CUSTOM keyframe."""

    keyframe_uid: str
    video_id: str
    video_ordinal: int
    ordinal_space_id: str
    frame_idx: int
    timestamp_ms: int
    raw_pts_time: float
    shot_id: int
    cluster_id: int
    embedding_index: int
    source_keyframe_id: int
    file_name: str
    image_relpath: str
    qwen_status: str = "OK"  # "OK" | "MISSING"
    frame_space: str = "CUSTOM"
    schema_version: str = "v1"
    source_id: str = "custom_keyframes_raw_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustomKeyframeRecord:
        return cls(
            keyframe_uid=data["keyframe_uid"],
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            ordinal_space_id=data.get("ordinal_space_id", "v1_natural_series_video"),
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            raw_pts_time=float(data["raw_pts_time"]),
            shot_id=int(data.get("shot_id", 0)),
            cluster_id=int(data.get("cluster_id", 0)),
            embedding_index=int(data.get("embedding_index", 0)),
            source_keyframe_id=int(data.get("source_keyframe_id", 0)),
            file_name=data["file_name"],
            image_relpath=data["image_relpath"],
            qwen_status=data.get("qwen_status", "OK"),
            frame_space=data.get("frame_space", "CUSTOM"),
            schema_version=data.get("schema_version", "v1"),
            source_id=data.get("source_id", "custom_keyframes_raw_v1"),
        )


@dataclass(frozen=True)
class QwenSemanticRecord:
    """Normalized Qwen visual semantic observation for a CUSTOM keyframe."""

    keyframe_uid: str
    video_id: str
    frame_idx: int
    timestamp_ms: int
    raw_pts_time: float
    objects: List[str] = field(default_factory=list)
    attributes: List[str] = field(default_factory=list)
    spatial_relations: List[str] = field(default_factory=list)
    counts: List[str] = field(default_factory=list)
    scene: List[str] = field(default_factory=list)
    visible_actions: List[str] = field(default_factory=list)
    caption: str = ""
    semantic_status: str = "OK"
    frame_space: str = "CUSTOM"
    schema_version: str = "v1"
    source_id: str = "qwen_raw_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QwenSemanticRecord:
        return cls(
            keyframe_uid=data["keyframe_uid"],
            video_id=data["video_id"],
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            raw_pts_time=float(data["raw_pts_time"]),
            objects=list(data.get("objects", [])),
            attributes=list(data.get("attributes", [])),
            spatial_relations=list(data.get("spatial_relations", [])),
            counts=list(data.get("counts", [])),
            scene=list(data.get("scene", [])),
            visible_actions=list(data.get("visible_actions", [])),
            caption=data.get("caption", ""),
            semantic_status=data.get("semantic_status", "OK"),
            frame_space=data.get("frame_space", "CUSTOM"),
            schema_version=data.get("schema_version", "v1"),
            source_id=data.get("source_id", "qwen_raw_v1"),
        )


@dataclass(frozen=True)
class QwenMissingRecord:
    """Explicit record of a keyframe that does not have valid Qwen semantic data."""

    keyframe_uid: str
    video_id: str
    frame_idx: int
    timestamp_ms: int
    raw_pts_time: float
    reason: str = "EMPTY_OR_UNPARSED_OUTPUT"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QwenMissingRecord:
        return cls(
            keyframe_uid=data["keyframe_uid"],
            video_id=data["video_id"],
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            raw_pts_time=float(data["raw_pts_time"]),
            reason=data.get("reason", "EMPTY_OR_UNPARSED_OUTPUT"),
        )


@dataclass(frozen=True)
class CustomSpace:
    """Passport metadata for the CUSTOM keyframe space."""

    custom_space_id: str
    frame_space: str
    schema_version: str
    keyframe_count: int
    video_count: int
    identity_rule: str
    source_checksum: str
    catalog_checksum: str
    created_at: str
    status: str = "READY"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustomSpace:
        return cls(
            custom_space_id=data["custom_space_id"],
            frame_space=data.get("frame_space", "CUSTOM"),
            schema_version=data.get("schema_version", "v1"),
            keyframe_count=int(data["keyframe_count"]),
            video_count=int(data["video_count"]),
            identity_rule=data.get("identity_rule", "CUSTOM:{video_id}:F{frame_idx}"),
            source_checksum=data.get("source_checksum", ""),
            catalog_checksum=data["catalog_checksum"],
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            status=data.get("status", "READY"),
        )


@dataclass
class CustomValidationResult:
    """Structured validation report for Custom Keyframes and Qwen semantics."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    custom_keyframe_count: int = 0
    unique_keyframe_count: int = 0
    covered_video_count: int = 0
    qwen_valid_count: int = 0
    qwen_joined_count: int = 0
    qwen_missing_count: int = 0
    qwen_orphan_count: int = 0
    pts_mismatch_count: int = 0
    custom_catalog_checksum: str = ""
    qwen_canonical_checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
