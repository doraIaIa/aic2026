from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class VideoRecord:
    """Canonical representation of a single video in the AIC 2026 catalog."""

    video_id: str
    ordinal: int
    ordinal_space_id: str
    series: str
    source_relpath: str
    duration_ms: Optional[int] = None
    duration_sec: Optional[float] = None
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    status_flags: str = "OK"
    source_id: str = "canonical_video_universe_v1"
    schema_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VideoRecord:
        return cls(
            video_id=data["video_id"],
            ordinal=int(data["ordinal"]),
            ordinal_space_id=data.get("ordinal_space_id", "v1_natural_series_video"),
            series=data.get("series", data["video_id"].split("_")[0] if "_" in data["video_id"] else ""),
            source_relpath=data["source_relpath"],
            duration_ms=data.get("duration_ms"),
            duration_sec=data.get("duration_sec"),
            fps=data.get("fps"),
            width=data.get("width"),
            height=data.get("height"),
            status_flags=data.get("status_flags", "OK"),
            source_id=data.get("source_id", "canonical_video_universe_v1"),
            schema_version=data.get("schema_version", "v1"),
        )


@dataclass(frozen=True)
class VideoSpace:
    """Metadata defining a deterministic coordinate space for video ordinals."""

    video_space_id: str
    schema_version: str
    video_count: int
    ordering_rule: str
    catalog_checksum: str
    created_at: str
    series_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VideoSpace:
        return cls(
            video_space_id=data["video_space_id"],
            schema_version=data.get("schema_version", "v1"),
            video_count=int(data["video_count"]),
            ordering_rule=data.get("ordering_rule", "natural_sort_series_video_asc"),
            catalog_checksum=data["catalog_checksum"],
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            series_counts=data.get("series_counts", {}),
        )


@dataclass(frozen=True)
class SourceRecord:
    """Entry in the Source Registry establishing provenance of source artifacts."""

    source_id: str
    source_type: str
    scope: str
    relative_path_or_logical_ref: str
    schema_version: str
    record_count: int
    checksum: str
    producer: Optional[str] = None
    status: str = "READY"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SourceRecord:
        return cls(
            source_id=data["source_id"],
            source_type=data["source_type"],
            scope=data["scope"],
            relative_path_or_logical_ref=data["relative_path_or_logical_ref"],
            schema_version=data.get("schema_version", "v1"),
            record_count=int(data["record_count"]),
            checksum=data.get("checksum", ""),
            producer=data.get("producer"),
            status=data.get("status", "READY"),
            notes=data.get("notes", []),
        )


@dataclass
class ValidationResult:
    """Structured result from VideoRegistryValidator."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    video_count: int = 0
    unique_video_count: int = 0
    ordinal_min: Optional[int] = None
    ordinal_max: Optional[int] = None
    series_counts: Dict[str, int] = field(default_factory=dict)
    catalog_checksum: str = ""
    ordinal_space_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
