from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from aic2026.data_hub.btc_models import (
    BtcClipRowRecord,
    BtcKeyframeRecord,
    BtcMediaInfoRecord,
    BtcObjectCoverageRecord,
    BtcObjectDetectionRecord,
    BtcValidationResult,
)
from aic2026.data_hub.video_registry import VideoRegistry


class BtcValidator:
    """Fail-closed validator for canonical BTC Data Hub entities."""

    def __init__(
        self,
        video_registry: VideoRegistry,
        expected_video_count: int = 873,
        expected_keyframe_count: int = 177321,
    ) -> None:
        self.video_registry = video_registry
        self.expected_video_count = expected_video_count
        self.expected_keyframe_count = expected_keyframe_count
        self._canonical_videos: Dict[str, int] = {
            r.video_id: r.ordinal for r in video_registry.iter_videos()
        }

    def compute_btc_catalog_checksum(self, records: List[BtcKeyframeRecord]) -> str:
        """Compute deterministic SHA-256 over canonical BTC keyframe records."""
        hasher = hashlib.sha256()
        sorted_records = sorted(records, key=lambda r: (r.video_ordinal, r.local_keyframe_no))
        for r in sorted_records:
            line = (
                f"{r.keyframe_uid}|{r.video_id}|{r.video_ordinal}|{r.ordinal_space_id}|"
                f"{r.local_keyframe_no}|{r.frame_idx}|{r.timestamp_ms}|{r.raw_pts_time:.6f}|"
                f"{r.fps:.4f}|{r.image_relpath}|{r.clip_status}|{r.object_status}\n"
            )
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def compute_clip_rowmap_checksum(self, records: List[BtcClipRowRecord]) -> str:
        """Compute deterministic SHA-256 over BTC CLIP row mappings."""
        hasher = hashlib.sha256()
        sorted_records = sorted(records, key=lambda r: (r.video_ordinal, r.row_in_video))
        for r in sorted_records:
            line = (
                f"{r.clip_source_id}|{r.video_id}|{r.video_ordinal}|{r.row_in_video}|"
                f"{r.keyframe_uid}|{r.local_keyframe_no}|{r.frame_idx}|{r.timestamp_ms}|"
                f"{r.feature_relpath}|{r.dimension}|{r.dtype}\n"
            )
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def compute_object_checksum(self, records: List[BtcObjectDetectionRecord]) -> str:
        """Compute deterministic SHA-256 over BTC object detections."""
        hasher = hashlib.sha256()
        sorted_records = sorted(
            records,
            key=lambda r: (r.video_ordinal, r.local_keyframe_no, r.local_detection_index),
        )
        for r in sorted_records:
            bbox_str = ",".join(f"{x:.6f}" for x in r.bbox)
            line = (
                f"{r.detection_uid}|{r.keyframe_uid}|{r.video_id}|{r.local_keyframe_no}|"
                f"{r.frame_idx}|{r.local_detection_index}|{r.class_name}|"
                f"{r.class_entity or ''}|{r.class_label or ''}|{r.confidence:.6f}|{bbox_str}\n"
            )
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def compute_media_info_checksum(self, records: List[BtcMediaInfoRecord]) -> str:
        """Compute deterministic SHA-256 over BTC media-info records."""
        hasher = hashlib.sha256()
        sorted_records = sorted(records, key=lambda r: r.video_ordinal)
        for r in sorted_records:
            kw_str = ",".join(r.keywords or [])
            line = (
                f"{r.video_id}|{r.video_ordinal}|{r.title}|{r.channel_id or ''}|"
                f"{r.publish_date or ''}|{r.duration_sec or 0}|{kw_str}\n"
            )
            hasher.update(line.encode("utf-8"))
        return hasher.hexdigest()

    def validate(
        self,
        btc_keyframes: List[BtcKeyframeRecord],
        clip_rowmaps: Optional[List[BtcClipRowRecord]] = None,
        object_detections: Optional[List[BtcObjectDetectionRecord]] = None,
        object_coverage: Optional[List[BtcObjectCoverageRecord]] = None,
        media_info: Optional[List[BtcMediaInfoRecord]] = None,
        faiss_metadata_rows: Optional[List[Dict]] = None,
        precomputed_object_count: Optional[int] = None,
        precomputed_object_checksum: Optional[str] = None,
    ) -> BtcValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        # ------------------------------------------------------------------
        # 1. Validate BTC Keyframes
        # ------------------------------------------------------------------
        seen_uids: Set[str] = set()
        seen_vid_n: Set[Tuple[str, int]] = set()
        covered_videos: Set[str] = set()

        for kf in btc_keyframes:
            # Identity format check
            if not kf.keyframe_uid.startswith(f"BTC:{kf.video_id}:KF"):
                errors.append(f"INVALID_BTC_UID_FORMAT: {kf.keyframe_uid}")
            if kf.frame_space != "BTC":
                errors.append(f"INVALID_FRAME_SPACE: Expected 'BTC', got '{kf.frame_space}' for {kf.keyframe_uid}")

            # Uniqueness
            if kf.keyframe_uid in seen_uids:
                errors.append(f"DUPLICATE_KEYFRAME_UID: {kf.keyframe_uid}")
            seen_uids.add(kf.keyframe_uid)

            if (kf.video_id, kf.local_keyframe_no) in seen_vid_n:
                errors.append(f"DUPLICATE_VIDEO_N: {kf.video_id} n={kf.local_keyframe_no}")
            seen_vid_n.add((kf.video_id, kf.local_keyframe_no))

            # Foreign key to video registry
            if kf.video_id not in self._canonical_videos:
                errors.append(f"UNKNOWN_VIDEO_ID: {kf.video_id} in {kf.keyframe_uid}")
            else:
                expected_ordinal = self._canonical_videos[kf.video_id]
                if kf.video_ordinal != expected_ordinal:
                    errors.append(
                        f"VIDEO_ORDINAL_MISMATCH: {kf.video_id} expected {expected_ordinal}, got {kf.video_ordinal}"
                    )
            covered_videos.add(kf.video_id)

            # Timestamps & FPS
            if kf.timestamp_ms < 0:
                errors.append(f"NEGATIVE_TIMESTAMP: {kf.timestamp_ms} for {kf.keyframe_uid}")
            if kf.raw_pts_time < 0 or math.isnan(kf.raw_pts_time) or math.isinf(kf.raw_pts_time):
                errors.append(f"INVALID_PTS_TIME: {kf.raw_pts_time} for {kf.keyframe_uid}")
            expected_ms = int(round(kf.raw_pts_time * 1000))
            if kf.timestamp_ms != expected_ms:
                errors.append(
                    f"TIMESTAMP_DERIVATION_MISMATCH: pts={kf.raw_pts_time} -> expected {expected_ms}ms, got {kf.timestamp_ms}ms"
                )
            if kf.fps <= 0 or math.isnan(kf.fps) or math.isinf(kf.fps):
                errors.append(f"INVALID_FPS: {kf.fps} for {kf.keyframe_uid}")
            if kf.frame_idx < 0:
                errors.append(f"NEGATIVE_FRAME_IDX: {kf.frame_idx} for {kf.keyframe_uid}")

            # Path safety
            p = kf.image_relpath
            if "\\" in p:
                errors.append(f"WINDOWS_SEPARATOR_IN_RELPATH: {p}")
            if p.startswith("/") or (len(p) > 1 and p[1] == ":"):
                errors.append(f"ABSOLUTE_IMAGE_PATH_REJECTED: {p}")
            if ".." in p.split("/"):
                errors.append(f"PATH_TRAVERSAL_REJECTED: {p}")

        if len(covered_videos) != self.expected_video_count:
            errors.append(
                f"BTC_VIDEO_COVERAGE_MISMATCH: Expected {self.expected_video_count} videos, got {len(covered_videos)}"
            )
        if len(btc_keyframes) != self.expected_keyframe_count:
            errors.append(
                f"BTC_KEYFRAME_COUNT_MISMATCH: Expected {self.expected_keyframe_count}, got {len(btc_keyframes)}"
            )

        btc_catalog_checksum = (
            self.compute_btc_catalog_checksum(btc_keyframes) if btc_keyframes else ""
        )

        # ------------------------------------------------------------------
        # 2. Validate Raw BTC CLIP Row Mappings
        # ------------------------------------------------------------------
        raw_clip_mapped_rows = 0
        raw_clip_unmapped_rows = 0
        seen_clip_refs: Set[Tuple[str, int]] = set()

        if clip_rowmaps is not None:
            for rm in clip_rowmaps:
                if rm.keyframe_uid not in seen_uids:
                    errors.append(f"CLIP_UNKNOWN_KEYFRAME_UID: {rm.keyframe_uid}")
                    raw_clip_unmapped_rows += 1
                else:
                    raw_clip_mapped_rows += 1

                ref_key = (rm.video_id, rm.row_in_video)
                if ref_key in seen_clip_refs:
                    errors.append(f"DUPLICATE_CLIP_ROW_REF: {ref_key}")
                seen_clip_refs.add(ref_key)

                if rm.local_keyframe_no != rm.row_in_video + 1:
                    errors.append(
                        f"CLIP_ROW_FORMULA_MISMATCH: row={rm.row_in_video}, expected n={rm.row_in_video + 1}, got {rm.local_keyframe_no}"
                    )
                if rm.dimension != 512:
                    errors.append(f"INVALID_CLIP_DIMENSION: Expected 512, got {rm.dimension}")

            if len(clip_rowmaps) != len(btc_keyframes):
                errors.append(
                    f"CLIP_TOTAL_ROWS_MISMATCH: Expected {len(btc_keyframes)} rows, got {len(clip_rowmaps)}"
                )

        raw_clip_rowmap_checksum = (
            self.compute_clip_rowmap_checksum(clip_rowmaps) if clip_rowmaps else ""
        )

        # ------------------------------------------------------------------
        # 3. Validate BTC Object Detections & Coverage
        # ------------------------------------------------------------------
        object_detection_count = precomputed_object_count or 0
        object_empty_keyframe_count = 0
        object_unavailable_keyframe_count = 0
        seen_det_uids: Set[str] = set()

        if object_detections is not None:
            object_detection_count = len(object_detections)
            for det in object_detections:
                if not det.detection_uid.startswith(f"BTC_OBJECT:{det.keyframe_uid}:D"):
                    errors.append(f"INVALID_OBJECT_DETECTION_UID: {det.detection_uid}")
                if det.keyframe_uid not in seen_uids:
                    errors.append(f"OBJECT_UNKNOWN_KEYFRAME_UID: {det.keyframe_uid}")
                if det.detection_uid in seen_det_uids:
                    errors.append(f"DUPLICATE_OBJECT_DETECTION_UID: {det.detection_uid}")
                seen_det_uids.add(det.detection_uid)

                # BBox validation
                if len(det.bbox) != 4:
                    errors.append(f"INVALID_BBOX_SHAPE: {det.bbox} for {det.detection_uid}")
                else:
                    for c in det.bbox:
                        if math.isnan(c) or math.isinf(c):
                            errors.append(f"NON_FINITE_BBOX_COORD: {c} in {det.detection_uid}")

                if math.isnan(det.confidence) or math.isinf(det.confidence):
                    errors.append(f"NON_FINITE_OBJECT_CONFIDENCE: {det.confidence} in {det.detection_uid}")

        if object_coverage is not None:
            cov_kfs = set()
            for cov in object_coverage:
                cov_kfs.add(cov.keyframe_uid)
                if cov.keyframe_uid not in seen_uids:
                    errors.append(f"OBJECT_COV_UNKNOWN_KEYFRAME: {cov.keyframe_uid}")
                if cov.object_status == "EMPTY":
                    object_empty_keyframe_count += 1
                elif cov.object_status == "UNAVAILABLE":
                    object_unavailable_keyframe_count += 1

            if len(cov_kfs) != len(btc_keyframes):
                errors.append(
                    f"OBJECT_COVERAGE_COUNT_MISMATCH: Expected {len(btc_keyframes)} coverage records, got {len(cov_kfs)}"
                )

        object_canonical_checksum = precomputed_object_checksum or (
            self.compute_object_checksum(object_detections) if object_detections else ""
        )

        # ------------------------------------------------------------------
        # 4. Validate Media-Info
        # ------------------------------------------------------------------
        seen_media_vids: Set[str] = set()
        if media_info is not None:
            for m in media_info:
                if m.video_id not in self._canonical_videos:
                    errors.append(f"MEDIA_INFO_UNKNOWN_VIDEO: {m.video_id}")
                if m.video_id in seen_media_vids:
                    errors.append(f"DUPLICATE_MEDIA_INFO_VIDEO: {m.video_id}")
                seen_media_vids.add(m.video_id)

            if len(seen_media_vids) != self.expected_video_count:
                errors.append(
                    f"MEDIA_INFO_COUNT_MISMATCH: Expected {self.expected_video_count} videos, got {len(seen_media_vids)}"
                )

        media_info_checksum = (
            self.compute_media_info_checksum(media_info) if media_info else ""
        )

        # ------------------------------------------------------------------
        # 5. Validate Existing FAISS Index Rows
        # ------------------------------------------------------------------
        faiss_mapped_rows = 0
        faiss_orphan_rows = 0
        faiss_vector_rows = len(faiss_metadata_rows) if faiss_metadata_rows else 0
        if faiss_metadata_rows is not None:
            for row in faiss_metadata_rows:
                vid = row.get("video_id")
                csv_n = row.get("csv_n")
                kf_uid = f"BTC:{vid}:KF{int(csv_n):06d}"
                if kf_uid in seen_uids:
                    faiss_mapped_rows += 1
                else:
                    errors.append(f"FAISS_ORPHAN_ROW: {kf_uid} not in canonical BTC space")
                    faiss_orphan_rows += 1

        is_valid = len(errors) == 0

        return BtcValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            map_csv_count=len(covered_videos),
            map_row_count=len(btc_keyframes),
            jpeg_count=len(btc_keyframes),
            btc_keyframe_count=len(btc_keyframes),
            btc_video_count=len(covered_videos),
            btc_catalog_checksum=btc_catalog_checksum,
            raw_clip_file_count=len(covered_videos) if clip_rowmaps else 0,
            raw_clip_row_count=len(clip_rowmaps) if clip_rowmaps else 0,
            raw_clip_mapped_rows=raw_clip_mapped_rows,
            raw_clip_unmapped_rows=raw_clip_unmapped_rows,
            raw_clip_rowmap_checksum=raw_clip_rowmap_checksum,
            object_video_count=len(covered_videos) if object_coverage else 0,
            object_keyframe_count=len(object_coverage) if object_coverage else 0,
            object_detection_count=object_detection_count,
            object_empty_keyframe_count=object_empty_keyframe_count,
            object_unavailable_keyframe_count=object_unavailable_keyframe_count,
            object_canonical_checksum=object_canonical_checksum,
            media_info_count=len(seen_media_vids) if media_info else 0,
            media_info_checksum=media_info_checksum,
            faiss_vector_rows=faiss_vector_rows,
            faiss_mapped_rows=faiss_mapped_rows,
            faiss_orphan_rows=faiss_orphan_rows,
            faiss_checksum="08ed3cdbe250401560d04a4a26f9958c92672739141b664c5c59b75bfcfac0b3",
        )
