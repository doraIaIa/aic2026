from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class BtcKeyframeRecord:
    """Canonical BTC keyframe record.
    
    BTC and CUSTOM are independent frame spaces:
      - Keyframe UID is strictly namespaced: 'BTC:{video_id}:KF{local_keyframe_no:06d}'
      - local_keyframe_no (n) comes from verified map CSV (1-indexed)
      - Physical frame_idx and raw_pts_time come directly from verified map CSV
      - timestamp_ms is deterministically derived as int(round(raw_pts_time * 1000))
    """

    keyframe_uid: str
    video_id: str
    video_ordinal: int
    ordinal_space_id: str
    local_keyframe_no: int
    frame_idx: int
    timestamp_ms: int
    raw_pts_time: float
    fps: float
    image_relpath: str
    frame_space: str = "BTC"
    btc_space_id: str = "btc_keyframes_v1"
    map_source_id: str = "btc_map_keyframes_raw_v1"
    clip_status: str = "HAS_CLIP_ROW"  # "HAS_CLIP_ROW" | "NO_CLIP"
    object_status: str = "HAS_OBJECTS"  # "HAS_OBJECTS" | "EMPTY" | "UNAVAILABLE"
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BtcKeyframeRecord:
        return cls(
            keyframe_uid=data["keyframe_uid"],
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            ordinal_space_id=data.get("ordinal_space_id", "v1_natural_series_video"),
            local_keyframe_no=int(data["local_keyframe_no"]),
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            raw_pts_time=float(data["raw_pts_time"]),
            fps=float(data["fps"]),
            image_relpath=data["image_relpath"],
            frame_space=data.get("frame_space", "BTC"),
            btc_space_id=data.get("btc_space_id", "btc_keyframes_v1"),
            map_source_id=data.get("map_source_id", "btc_map_keyframes_raw_v1"),
            clip_status=data.get("clip_status", "HAS_CLIP_ROW"),
            object_status=data.get("object_status", "HAS_OBJECTS"),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class BtcClipRowRecord:
    """1:1 deterministic mapping record for a raw BTC CLIP feature row."""

    clip_source_id: str
    video_id: str
    video_ordinal: int
    ordinal_space_id: str
    row_in_video: int
    keyframe_uid: str
    local_keyframe_no: int
    frame_idx: int
    timestamp_ms: int
    feature_relpath: str
    dimension: int = 512
    dtype: str = "float16"
    normalized: bool = True
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BtcClipRowRecord:
        return cls(
            clip_source_id=data.get("clip_source_id", "btc_clip_features_32_v1"),
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            ordinal_space_id=data.get("ordinal_space_id", "v1_natural_series_video"),
            row_in_video=int(data["row_in_video"]),
            keyframe_uid=data["keyframe_uid"],
            local_keyframe_no=int(data["local_keyframe_no"]),
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            feature_relpath=data["feature_relpath"],
            dimension=int(data.get("dimension", 512)),
            dtype=data.get("dtype", "float16"),
            normalized=bool(data.get("normalized", True)),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class BtcObjectDetectionRecord:
    """Canonical object detection record for a BTC keyframe."""

    detection_uid: str
    keyframe_uid: str
    video_id: str
    video_ordinal: int
    local_keyframe_no: int
    frame_idx: int
    timestamp_ms: int
    local_detection_index: int
    class_name: str  # OpenImages MID e.g. "/m/01jfsr"
    class_entity: Optional[str]  # English class name e.g. "Lantern"
    class_label: Optional[str]  # e.g. "84"
    confidence: float
    bbox: List[float]  # [ymin, xmin, ymax, xmax] normalized
    frame_space: str = "BTC"
    source_id: str = "btc_objects_raw_v1"
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BtcObjectDetectionRecord:
        return cls(
            detection_uid=data["detection_uid"],
            keyframe_uid=data["keyframe_uid"],
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            local_keyframe_no=int(data["local_keyframe_no"]),
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            local_detection_index=int(data["local_detection_index"]),
            class_name=data["class_name"],
            class_entity=data.get("class_entity"),
            class_label=data.get("class_label"),
            confidence=float(data["confidence"]),
            bbox=[float(x) for x in data["bbox"]],
            frame_space=data.get("frame_space", "BTC"),
            source_id=data.get("source_id", "btc_objects_raw_v1"),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class BtcObjectCoverageRecord:
    """Keyframe-level object coverage record across all BTC keyframes."""

    keyframe_uid: str
    video_id: str
    video_ordinal: int
    local_keyframe_no: int
    frame_idx: int
    timestamp_ms: int
    detection_count: int
    object_status: str  # "HAS_OBJECTS" | "EMPTY" | "UNAVAILABLE"
    source_file_relpath: str
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BtcObjectCoverageRecord:
        return cls(
            keyframe_uid=data["keyframe_uid"],
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            local_keyframe_no=int(data["local_keyframe_no"]),
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            detection_count=int(data["detection_count"]),
            object_status=data["object_status"],
            source_file_relpath=data.get("source_file_relpath", ""),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class BtcMediaInfoRecord:
    """Video-level YouTube media info record (video prior, not frame truth)."""

    video_id: str
    video_ordinal: int
    ordinal_space_id: str
    title: str
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    author: Optional[str] = None
    channel_id: Optional[str] = None
    channel_url: Optional[str] = None
    publish_date: Optional[str] = None
    duration_sec: Optional[int] = None
    thumbnail_url: Optional[str] = None
    watch_url: Optional[str] = None
    source_id: str = "btc_media_info_raw_v1"
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BtcMediaInfoRecord:
        return cls(
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            ordinal_space_id=data.get("ordinal_space_id", "v1_natural_series_video"),
            title=data.get("title", ""),
            description=data.get("description"),
            keywords=data.get("keywords") if data.get("keywords") is not None else [],
            author=data.get("author"),
            channel_id=data.get("channel_id"),
            channel_url=data.get("channel_url"),
            publish_date=data.get("publish_date"),
            duration_sec=int(data["duration_sec"]) if data.get("duration_sec") is not None else (int(data["length"]) if data.get("length") is not None else None),
            thumbnail_url=data.get("thumbnail_url"),
            watch_url=data.get("watch_url"),
            source_id=data.get("source_id", "btc_media_info_raw_v1"),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class BtcSpace:
    """Metadata space contract for canonical BTC keyframes."""

    btc_space_id: str
    frame_space: str
    schema_version: str
    keyframe_count: int
    video_count: int
    identity_rule: str
    catalog_checksum: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BtcSpace:
        return cls(
            btc_space_id=data["btc_space_id"],
            frame_space=data.get("frame_space", "BTC"),
            schema_version=data.get("schema_version", "v1"),
            keyframe_count=int(data["keyframe_count"]),
            video_count=int(data["video_count"]),
            identity_rule=data["identity_rule"],
            catalog_checksum=data["catalog_checksum"],
            created_at=data["created_at"],
        )


@dataclass(frozen=True)
class BtcValidationResult:
    """Comprehensive validation result for M1D BTC Data Hub."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]
    map_csv_count: int
    map_row_count: int
    jpeg_count: int
    btc_keyframe_count: int
    btc_video_count: int
    btc_catalog_checksum: str
    raw_clip_file_count: int
    raw_clip_row_count: int
    raw_clip_mapped_rows: int
    raw_clip_unmapped_rows: int
    raw_clip_rowmap_checksum: str
    object_video_count: int
    object_keyframe_count: int
    object_detection_count: int
    object_empty_keyframe_count: int
    object_unavailable_keyframe_count: int
    object_canonical_checksum: str
    media_info_count: int
    media_info_checksum: str
    faiss_vector_rows: int
    faiss_mapped_rows: int
    faiss_orphan_rows: int
    faiss_checksum: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
