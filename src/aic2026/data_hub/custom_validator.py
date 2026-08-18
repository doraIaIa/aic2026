from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple

from aic2026.data_hub.custom_models import (
    CustomKeyframeRecord,
    CustomSpace,
    CustomValidationResult,
    QwenMissingRecord,
    QwenSemanticRecord,
)
from aic2026.data_hub.video_registry import VideoRegistry


_ABSOLUTE_PATH_REGEX = re.compile(r"^[a-zA-Z]:[\\/]|^\/|^\\")


class CustomKeyframeValidator:
    """Fail-closed validator for CUSTOM keyframes and Qwen semantic join."""

    def __init__(
        self,
        expected_keyframe_count: int = 116767,
        expected_video_count: int = 873,
        expected_qwen_valid_count: Optional[int] = None,
        expected_qwen_missing_count: Optional[int] = None,
        video_registry: Optional[VideoRegistry] = None,
    ) -> None:
        self.expected_keyframe_count = expected_keyframe_count
        self.expected_video_count = expected_video_count
        self.expected_qwen_valid_count = expected_qwen_valid_count
        self.expected_qwen_missing_count = expected_qwen_missing_count
        self.video_registry = video_registry

    def compute_custom_catalog_checksum(self, records: List[CustomKeyframeRecord]) -> str:
        """Compute deterministic SHA-256 hash across sorted canonical CUSTOM keyframes."""
        hasher = hashlib.sha256()
        # Sort deterministically by (video_ordinal, frame_idx)
        sorted_records = sorted(records, key=lambda r: (r.video_ordinal, r.frame_idx))
        for r in sorted_records:
            line = f"{r.keyframe_uid}:{r.video_id}:{r.video_ordinal}:{r.frame_idx}:{r.timestamp_ms}:{r.image_relpath}:{r.qwen_status}\n"
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def compute_qwen_canonical_checksum(self, records: List[QwenSemanticRecord]) -> str:
        """Compute deterministic SHA-256 hash across sorted canonical Qwen semantic observations."""
        hasher = hashlib.sha256()
        sorted_records = sorted(records, key=lambda r: (r.video_id, r.frame_idx))
        for r in sorted_records:
            line = f"{r.keyframe_uid}:{r.video_id}:{r.frame_idx}:{r.timestamp_ms}:{r.caption}\n"
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def validate(
        self,
        custom_records: List[CustomKeyframeRecord],
        qwen_records: Optional[List[QwenSemanticRecord]] = None,
        missing_records: Optional[List[QwenMissingRecord]] = None,
        custom_space: Optional[CustomSpace] = None,
    ) -> CustomValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        actual_custom_count = len(custom_records)
        if actual_custom_count != self.expected_keyframe_count:
            errors.append(
                f"CUSTOM_COUNT_MISMATCH: Expected {self.expected_keyframe_count}, got {actual_custom_count}"
            )

        seen_uids: Set[str] = set()
        seen_join_keys: Dict[Tuple[str, int], CustomKeyframeRecord] = {}
        covered_videos: Set[str] = set()

        for idx, r in enumerate(custom_records):
            # Check frame_space
            if r.frame_space != "CUSTOM":
                errors.append(f"INVALID_FRAME_SPACE: Record {idx} ({r.keyframe_uid}) has frame_space='{r.frame_space}', expected 'CUSTOM'")

            # Check duplicate UID
            if r.keyframe_uid in seen_uids:
                errors.append(f"DUPLICATE_KEYFRAME_UID: UID '{r.keyframe_uid}' appears multiple times")
            seen_uids.add(r.keyframe_uid)

            # Check join key (video_id, frame_idx)
            join_key = (r.video_id, r.frame_idx)
            if join_key in seen_join_keys:
                errors.append(f"DUPLICATE_VIDEO_FRAME: Duplicate (video_id, frame_idx) {join_key} in custom keyframes")
            seen_join_keys[join_key] = r
            covered_videos.add(r.video_id)

            # Validate against VideoRegistry if provided
            if self.video_registry is not None:
                v_meta = self.video_registry.get_video(r.video_id)
                if v_meta is None:
                    errors.append(f"UNKNOWN_VIDEO_ID: Keyframe '{r.keyframe_uid}' references unknown video '{r.video_id}'")
                else:
                    if r.video_ordinal != v_meta.ordinal:
                        errors.append(
                            f"ORDINAL_MISMATCH: Video '{r.video_id}' record has ordinal {r.video_ordinal}, expected {v_meta.ordinal}"
                        )
                    if r.ordinal_space_id != v_meta.ordinal_space_id:
                        errors.append(
                            f"ORDINAL_SPACE_MISMATCH: Video '{r.video_id}' has ordinal_space_id='{r.ordinal_space_id}', expected '{v_meta.ordinal_space_id}'"
                        )

            # Check image_relpath
            if not r.image_relpath or not r.image_relpath.strip():
                errors.append(f"EMPTY_IMAGE_RELPATH: Keyframe '{r.keyframe_uid}' has empty image_relpath")
            else:
                if _ABSOLUTE_PATH_REGEX.search(r.image_relpath):
                    errors.append(
                        f"ABSOLUTE_PATH_FORBIDDEN: Keyframe '{r.keyframe_uid}' image_relpath '{r.image_relpath}' is absolute"
                    )
                if ".." in r.image_relpath.split("/") or ".." in r.image_relpath.split("\\"):
                    errors.append(
                        f"PATH_TRAVERSAL_FORBIDDEN: Keyframe '{r.keyframe_uid}' image_relpath '{r.image_relpath}' contains '..'"
                    )

            # Validate frame_idx and timestamp_ms
            if r.frame_idx < 0:
                errors.append(f"NEGATIVE_FRAME_IDX: Keyframe '{r.keyframe_uid}' has frame_idx={r.frame_idx}")
            if r.timestamp_ms < 0:
                errors.append(f"NEGATIVE_TIMESTAMP: Keyframe '{r.keyframe_uid}' has timestamp_ms={r.timestamp_ms}")

        # Check covered video count
        actual_video_count = len(covered_videos)
        if actual_video_count != self.expected_video_count:
            errors.append(
                f"VIDEO_COVERAGE_MISMATCH: Expected {self.expected_video_count} videos, got {actual_video_count}"
            )

        # 2. Qwen semantics validation
        qwen_valid_count = 0
        qwen_joined_count = 0
        qwen_orphan_count = 0
        pts_mismatch_count = 0
        qwen_covered_videos: Set[str] = set()
        seen_qwen_keys: Set[Tuple[str, int]] = set()

        if qwen_records is not None:
            qwen_valid_count = len(qwen_records)
            for q in qwen_records:
                if q.frame_space != "CUSTOM":
                    errors.append(f"INVALID_QWEN_FRAME_SPACE: Record '{q.keyframe_uid}' has frame_space='{q.frame_space}'")

                q_key = (q.video_id, q.frame_idx)
                if q_key in seen_qwen_keys:
                    errors.append(f"DUPLICATE_QWEN_KEY: Duplicate Qwen join key {q_key}")
                seen_qwen_keys.add(q_key)
                qwen_covered_videos.add(q.video_id)

                if q_key in seen_join_keys:
                    qwen_joined_count += 1
                    c_rec = seen_join_keys[q_key]
                    if abs(q.raw_pts_time - c_rec.raw_pts_time) > 0.01:
                        pts_mismatch_count += 1
                        errors.append(
                            f"PTS_MISMATCH: Key {q_key} has Qwen pts={q.raw_pts_time} vs Custom pts={c_rec.raw_pts_time}"
                        )
                else:
                    qwen_orphan_count += 1
                    errors.append(f"ORPHAN_QWEN_RECORD: Qwen key {q_key} does not exist in custom keyframes")

            if self.expected_qwen_valid_count is not None and qwen_valid_count != self.expected_qwen_valid_count:
                errors.append(
                    f"QWEN_VALID_COUNT_MISMATCH: Expected {self.expected_qwen_valid_count}, got {qwen_valid_count}"
                )

        # 3. Missing records validation
        qwen_missing_count = len(missing_records) if missing_records is not None else 0
        if self.expected_qwen_missing_count is not None and qwen_missing_count != self.expected_qwen_missing_count:
            errors.append(
                f"QWEN_MISSING_COUNT_MISMATCH: Expected {self.expected_qwen_missing_count}, got {qwen_missing_count}"
            )

        # OK + MISSING total accounting check
        if qwen_records is not None and missing_records is not None:
            if qwen_valid_count + qwen_missing_count != actual_custom_count:
                errors.append(
                    f"ACCOUNTING_MISMATCH: Valid ({qwen_valid_count}) + Missing ({qwen_missing_count}) != Total ({actual_custom_count})"
                )

        custom_checksum = self.compute_custom_catalog_checksum(custom_records)
        qwen_checksum = self.compute_qwen_canonical_checksum(qwen_records) if qwen_records else ""

        if custom_space is not None:
            if custom_space.catalog_checksum and custom_space.catalog_checksum != custom_checksum:
                errors.append(
                    f"CHECKSUM_MISMATCH: CustomSpace checksum '{custom_space.catalog_checksum}' != computed '{custom_checksum}'"
                )
            if custom_space.keyframe_count != actual_custom_count:
                errors.append(
                    f"SPACE_KEYFRAME_COUNT_MISMATCH: CustomSpace count {custom_space.keyframe_count} != actual {actual_custom_count}"
                )

        return CustomValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            custom_keyframe_count=actual_custom_count,
            unique_keyframe_count=len(seen_uids),
            covered_video_count=actual_video_count,
            qwen_valid_count=qwen_valid_count,
            qwen_joined_count=qwen_joined_count,
            qwen_missing_count=qwen_missing_count,
            qwen_orphan_count=qwen_orphan_count,
            pts_mismatch_count=pts_mismatch_count,
            custom_catalog_checksum=custom_checksum,
            qwen_canonical_checksum=qwen_checksum,
        )
