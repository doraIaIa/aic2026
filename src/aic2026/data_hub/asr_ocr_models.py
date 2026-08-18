from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AsrSegmentRecord:
    """Canonical representation of an ASR speech transcript interval."""

    segment_uid: str
    source_segment_id: str
    video_id: str
    video_ordinal: int
    ordinal_space_id: str
    start_ms: int
    end_ms: int
    start_sec: float
    end_sec: float
    text_raw: str
    text_norm: str
    language: str = "vi"
    model: str = "whisper-medium"
    avg_logprob: Optional[float] = None
    no_speech_prob: Optional[float] = None
    compression_ratio: Optional[float] = None
    batch_id: Optional[str] = None
    source_file: Optional[str] = None
    source_id: str = "asr_whisper_medium_vi_full_v1"
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AsrSegmentRecord:
        return cls(
            segment_uid=data["segment_uid"],
            source_segment_id=data["source_segment_id"],
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            ordinal_space_id=data.get("ordinal_space_id", "v1_natural_series_video"),
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            start_sec=float(data["start_sec"]),
            end_sec=float(data["end_sec"]),
            text_raw=data["text_raw"],
            text_norm=data["text_norm"],
            language=data.get("language", "vi"),
            model=data.get("model", "whisper-medium"),
            avg_logprob=float(data["avg_logprob"]) if data.get("avg_logprob") is not None else None,
            no_speech_prob=float(data["no_speech_prob"]) if data.get("no_speech_prob") is not None else None,
            compression_ratio=float(data["compression_ratio"]) if data.get("compression_ratio") is not None else None,
            batch_id=data.get("batch_id"),
            source_file=data.get("source_file"),
            source_id=data.get("source_id", "asr_whisper_medium_vi_full_v1"),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class AsrVideoCoverageRecord:
    """Video-level ASR coverage record across all 873 canonical videos."""

    video_id: str
    video_ordinal: int
    ordinal_space_id: str
    segment_count: int
    duration_sec: float
    duration_ms: int
    asr_status: str  # "HAS_SEGMENTS" | "ZERO_ASR_SEGMENTS"
    source_id: str = "asr_whisper_medium_vi_full_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AsrVideoCoverageRecord:
        return cls(
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            ordinal_space_id=data.get("ordinal_space_id", "v1_natural_series_video"),
            segment_count=int(data["segment_count"]),
            duration_sec=float(data["duration_sec"]),
            duration_ms=int(data["duration_ms"]),
            asr_status=data["asr_status"],
            source_id=data.get("source_id", "asr_whisper_medium_vi_full_v1"),
        )


@dataclass(frozen=True)
class OcrItemRecord:
    """Canonical representation of an OCR detected text item on a CUSTOM keyframe."""

    ocr_uid: str
    video_id: str
    video_ordinal: int
    ordinal_space_id: str
    frame_space: str
    keyframe_uid: str
    frame_idx: int
    timestamp_ms: int
    raw_pts_time: float
    local_text_index: int
    text_raw: str
    text_norm: str
    bbox: Optional[List[float]] = None
    ocr_confidence: Optional[float] = None
    ocr_type: Optional[str] = None
    dense_embedding_ref: Optional[str] = None
    source_id: str = "ocr_custom_manifest_v1"
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OcrItemRecord:
        return cls(
            ocr_uid=data["ocr_uid"],
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            ordinal_space_id=data.get("ordinal_space_id", "v1_natural_series_video"),
            frame_space=data.get("frame_space", "CUSTOM"),
            keyframe_uid=data["keyframe_uid"],
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            raw_pts_time=float(data["raw_pts_time"]),
            local_text_index=int(data.get("local_text_index", 0)),
            text_raw=data["text_raw"],
            text_norm=data["text_norm"],
            bbox=list(data["bbox"]) if data.get("bbox") is not None else None,
            ocr_confidence=float(data["ocr_confidence"]) if data.get("ocr_confidence") is not None else None,
            ocr_type=data.get("ocr_type"),
            dense_embedding_ref=data.get("dense_embedding_ref"),
            source_id=data.get("source_id", "ocr_custom_manifest_v1"),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class OcrKeyframeCoverageRecord:
    """Keyframe-level OCR coverage manifest record."""

    keyframe_uid: str
    video_id: str
    video_ordinal: int
    frame_idx: int
    timestamp_ms: int
    raw_pts_time: float
    file_name: str
    image_relpath: str
    item_count: int
    source_id: str = "ocr_custom_manifest_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OcrKeyframeCoverageRecord:
        return cls(
            keyframe_uid=data["keyframe_uid"],
            video_id=data["video_id"],
            video_ordinal=int(data["video_ordinal"]),
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            raw_pts_time=float(data["raw_pts_time"]),
            file_name=data["file_name"],
            image_relpath=data["image_relpath"],
            item_count=int(data.get("item_count", 0)),
            source_id=data.get("source_id", "ocr_custom_manifest_v1"),
        )


@dataclass(frozen=True)
class OcrBgeRowmapRecord:
    """Dense vector row mapping connecting BGE-M3 embedding shards to canonical OCR items."""

    index_id: str
    shard_id: str
    row_in_shard: int
    ocr_uid: str
    keyframe_uid: str
    video_id: str
    frame_idx: int
    timestamp_ms: int
    global_row: Optional[int] = None
    source_metadata_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OcrBgeRowmapRecord:
        return cls(
            index_id=data.get("index_id", "ocr_bge_m3_single_text_v1"),
            shard_id=data["shard_id"],
            row_in_shard=int(data["row_in_shard"]),
            ocr_uid=data["ocr_uid"],
            keyframe_uid=data["keyframe_uid"],
            video_id=data["video_id"],
            frame_idx=int(data["frame_idx"]),
            timestamp_ms=int(data["timestamp_ms"]),
            global_row=int(data["global_row"]) if data.get("global_row") is not None else None,
            source_metadata_ref=data.get("source_metadata_ref"),
        )


@dataclass
class AsrOcrValidationResult:
    """Validation report for ASR and OCR canonical datasets."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # ASR stats
    asr_video_count: int = 0
    asr_segment_count: int = 0
    asr_videos_with_segments: int = 0
    asr_zero_segment_videos: int = 0
    asr_invalid_intervals: int = 0
    asr_canonical_checksum: str = ""

    # OCR stats
    ocr_keyframe_count: int = 0
    ocr_covered_videos: int = 0
    ocr_item_count: int = 0
    ocr_confidence_low_count: int = 0
    ocr_confidence_high_count: int = 0
    ocr_canonical_checksum: str = ""

    # BGE stats
    bge_vector_row_count: int = 0
    bge_metadata_row_count: int = 0
    bge_mapped_row_count: int = 0
    bge_unmapped_row_count: int = 0
    bge_rowmap_checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
