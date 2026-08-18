from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from aic2026.data_hub.asr_ocr_models import (
    AsrOcrValidationResult,
    AsrSegmentRecord,
    AsrVideoCoverageRecord,
    OcrBgeRowmapRecord,
    OcrItemRecord,
    OcrKeyframeCoverageRecord,
)
from aic2026.data_hub.custom_registry import CustomKeyframeRegistry
from aic2026.data_hub.video_registry import VideoRegistry


class AsrOcrValidator:
    """Fail-closed validator for canonical ASR intervals, OCR text evidence, and BGE-M3 row mappings."""

    def __init__(
        self,
        expected_video_count: int = 873,
        expected_asr_segment_count: int = 107540,
        expected_asr_with_segments_count: int = 859,
        expected_asr_zero_segment_count: int = 14,
        expected_ocr_keyframe_count: int = 116767,
        video_registry: Optional[VideoRegistry] = None,
        custom_registry: Optional[CustomKeyframeRegistry] = None,
    ) -> None:
        self.expected_video_count = expected_video_count
        self.expected_asr_segment_count = expected_asr_segment_count
        self.expected_asr_with_segments_count = expected_asr_with_segments_count
        self.expected_asr_zero_segment_count = expected_asr_zero_segment_count
        self.expected_ocr_keyframe_count = expected_ocr_keyframe_count
        self.video_registry = video_registry
        self.custom_registry = custom_registry

    def compute_asr_canonical_checksum(self, segments: List[AsrSegmentRecord]) -> str:
        """Compute deterministic SHA-256 hash across sorted canonical ASR segments."""
        hasher = hashlib.sha256()
        sorted_segments = sorted(segments, key=lambda s: (s.video_ordinal, s.start_ms, s.end_ms, s.source_segment_id))
        for s in sorted_segments:
            line = f"{s.segment_uid}:{s.video_id}:{s.video_ordinal}:{s.start_ms}:{s.end_ms}:{s.text_raw}\n"
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def compute_ocr_canonical_checksum(self, keyframes: List[OcrKeyframeCoverageRecord], items: Optional[List[OcrItemRecord]] = None) -> str:
        """Compute deterministic SHA-256 hash across sorted OCR keyframe coverage and items."""
        hasher = hashlib.sha256()
        sorted_kf = sorted(keyframes, key=lambda k: (k.video_ordinal, k.frame_idx))
        for k in sorted_kf:
            line = f"{k.keyframe_uid}:{k.video_id}:{k.video_ordinal}:{k.frame_idx}:{k.item_count}\n"
            hasher.update(line.encode("utf-8"))
        if items:
            sorted_items = sorted(items, key=lambda it: (it.video_ordinal, it.frame_idx, it.local_text_index))
            for it in sorted_items:
                line = f"{it.ocr_uid}:{it.keyframe_uid}:{it.local_text_index}:{it.text_raw}:{it.ocr_confidence}\n"
                hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def compute_bge_rowmap_checksum(self, rowmaps: List[OcrBgeRowmapRecord]) -> str:
        """Compute deterministic SHA-256 hash across sorted BGE vector row mappings."""
        hasher = hashlib.sha256()
        sorted_rm = sorted(rowmaps, key=lambda r: (r.shard_id, r.row_in_shard))
        for r in sorted_rm:
            line = f"{r.shard_id}:{r.row_in_shard}:{r.ocr_uid}:{r.keyframe_uid}\n"
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def validate_bge_shards_on_disk(
        self,
        dense_dir: Path,
        expected_shard_count: int = 10,
        expected_dim: int = 1024,
    ) -> List[str]:
        """Validate actual .npy and .json shard files on disk."""
        errors: List[str] = []
        dense_dir = Path(dense_dir)
        if not dense_dir.exists():
            return [f"DENSE_DIR_NOT_FOUND: {dense_dir}"]

        import json
        import numpy as np
        total_meta = 0
        total_vec = 0

        for shard_idx in range(expected_shard_count):
            shard_str = f"{shard_idx:03d}"
            npy_path = dense_dir / f"embeddings_shard_{shard_str}.npy"
            json_path = dense_dir / f"metadata_shard_{shard_str}.json"

            if not npy_path.exists():
                errors.append(f"MISSING_EMBEDDING_SHARD: {npy_path}")
                continue
            if not json_path.exists():
                errors.append(f"MISSING_METADATA_SHARD: {json_path}")
                continue

            arr = None
            try:
                arr = np.load(npy_path, mmap_mode="r")
                if len(arr.shape) != 2 or arr.shape[1] != expected_dim:
                    errors.append(f"INVALID_SHARD_SHAPE: {npy_path} has shape {arr.shape}, expected (*, {expected_dim})")
                total_vec += arr.shape[0]
            except Exception as exc:
                errors.append(f"CORRUPT_EMBEDDING_SHARD: {npy_path} error: {exc}")

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    rows = json.load(f)
                total_meta += len(rows)
                if arr is not None and len(rows) != arr.shape[0]:
                    errors.append(f"SHARD_ROW_COUNT_MISMATCH: Shard {shard_str} has {len(rows)} metadata rows != {arr.shape[0]} vector rows")
            except Exception as exc:
                errors.append(f"CORRUPT_METADATA_SHARD: {json_path} error: {exc}")

        return errors

    def validate(
        self,
        asr_coverage: List[AsrVideoCoverageRecord],
        asr_segments: List[AsrSegmentRecord],
        ocr_keyframes: List[OcrKeyframeCoverageRecord],
        ocr_items: Optional[List[OcrItemRecord]] = None,
        bge_rowmaps: Optional[List[OcrBgeRowmapRecord]] = None,
    ) -> AsrOcrValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        # ------------------------------------------------------------------
        # 1. ASR Validation
        # ------------------------------------------------------------------
        asr_video_count = len(asr_coverage)
        if asr_video_count != self.expected_video_count:
            errors.append(
                f"ASR_VIDEO_COUNT_MISMATCH: Expected {self.expected_video_count} videos in coverage, got {asr_video_count}"
            )

        seen_asr_video_ids: Set[str] = set()
        asr_with_segments = 0
        asr_zero_segments = 0
        per_video_segment_expected: Dict[str, int] = {}

        for v_cov in asr_coverage:
            if v_cov.video_id in seen_asr_video_ids:
                errors.append(f"DUPLICATE_ASR_VIDEO_ID: Video '{v_cov.video_id}' duplicated in coverage manifest")
            seen_asr_video_ids.add(v_cov.video_id)
            per_video_segment_expected[v_cov.video_id] = v_cov.segment_count

            if v_cov.segment_count > 0:
                asr_with_segments += 1
                if v_cov.asr_status != "HAS_SEGMENTS":
                    errors.append(f"INVALID_ASR_STATUS: Video '{v_cov.video_id}' has {v_cov.segment_count} segments but status='{v_cov.asr_status}'")
            else:
                asr_zero_segments += 1
                if v_cov.asr_status != "ZERO_ASR_SEGMENTS":
                    errors.append(f"INVALID_ASR_STATUS: Video '{v_cov.video_id}' has 0 segments but status='{v_cov.asr_status}'")

            if self.video_registry is not None:
                v_meta = self.video_registry.get_video(v_cov.video_id)
                if v_meta is None:
                    errors.append(f"UNKNOWN_ASR_VIDEO_ID: Video '{v_cov.video_id}' not found in canonical VideoRegistry")
                else:
                    if v_cov.video_ordinal != v_meta.ordinal:
                        errors.append(f"ASR_ORDINAL_MISMATCH: Video '{v_cov.video_id}' has ordinal {v_cov.video_ordinal}, expected {v_meta.ordinal}")

        if asr_with_segments != self.expected_asr_with_segments_count:
            errors.append(f"ASR_WITH_SEGMENTS_COUNT_MISMATCH: Expected {self.expected_asr_with_segments_count}, got {asr_with_segments}")

        if asr_zero_segments != self.expected_asr_zero_segment_count:
            errors.append(f"ASR_ZERO_SEGMENT_COUNT_MISMATCH: Expected {self.expected_asr_zero_segment_count}, got {asr_zero_segments}")

        # ASR Segments
        asr_segment_count = len(asr_segments)
        if asr_segment_count != self.expected_asr_segment_count:
            errors.append(f"ASR_SEGMENT_COUNT_MISMATCH: Expected {self.expected_asr_segment_count}, got {asr_segment_count}")

        seen_segment_uids: Set[str] = set()
        seen_source_segment_ids: Set[Tuple[str, str]] = set()
        actual_per_video_segments: Dict[str, int] = {vid: 0 for vid in seen_asr_video_ids}
        asr_invalid_intervals = 0

        for s in asr_segments:
            if s.segment_uid in seen_segment_uids:
                errors.append(f"DUPLICATE_SEGMENT_UID: Segment UID '{s.segment_uid}' appears multiple times")
            seen_segment_uids.add(s.segment_uid)

            src_key = (s.video_id, s.source_segment_id)
            if src_key in seen_source_segment_ids:
                errors.append(f"DUPLICATE_SOURCE_SEGMENT_ID: Source segment {src_key} appears multiple times")
            seen_source_segment_ids.add(src_key)

            if s.video_id not in seen_asr_video_ids:
                errors.append(f"SEGMENT_UNKNOWN_VIDEO: Segment '{s.segment_uid}' belongs to unknown video '{s.video_id}'")
            else:
                actual_per_video_segments[s.video_id] += 1

            if s.start_ms < 0:
                asr_invalid_intervals += 1
                errors.append(f"NEGATIVE_ASR_TIMESTAMP: Segment '{s.segment_uid}' has start_ms={s.start_ms}")
            if s.end_ms < s.start_ms:
                asr_invalid_intervals += 1
                errors.append(f"INVALID_ASR_INTERVAL: Segment '{s.segment_uid}' has end_ms ({s.end_ms}) < start_ms ({s.start_ms})")

            if not s.text_raw or not s.text_raw.strip():
                errors.append(f"EMPTY_ASR_TRANSCRIPT: Segment '{s.segment_uid}' has empty text_raw")

        for vid, expected_count in per_video_segment_expected.items():
            actual_count = actual_per_video_segments.get(vid, 0)
            if actual_count != expected_count:
                errors.append(f"VIDEO_SEGMENT_COUNT_MISMATCH: Video '{vid}' expected {expected_count} segments, found {actual_count}")

        asr_checksum = self.compute_asr_canonical_checksum(asr_segments)

        # ------------------------------------------------------------------
        # 2. OCR Keyframe Coverage Validation
        # ------------------------------------------------------------------
        ocr_keyframe_count = len(ocr_keyframes)
        if ocr_keyframe_count != self.expected_ocr_keyframe_count:
            errors.append(f"OCR_KEYFRAME_COUNT_MISMATCH: Expected {self.expected_ocr_keyframe_count}, got {ocr_keyframe_count}")

        seen_ocr_kf_uids: Set[str] = set()
        ocr_covered_videos: Set[str] = set()

        for k in ocr_keyframes:
            if k.keyframe_uid in seen_ocr_kf_uids:
                errors.append(f"DUPLICATE_OCR_KEYFRAME_UID: Keyframe '{k.keyframe_uid}' duplicated in OCR coverage")
            seen_ocr_kf_uids.add(k.keyframe_uid)
            ocr_covered_videos.add(k.video_id)

            if self.custom_registry is not None:
                c_meta = self.custom_registry.get_custom_keyframe(k.keyframe_uid)
                if c_meta is None:
                    errors.append(f"UNKNOWN_CUSTOM_KEYFRAME: OCR keyframe '{k.keyframe_uid}' not found in CustomKeyframeRegistry")
                else:
                    if k.frame_idx != c_meta.frame_idx:
                        errors.append(f"OCR_FRAME_IDX_MISMATCH: Keyframe '{k.keyframe_uid}' has frame_idx={k.frame_idx}, expected {c_meta.frame_idx}")

        if len(ocr_covered_videos) != self.expected_video_count:
            errors.append(f"OCR_VIDEO_COVERAGE_MISMATCH: Expected {self.expected_video_count} videos, got {len(ocr_covered_videos)}")

        # ------------------------------------------------------------------
        # 3. OCR Items Validation (if present)
        # ------------------------------------------------------------------
        ocr_item_count = 0
        ocr_raw_item_count = 0
        ocr_dense_item_count = 0
        ocr_raw_without_dense_count = 0
        ocr_conf_low = 0
        ocr_conf_high = 0
        seen_ocr_uids: Set[str] = set()

        if ocr_items:
            ocr_item_count = len(ocr_items)
            ocr_raw_item_count = len(ocr_items)
            for it in ocr_items:
                if it.ocr_uid in seen_ocr_uids:
                    errors.append(f"DUPLICATE_OCR_UID: OCR UID '{it.ocr_uid}' appears multiple times")
                seen_ocr_uids.add(it.ocr_uid)

                if it.keyframe_uid not in seen_ocr_kf_uids:
                    errors.append(f"OCR_ITEM_UNKNOWN_KEYFRAME: OCR item '{it.ocr_uid}' references unknown keyframe '{it.keyframe_uid}'")

                if it.dense_embedding_ref is not None:
                    ocr_dense_item_count += 1
                else:
                    ocr_raw_without_dense_count += 1

                if it.ocr_confidence is not None:
                    if it.ocr_confidence < 0.5:
                        ocr_conf_low += 1
                    else:
                        ocr_conf_high += 1

                if it.bbox is not None:
                    if not isinstance(it.bbox, list) or len(it.bbox) != 4:
                        errors.append(f"INVALID_BBOX_SHAPE: Item '{it.ocr_uid}' has invalid bbox: {it.bbox}")
                    else:
                        coords: List[float] = []
                        for elem in it.bbox:
                            if isinstance(elem, (list, tuple)):
                                coords.extend(elem)
                            elif isinstance(elem, (int, float)):
                                coords.append(float(elem))
                        if any(math.isnan(x) or math.isinf(x) for x in coords):
                            errors.append(f"NON_FINITE_BBOX: Item '{it.ocr_uid}' has non-finite bbox coordinates: {it.bbox}")

        ocr_checksum = self.compute_ocr_canonical_checksum(ocr_keyframes, ocr_items)

        # ------------------------------------------------------------------
        # 4. OCR BGE Rowmap Validation (if present)
        # ------------------------------------------------------------------
        bge_vector_row_count = 0
        bge_mapped_row_count = 0
        bge_unmapped_row_count = 0
        seen_rowmap_slots: Set[Tuple[str, int]] = set()

        if bge_rowmaps:
            bge_vector_row_count = len(bge_rowmaps)
            for rm in bge_rowmaps:
                slot = (rm.shard_id, rm.row_in_shard)
                if slot in seen_rowmap_slots:
                    errors.append(f"DUPLICATE_BGE_SLOT: Shard slot {slot} appears multiple times")
                seen_rowmap_slots.add(slot)

                if rm.keyframe_uid not in seen_ocr_kf_uids:
                    bge_unmapped_row_count += 1
                    errors.append(f"BGE_UNKNOWN_KEYFRAME: BGE row {slot} references unknown keyframe '{rm.keyframe_uid}'")
                else:
                    bge_mapped_row_count += 1

        bge_checksum = self.compute_bge_rowmap_checksum(bge_rowmaps) if bge_rowmaps else ""

        return AsrOcrValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            asr_video_count=asr_video_count,
            asr_segment_count=asr_segment_count,
            asr_videos_with_segments=asr_with_segments,
            asr_zero_segment_videos=asr_zero_segments,
            asr_invalid_intervals=asr_invalid_intervals,
            asr_canonical_checksum=asr_checksum,
            ocr_keyframe_count=ocr_keyframe_count,
            ocr_covered_videos=len(ocr_covered_videos),
            ocr_item_count=ocr_item_count,
            ocr_raw_item_count=ocr_raw_item_count,
            ocr_dense_item_count=ocr_dense_item_count,
            ocr_dense_mapped_count=bge_mapped_row_count if bge_rowmaps else ocr_dense_item_count,
            ocr_raw_without_dense_count=ocr_raw_without_dense_count,
            ocr_confidence_low_count=ocr_conf_low,
            ocr_confidence_high_count=ocr_conf_high,
            ocr_canonical_checksum=ocr_checksum,
            bge_vector_row_count=bge_vector_row_count,
            bge_metadata_row_count=bge_vector_row_count,
            bge_mapped_row_count=bge_mapped_row_count,
            bge_unmapped_row_count=bge_unmapped_row_count,
            bge_rowmap_checksum=bge_checksum,
        )
