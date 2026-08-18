from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, List, Optional, Set

from aic2026.data_hub.models import ValidationResult, VideoRecord, VideoSpace


# Frozen canonical series universe expected for AIC 2026 873-video dataset
EXPECTED_SERIES_COUNTS_873: Dict[str, int] = {
    "L21": 29,
    "L22": 31,
    "L23": 25,
    "L24": 43,
    "L25": 88,
    "L26": 498,
    "L27": 16,
    "L28": 24,
    "L29": 23,
    "L30": 96,
}

_VIDEO_ID_REGEX = re.compile(r"^L(\d{2})_V(\d{3})$")
_ABSOLUTE_PATH_REGEX = re.compile(r"^[a-zA-Z]:[\\/]|^\/|^\\")


class VideoRegistryValidator:
    """Fail-closed validator for the canonical Video Registry and VideoSpace."""

    def __init__(
        self,
        expected_count: int = 873,
        expected_series_counts: Optional[Dict[str, int]] = None,
        expected_ordinal_space_id: str = "v1_natural_series_video",
    ) -> None:
        self.expected_count = expected_count
        self.expected_series_counts = (
            expected_series_counts
            if expected_series_counts is not None
            else (EXPECTED_SERIES_COUNTS_873 if expected_count == 873 else None)
        )
        self.expected_ordinal_space_id = expected_ordinal_space_id

    def compute_catalog_checksum(self, records: List[VideoRecord]) -> str:
        """Compute deterministic SHA-256 hash across all canonical video lines."""
        hasher = hashlib.sha256()
        # Sort by ordinal to ensure deterministic ordering
        sorted_records = sorted(records, key=lambda r: r.ordinal)
        for r in sorted_records:
            # Deterministic canonical line representation
            line = f"{r.ordinal}:{r.video_id}:{r.series}:{r.source_relpath}:{r.duration_ms}:{r.ordinal_space_id}\n"
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def validate(
        self,
        records: List[VideoRecord],
        video_space: Optional[VideoSpace] = None,
    ) -> ValidationResult:
        """Validate a list of VideoRecords against all fail-closed invariants."""
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Video count validation
        actual_count = len(records)
        if actual_count != self.expected_count:
            errors.append(
                f"COUNT_MISMATCH: Expected {self.expected_count} videos, got {actual_count}"
            )

        seen_video_ids: Set[str] = set()
        seen_ordinals: Set[int] = set()
        seen_relpaths: Set[str] = set()
        series_counts: Dict[str, int] = {}
        ordinal_space_ids: Set[str] = set()

        for idx, r in enumerate(records):
            # Check for duplicate video_id
            if r.video_id in seen_video_ids:
                errors.append(f"DUPLICATE_VIDEO_ID: Video ID '{r.video_id}' appears multiple times (record {idx})")
            seen_video_ids.add(r.video_id)

            # Check video_id format
            match = _VIDEO_ID_REGEX.match(r.video_id)
            if not match:
                errors.append(f"MALFORMED_VIDEO_ID: '{r.video_id}' does not match expected format 'Lxx_Vxxx'")
            else:
                expected_series = f"L{match.group(1)}"
                if r.series != expected_series:
                    errors.append(
                        f"SERIES_MISMATCH: Record '{r.video_id}' has series='{r.series}', expected '{expected_series}'"
                    )

            # Accumulate series counts
            series_counts[r.series] = series_counts.get(r.series, 0) + 1

            # Check duplicate ordinal
            if r.ordinal in seen_ordinals:
                errors.append(f"DUPLICATE_ORDINAL: Ordinal {r.ordinal} assigned to multiple videos (record {idx}: {r.video_id})")
            seen_ordinals.add(r.ordinal)

            # Check source_relpath
            if not r.source_relpath or not r.source_relpath.strip():
                errors.append(f"EMPTY_SOURCE_RELPATH: Video '{r.video_id}' has empty source_relpath")
            else:
                # Check absolute path
                if _ABSOLUTE_PATH_REGEX.search(r.source_relpath):
                    errors.append(
                        f"ABSOLUTE_PATH_FORBIDDEN: Video '{r.video_id}' source_relpath '{r.source_relpath}' is absolute"
                    )
                # Check path traversal
                if ".." in r.source_relpath.split("/") or ".." in r.source_relpath.split("\\"):
                    errors.append(
                        f"PATH_TRAVERSAL_FORBIDDEN: Video '{r.video_id}' source_relpath '{r.source_relpath}' contains '..'"
                    )

            # Check duplicate relpath
            if r.source_relpath in seen_relpaths:
                errors.append(
                    f"DUPLICATE_SOURCE_RELPATH: source_relpath '{r.source_relpath}' used by multiple videos ({r.video_id})"
                )
            seen_relpaths.add(r.source_relpath)

            # Check ordinal_space_id
            ordinal_space_ids.add(r.ordinal_space_id)

        # 2. Ordinal sequence validation
        ord_min: Optional[int] = None
        ord_max: Optional[int] = None
        if seen_ordinals:
            ord_min = min(seen_ordinals)
            ord_max = max(seen_ordinals)
            expected_ordinals = set(range(actual_count))
            if seen_ordinals != expected_ordinals:
                missing = expected_ordinals - seen_ordinals
                extra = seen_ordinals - expected_ordinals
                if missing:
                    errors.append(f"ORDINAL_GAP: Missing ordinals {sorted(missing)[:10]}")
                if extra:
                    errors.append(f"ORDINAL_OUT_OF_RANGE: Extra ordinals {sorted(extra)[:10]}")

        # 3. Ordinal space ID consistency
        if len(ordinal_space_ids) > 1:
            errors.append(f"INCONSISTENT_ORDINAL_SPACE: Multiple ordinal_space_ids found: {sorted(ordinal_space_ids)}")
        elif ordinal_space_ids and self.expected_ordinal_space_id:
            found_space = next(iter(ordinal_space_ids))
            if found_space != self.expected_ordinal_space_id:
                errors.append(
                    f"ORDINAL_SPACE_MISMATCH: Expected space '{self.expected_ordinal_space_id}', found '{found_space}'"
                )

        # 4. Series count validation
        if self.expected_series_counts is not None:
            if series_counts != self.expected_series_counts:
                for s, exp_c in self.expected_series_counts.items():
                    act_c = series_counts.get(s, 0)
                    if act_c != exp_c:
                        errors.append(f"SERIES_COUNT_MISMATCH: Series {s} expected {exp_c}, got {act_c}")
                for s, act_c in series_counts.items():
                    if s not in self.expected_series_counts:
                        errors.append(f"UNEXPECTED_SERIES: Series {s} not in expected universe (count={act_c})")

        # 5. Catalog Checksum
        computed_checksum = self.compute_catalog_checksum(records)
        if video_space is not None:
            if video_space.catalog_checksum and video_space.catalog_checksum != computed_checksum:
                errors.append(
                    f"CHECKSUM_MISMATCH: VideoSpace checksum '{video_space.catalog_checksum}' != computed '{computed_checksum}'"
                )
            if video_space.video_count != actual_count:
                errors.append(
                    f"SPACE_COUNT_MISMATCH: VideoSpace count {video_space.video_count} != actual records {actual_count}"
                )

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            video_count=actual_count,
            unique_video_count=len(seen_video_ids),
            ordinal_min=ord_min,
            ordinal_max=ord_max,
            series_counts=series_counts,
            catalog_checksum=computed_checksum,
            ordinal_space_id=next(iter(ordinal_space_ids)) if ordinal_space_ids else "",
        )
