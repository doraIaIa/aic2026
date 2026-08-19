from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TaxonomyNodeRecord:
    """Canonical flat graph taxonomy node."""

    branch_id: str
    branch_type: str  # 'PROGRAM' | 'SUBJECT' | 'TOPIC' | 'FACET'
    label_vi: str
    label_en: str
    parent_ids: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    requires_region_index: bool = False
    active: bool = True
    schema_version: str = "v1"
    source_id: str = "taxonomy_authority_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaxonomyNodeRecord:
        return cls(
            branch_id=data["branch_id"],
            branch_type=data["branch_type"],
            label_vi=data["label_vi"],
            label_en=data["label_en"],
            parent_ids=data.get("parent_ids", []),
            aliases=data.get("aliases", []),
            requires_region_index=bool(data.get("requires_region_index", False)),
            active=bool(data.get("active", True)),
            schema_version=data.get("schema_version", "v1"),
            source_id=data.get("source_id", "taxonomy_authority_v1"),
        )


@dataclass(frozen=True)
class VideoMembershipRecord:
    """Mapping between a canonical video and a taxonomy node."""

    membership_id: str  # '{video_id}#{branch_id}'
    video_id: str
    branch_id: str
    membership_type: str  # 'PRIMARY_PROGRAM' | 'SUBJECT' | 'TOPIC'
    status: str  # 'VERIFIED' | 'INFERRED' | 'OUTLIER'
    confidence: Optional[float] = None
    score_type: Optional[str] = "heuristic"
    evidence: Optional[str] = None
    prune_override: Optional[str] = None
    schema_version: str = "v1"
    source_id: str = "taxonomy_authority_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VideoMembershipRecord:
        return cls(
            membership_id=data["membership_id"],
            video_id=data["video_id"],
            branch_id=data["branch_id"],
            membership_type=data["membership_type"],
            status=data["status"],
            confidence=float(data["confidence"]) if data.get("confidence") is not None else None,
            score_type=data.get("score_type", "heuristic"),
            evidence=data.get("evidence"),
            prune_override=data.get("prune_override"),
            schema_version=data.get("schema_version", "v1"),
            source_id=data.get("source_id", "taxonomy_authority_v1"),
        )


@dataclass(frozen=True)
class TaxonomySpace:
    """Metadata describing the taxonomy hierarchy and build statistics."""

    taxonomy_id: str
    schema_version: str
    node_count: int
    membership_count: int
    program_counts: Dict[str, int]
    status_counts: Dict[str, int]
    checksum: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaxonomySpace:
        return cls(
            taxonomy_id=data["taxonomy_id"],
            schema_version=data.get("schema_version", "v1"),
            node_count=int(data["node_count"]),
            membership_count=int(data["membership_count"]),
            program_counts=data.get("program_counts", {}),
            status_counts=data.get("status_counts", {}),
            checksum=data.get("checksum", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )
