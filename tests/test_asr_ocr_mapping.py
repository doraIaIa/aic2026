from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from aic2026.data_hub.asr_ocr_builder import (
    AsrOcrCatalogBuilder,
    normalize_canonical_text,
)
from aic2026.data_hub.asr_ocr_models import (
    AsrSegmentRecord,
    AsrVideoCoverageRecord,
    OcrBgeRowmapRecord,
    OcrItemRecord,
    OcrKeyframeCoverageRecord,
)
from aic2026.data_hub.asr_ocr_registry import AsrOcrRegistry
from aic2026.data_hub.asr_ocr_validator import AsrOcrValidator
from aic2026.data_hub.custom_models import CustomKeyframeRecord, CustomSpace
from aic2026.data_hub.custom_registry import CustomKeyframeRegistry
from aic2026.data_hub.models import VideoRecord, VideoSpace
from aic2026.data_hub.video_registry import VideoRegistry


@pytest.fixture
def mock_video_registry() -> VideoRegistry:
    v1 = VideoRecord(
        video_id="L21_V001",
        ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        series="L21",
        source_relpath="data_extracted/video/L21_V001.mp4",
        duration_ms=60000,
        fps=25.0,
    )
    v2 = VideoRecord(
        video_id="L24_V008",
        ordinal=1,
        ordinal_space_id="v1_natural_series_video",
        series="L24",
        source_relpath="data_extracted/video/L24_V008.mp4",
        duration_ms=45000,
        fps=25.0,
    )
    space = VideoSpace(
        video_space_id="v1_natural_series_video",
        schema_version="v1",
        video_count=2,
        ordering_rule="natural_sort_series_video_asc",
        catalog_checksum="dummy_checksum_video",
        created_at="2026-08-18T00:00:00Z",
    )
    return VideoRegistry(records=[v1, v2], video_space=space)


@pytest.fixture
def mock_custom_registry(mock_video_registry: VideoRegistry) -> CustomKeyframeRegistry:
    kf1 = CustomKeyframeRecord(
        keyframe_uid="CUSTOM:L21_V001:F15",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        frame_idx=15,
        timestamp_ms=500,
        raw_pts_time=0.5,
        shot_id=0,
        cluster_id=0,
        embedding_index=0,
        source_keyframe_id=0,
        file_name="000001.jpg",
        image_relpath="output/keyframes/L21_V001/000001.jpg",
    )
    kf2 = CustomKeyframeRecord(
        keyframe_uid="CUSTOM:L24_V008:F30",
        video_id="L24_V008",
        video_ordinal=1,
        ordinal_space_id="v1_natural_series_video",
        frame_idx=30,
        timestamp_ms=1000,
        raw_pts_time=1.0,
        shot_id=0,
        cluster_id=0,
        embedding_index=0,
        source_keyframe_id=0,
        file_name="000001.jpg",
        image_relpath="output/keyframes/L24_V008/000001.jpg",
    )
    space = CustomSpace(
        custom_space_id="custom_keyframes_v1",
        frame_space="CUSTOM",
        schema_version="v1",
        keyframe_count=2,
        video_count=2,
        identity_rule="CUSTOM:{video_id}:F{frame_idx}",
        source_checksum="",
        catalog_checksum="dummy_checksum_custom",
        created_at="2026-08-18T00:00:00Z",
    )
    return CustomKeyframeRegistry(
        custom_records=[kf1, kf2],
        qwen_records=[],
        missing_records=[],
        custom_space=space,
    )


# ----------------------------------------------------------------------
# 1. ASR Unit Tests
# ----------------------------------------------------------------------
def test_text_normalization():
    raw = "  Chào   mừng \t quý   vị  \n "
    norm = normalize_canonical_text(raw)
    assert norm == "Chào mừng quý vị"


def test_asr_segment_namespaced_uid_and_time_derivation():
    start_sec = 4.43
    end_sec = 8.23
    start_ms = int(round(start_sec * 1000))
    end_ms = int(round(end_sec * 1000))

    seg = AsrSegmentRecord(
        segment_uid="ASR:L21_V001:000000",
        source_segment_id="000000",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        start_ms=start_ms,
        end_ms=end_ms,
        start_sec=start_sec,
        end_sec=end_sec,
        text_raw="Chào mừng quý vị",
        text_norm="Chào mừng quý vị",
    )
    assert seg.segment_uid == "ASR:L21_V001:000000"
    assert seg.source_segment_id == "000000"
    assert seg.start_ms == 4430
    assert seg.end_ms == 8230


def test_validator_rejects_negative_and_inverted_timestamps(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(
        expected_video_count=2,
        expected_asr_segment_count=1,
        expected_asr_with_segments_count=1,
        expected_asr_zero_segment_count=1,
        expected_ocr_keyframe_count=2,
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    cov = [
        AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 1, 60.0, 60000, "HAS_SEGMENTS"),
        AsrVideoCoverageRecord("L24_V008", 1, "v1_natural_series_video", 0, 45.0, 45000, "ZERO_ASR_SEGMENTS"),
    ]
    # Inverted timestamps
    bad_seg = [
        AsrSegmentRecord(
            segment_uid="ASR:L21_V001:000001",
            source_segment_id="000001",
            video_id="L21_V001",
            video_ordinal=0,
            ordinal_space_id="v1_natural_series_video",
            start_ms=5000,
            end_ms=3000,
            start_sec=5.0,
            end_sec=3.0,
            text_raw="Thử nghiệm",
            text_norm="Thử nghiệm",
        )
    ]
    ocr_kf = [
        OcrKeyframeCoverageRecord("CUSTOM:L21_V001:F15", "L21_V001", 0, 15, 500, 0.5, "000001.jpg", "output/keyframes/L21_V001/000001.jpg", 0),
        OcrKeyframeCoverageRecord("CUSTOM:L24_V008:F30", "L24_V008", 1, 30, 1000, 1.0, "000001.jpg", "output/keyframes/L24_V008/000001.jpg", 0),
    ]
    res = validator.validate(asr_coverage=cov, asr_segments=bad_seg, ocr_keyframes=ocr_kf)
    assert not res.is_valid
    assert any("INVALID_ASR_INTERVAL" in e for e in res.errors)


def test_validator_rejects_empty_transcript(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(
        expected_video_count=2,
        expected_asr_segment_count=1,
        expected_asr_with_segments_count=1,
        expected_asr_zero_segment_count=1,
        expected_ocr_keyframe_count=2,
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    cov = [
        AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 1, 60.0, 60000, "HAS_SEGMENTS"),
        AsrVideoCoverageRecord("L24_V008", 1, "v1_natural_series_video", 0, 45.0, 45000, "ZERO_ASR_SEGMENTS"),
    ]
    empty_seg = [
        AsrSegmentRecord(
            segment_uid="ASR:L21_V001:000001",
            source_segment_id="000001",
            video_id="L21_V001",
            video_ordinal=0,
            ordinal_space_id="v1_natural_series_video",
            start_ms=1000,
            end_ms=3000,
            start_sec=1.0,
            end_sec=3.0,
            text_raw="   ",
            text_norm="",
        )
    ]
    ocr_kf = [
        OcrKeyframeCoverageRecord("CUSTOM:L21_V001:F15", "L21_V001", 0, 15, 500, 0.5, "000001.jpg", "output/keyframes/L21_V001/000001.jpg", 0),
        OcrKeyframeCoverageRecord("CUSTOM:L24_V008:F30", "L24_V008", 1, 30, 1000, 1.0, "000001.jpg", "output/keyframes/L24_V008/000001.jpg", 0),
    ]
    res = validator.validate(asr_coverage=cov, asr_segments=empty_seg, ocr_keyframes=ocr_kf)
    assert not res.is_valid
    assert any("EMPTY_ASR_TRANSCRIPT" in e for e in res.errors)


def test_zero_asr_status_is_preserved_not_error(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(
        expected_video_count=2,
        expected_asr_segment_count=1,
        expected_asr_with_segments_count=1,
        expected_asr_zero_segment_count=1,
        expected_ocr_keyframe_count=2,
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    cov = [
        AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 1, 60.0, 60000, "HAS_SEGMENTS"),
        AsrVideoCoverageRecord("L24_V008", 1, "v1_natural_series_video", 0, 45.0, 45000, "ZERO_ASR_SEGMENTS"),
    ]
    seg = [
        AsrSegmentRecord(
            segment_uid="ASR:L21_V001:000001",
            source_segment_id="000001",
            video_id="L21_V001",
            video_ordinal=0,
            ordinal_space_id="v1_natural_series_video",
            start_ms=1000,
            end_ms=3000,
            start_sec=1.0,
            end_sec=3.0,
            text_raw="Tin tức 60 giây",
            text_norm="Tin tức 60 giây",
        )
    ]
    ocr_kf = [
        OcrKeyframeCoverageRecord("CUSTOM:L21_V001:F15", "L21_V001", 0, 15, 500, 0.5, "000001.jpg", "output/keyframes/L21_V001/000001.jpg", 0),
        OcrKeyframeCoverageRecord("CUSTOM:L24_V008:F30", "L24_V008", 1, 30, 1000, 1.0, "000001.jpg", "output/keyframes/L24_V008/000001.jpg", 0),
    ]
    res = validator.validate(asr_coverage=cov, asr_segments=seg, ocr_keyframes=ocr_kf)
    assert res.is_valid
    assert res.asr_zero_segment_videos == 1
    assert res.asr_videos_with_segments == 1


# ----------------------------------------------------------------------
# 2. OCR and BGE Unit Tests
# ----------------------------------------------------------------------
def test_ocr_item_deterministic_uid_and_low_confidence_preserved(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(
        expected_video_count=2,
        expected_asr_segment_count=0,
        expected_asr_with_segments_count=0,
        expected_asr_zero_segment_count=2,
        expected_ocr_keyframe_count=2,
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    cov = [
        AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 0, 60.0, 60000, "ZERO_ASR_SEGMENTS"),
        AsrVideoCoverageRecord("L24_V008", 1, "v1_natural_series_video", 0, 45.0, 45000, "ZERO_ASR_SEGMENTS"),
    ]
    ocr_kf = [
        OcrKeyframeCoverageRecord("CUSTOM:L21_V001:F15", "L21_V001", 0, 15, 500, 0.5, "000001.jpg", "output/keyframes/L21_V001/000001.jpg", 2),
        OcrKeyframeCoverageRecord("CUSTOM:L24_V008:F30", "L24_V008", 1, 30, 1000, 1.0, "000001.jpg", "output/keyframes/L24_V008/000001.jpg", 0),
    ]
    # Low confidence raw OCR item (0.24) and high confidence (0.91)
    it1 = OcrItemRecord(
        ocr_uid="OCR:CUSTOM:L21_V001:F15:T0",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        frame_space="CUSTOM",
        keyframe_uid="CUSTOM:L21_V001:F15",
        frame_idx=15,
        timestamp_ms=500,
        raw_pts_time=0.5,
        local_text_index=0,
        text_raw="60 GIAY",
        text_norm="60 GIAY",
        bbox=[0.05, 0.80, 0.15, 0.95],
        ocr_confidence=0.91,
    )
    it2 = OcrItemRecord(
        ocr_uid="OCR:CUSTOM:L21_V001:F15:T1",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        frame_space="CUSTOM",
        keyframe_uid="CUSTOM:L21_V001:F15",
        frame_idx=15,
        timestamp_ms=500,
        raw_pts_time=0.5,
        local_text_index=1,
        text_raw="HTV9",
        text_norm="HTV9",
        bbox=[0.01, 0.01, 0.08, 0.12],
        ocr_confidence=0.24,  # low confidence preserved
    )

    res = validator.validate(asr_coverage=cov, asr_segments=[], ocr_keyframes=ocr_kf, ocr_items=[it1, it2])
    assert res.is_valid
    assert res.ocr_item_count == 2
    assert res.ocr_confidence_low_count == 1
    assert res.ocr_confidence_high_count == 1


def test_validator_rejects_non_finite_bbox(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(
        expected_video_count=2,
        expected_asr_segment_count=0,
        expected_asr_with_segments_count=0,
        expected_asr_zero_segment_count=2,
        expected_ocr_keyframe_count=2,
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    cov = [
        AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 0, 60.0, 60000, "ZERO_ASR_SEGMENTS"),
        AsrVideoCoverageRecord("L24_V008", 1, "v1_natural_series_video", 0, 45.0, 45000, "ZERO_ASR_SEGMENTS"),
    ]
    ocr_kf = [
        OcrKeyframeCoverageRecord("CUSTOM:L21_V001:F15", "L21_V001", 0, 15, 500, 0.5, "000001.jpg", "output/keyframes/L21_V001/000001.jpg", 1),
        OcrKeyframeCoverageRecord("CUSTOM:L24_V008:F30", "L24_V008", 1, 30, 1000, 1.0, "000001.jpg", "output/keyframes/L24_V008/000001.jpg", 0),
    ]
    bad_it = OcrItemRecord(
        ocr_uid="OCR:CUSTOM:L21_V001:F15:T0",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        frame_space="CUSTOM",
        keyframe_uid="CUSTOM:L21_V001:F15",
        frame_idx=15,
        timestamp_ms=500,
        raw_pts_time=0.5,
        local_text_index=0,
        text_raw="BAD BBOX",
        text_norm="BAD BBOX",
        bbox=[float("nan"), 0.80, 0.15, 0.95],
    )
    res = validator.validate(asr_coverage=cov, asr_segments=[], ocr_keyframes=ocr_kf, ocr_items=[bad_it])
    assert not res.is_valid
    assert any("NON_FINITE_BBOX" in e for e in res.errors)


# ----------------------------------------------------------------------
# 3. Registry Query APIs
# ----------------------------------------------------------------------
def test_asr_ocr_registry_queries():
    seg1 = AsrSegmentRecord(
        segment_uid="ASR:L21_V001:000001",
        source_segment_id="000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        start_ms=2000,
        end_ms=6000,
        start_sec=2.0,
        end_sec=6.0,
        text_raw="Bản tin 60 giây sáng",
        text_norm="Bản tin 60 giây sáng",
    )
    seg2 = AsrSegmentRecord(
        segment_uid="ASR:L21_V001:000002",
        source_segment_id="000002",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        start_ms=10000,
        end_ms=14000,
        start_sec=10.0,
        end_sec=14.0,
        text_raw="Hôm nay thời tiết đẹp",
        text_norm="Hôm nay thời tiết đẹp",
    )
    cov1 = AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 2, 60.0, 60000, "HAS_SEGMENTS")

    it1 = OcrItemRecord(
        ocr_uid="OCR:CUSTOM:L21_V001:F15:T0",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        frame_space="CUSTOM",
        keyframe_uid="CUSTOM:L21_V001:F15",
        frame_idx=15,
        timestamp_ms=3000,
        raw_pts_time=3.0,
        local_text_index=0,
        text_raw="60 GIAY",
        text_norm="60 GIAY",
    )

    reg = AsrOcrRegistry(
        asr_segments=[seg1, seg2],
        asr_coverage=[cov1],
        ocr_items=[it1],
    )

    # 1. get_asr_near
    near_segs = reg.get_asr_near("L21_V001", timestamp_ms=4000, window_ms=1000)
    assert len(near_segs) == 1
    assert near_segs[0].segment_uid == "ASR:L21_V001:000001"

    # 2. get_asr_overlapping
    overlap_segs = reg.get_asr_overlapping("L21_V001", start_ms=5000, end_ms=11000)
    assert len(overlap_segs) == 2

    # 3. get_ocr_for_keyframe
    kf_ocr = reg.get_ocr_for_keyframe("CUSTOM:L21_V001:F15")
    assert len(kf_ocr) == 1
    assert kf_ocr[0].ocr_uid == "OCR:CUSTOM:L21_V001:F15:T0"


# ----------------------------------------------------------------------
# 4. Duplicate Checks and Unknown Entities
# ----------------------------------------------------------------------
def test_validator_rejects_duplicate_segment_uid(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(
        expected_video_count=2,
        expected_asr_segment_count=2,
        expected_asr_with_segments_count=1,
        expected_asr_zero_segment_count=1,
        expected_ocr_keyframe_count=2,
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    cov = [
        AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 2, 60.0, 60000, "HAS_SEGMENTS"),
        AsrVideoCoverageRecord("L24_V008", 1, "v1_natural_series_video", 0, 45.0, 45000, "ZERO_ASR_SEGMENTS"),
    ]
    seg1 = AsrSegmentRecord("ASR:L21_V001:000001", "000001", "L21_V001", 0, "v1_natural_series_video", 1000, 3000, 1.0, 3.0, "A", "A")
    seg2 = AsrSegmentRecord("ASR:L21_V001:000001", "000002", "L21_V001", 0, "v1_natural_series_video", 4000, 6000, 4.0, 6.0, "B", "B")
    ocr_kf = [
        OcrKeyframeCoverageRecord("CUSTOM:L21_V001:F15", "L21_V001", 0, 15, 500, 0.5, "000001.jpg", "output/keyframes/L21_V001/000001.jpg", 0),
        OcrKeyframeCoverageRecord("CUSTOM:L24_V008:F30", "L24_V008", 1, 30, 1000, 1.0, "000001.jpg", "output/keyframes/L24_V008/000001.jpg", 0),
    ]
    res = validator.validate(asr_coverage=cov, asr_segments=[seg1, seg2], ocr_keyframes=ocr_kf)
    assert not res.is_valid
    assert any("DUPLICATE_SEGMENT_UID" in e for e in res.errors)


def test_validator_rejects_unknown_video_in_segment(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(
        expected_video_count=2,
        expected_asr_segment_count=1,
        expected_asr_with_segments_count=1,
        expected_asr_zero_segment_count=1,
        expected_ocr_keyframe_count=2,
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    cov = [
        AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 0, 60.0, 60000, "ZERO_ASR_SEGMENTS"),
        AsrVideoCoverageRecord("L24_V008", 1, "v1_natural_series_video", 0, 45.0, 45000, "ZERO_ASR_SEGMENTS"),
    ]
    bad_seg = AsrSegmentRecord("ASR:L99_V999:000001", "000001", "L99_V999", 99, "v1_natural_series_video", 1000, 3000, 1.0, 3.0, "A", "A")
    ocr_kf = [
        OcrKeyframeCoverageRecord("CUSTOM:L21_V001:F15", "L21_V001", 0, 15, 500, 0.5, "000001.jpg", "output/keyframes/L21_V001/000001.jpg", 0),
        OcrKeyframeCoverageRecord("CUSTOM:L24_V008:F30", "L24_V008", 1, 30, 1000, 1.0, "000001.jpg", "output/keyframes/L24_V008/000001.jpg", 0),
    ]
    res = validator.validate(asr_coverage=cov, asr_segments=[bad_seg], ocr_keyframes=ocr_kf)
    assert not res.is_valid
    assert any("SEGMENT_UNKNOWN_VIDEO" in e for e in res.errors)


def test_bge_rowmap_validation_and_unmapped_detection(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(
        expected_video_count=2,
        expected_asr_segment_count=0,
        expected_asr_with_segments_count=0,
        expected_asr_zero_segment_count=2,
        expected_ocr_keyframe_count=2,
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    cov = [
        AsrVideoCoverageRecord("L21_V001", 0, "v1_natural_series_video", 0, 60.0, 60000, "ZERO_ASR_SEGMENTS"),
        AsrVideoCoverageRecord("L24_V008", 1, "v1_natural_series_video", 0, 45.0, 45000, "ZERO_ASR_SEGMENTS"),
    ]
    ocr_kf = [
        OcrKeyframeCoverageRecord("CUSTOM:L21_V001:F15", "L21_V001", 0, 15, 500, 0.5, "000001.jpg", "output/keyframes/L21_V001/000001.jpg", 1),
        OcrKeyframeCoverageRecord("CUSTOM:L24_V008:F30", "L24_V008", 1, 30, 1000, 1.0, "000001.jpg", "output/keyframes/L24_V008/000001.jpg", 0),
    ]
    rm_valid = OcrBgeRowmapRecord("ocr_bge_m3_single_text_v1", "000", 0, "OCR:CUSTOM:L21_V001:F15:T0", "CUSTOM:L21_V001:F15", "L21_V001", 15, 500)
    rm_bad = OcrBgeRowmapRecord("ocr_bge_m3_single_text_v1", "000", 1, "OCR:CUSTOM:UNKNOWN:F99:T0", "CUSTOM:UNKNOWN:F99", "UNKNOWN", 99, 999)

    res = validator.validate(asr_coverage=cov, asr_segments=[], ocr_keyframes=ocr_kf, bge_rowmaps=[rm_valid, rm_bad])
    assert not res.is_valid
    assert res.bge_mapped_row_count == 1
    assert res.bge_unmapped_row_count == 1
    assert any("BGE_UNKNOWN_KEYFRAME" in e for e in res.errors)


# ----------------------------------------------------------------------
# 5. Builder End-to-End Test
# ----------------------------------------------------------------------
def test_asr_ocr_builder_materialization(tmp_path, mock_video_registry, mock_custom_registry):
    # Setup temporary mock input files
    asr_vid_p = tmp_path / "asr_videos.jsonl"
    with open(asr_vid_p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"video_id": "L21_V001", "duration_sec": 60.0, "segment_count": 1}) + "\n")
        f.write(json.dumps({"video_id": "L24_V008", "duration_sec": 45.0, "segment_count": 0}) + "\n")

    asr_seg_p = tmp_path / "asr_segments.jsonl"
    with open(asr_seg_p, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "video_id": "L21_V001",
            "segment_id": "L21_V001:000000",
            "start_sec": 4.43,
            "end_sec": 8.23,
            "text": "Chào mừng quý vị",
            "language": "vi",
            "model": "medium",
            "avg_logprob": -0.22,
        }) + "\n")

    ocr_man_p = tmp_path / "manifest.jsonl"
    with open(ocr_man_p, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "ocr_image_source": "CUSTOM",
            "video_id": "L21_V001",
            "file_name": "000001.jpg",
            "frame_idx": 15,
            "pts_time": 0.5,
            "image_path": "output/keyframes/L21_V001/000001.jpg",
        }) + "\n")
        f.write(json.dumps({
            "ocr_image_source": "CUSTOM",
            "video_id": "L24_V008",
            "file_name": "000001.jpg",
            "frame_idx": 30,
            "pts_time": 1.0,
            "image_path": "output/keyframes/L24_V008/000001.jpg",
        }) + "\n")

    out_dir = tmp_path / "materialized_catalog"
    builder = AsrOcrCatalogBuilder(
        video_registry=mock_video_registry,
        custom_registry=mock_custom_registry,
    )
    # Configure validator to expect 2 videos and 1 segment
    builder.validator.expected_video_count = 2
    builder.validator.expected_asr_segment_count = 1
    builder.validator.expected_asr_with_segments_count = 1
    builder.validator.expected_asr_zero_segment_count = 1
    builder.validator.expected_ocr_keyframe_count = 2

    validation = builder.materialize(
        output_dir=out_dir,
        asr_videos_path=asr_vid_p,
        asr_segments_path=asr_seg_p,
        ocr_manifest_path=ocr_man_p,
    )

    assert validation.is_valid
    assert (out_dir / "asr_segments_canonical.jsonl").exists()
    assert (out_dir / "asr_video_coverage.jsonl").exists()
    assert (out_dir / "asr_space.json").exists()
    assert (out_dir / "ocr_keyframe_coverage.jsonl").exists()
    assert (out_dir / "ocr_space.json").exists()
    assert (out_dir / "build_manifest_m1c.json").exists()

    # Load from materialized dir using AsrOcrRegistry
    registry = AsrOcrRegistry.load_from_dir(out_dir)
    assert len(registry._asr_segments_by_uid) == 1
    assert len(registry._asr_coverage_by_video) == 2
    assert len(registry._ocr_kf_by_uid) == 2
    assert registry.get_asr_video_status("L24_V008").asr_status == "ZERO_ASR_SEGMENTS"


# ----------------------------------------------------------------------
# 6. M1C-R1 BGE Shard Disk Validation & Determinism Tests
# ----------------------------------------------------------------------
def test_bge_shard_disk_validator_rejects_missing_or_corrupt_files(tmp_path, mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(video_registry=mock_video_registry, custom_registry=mock_custom_registry)
    
    dense_dir = tmp_path / "mock_dense"
    dense_dir.mkdir()

    # 1. Missing shard files
    errors = validator.validate_bge_shards_on_disk(dense_dir, expected_shard_count=2, expected_dim=1024)
    assert len(errors) > 0
    assert any("MISSING_EMBEDDING_SHARD" in e for e in errors)

    # 2. Shard with wrong dimension (512 instead of 1024)
    import numpy as np
    emb0 = np.zeros((10, 512), dtype=np.float32)
    np.save(dense_dir / "embeddings_shard_000.npy", emb0)
    with open(dense_dir / "metadata_shard_000.json", "w", encoding="utf-8") as f:
        json.dump([{"video_id": "L21_V001", "keyframe_id": "000001", "text_index": 0}] * 10, f)

    emb1 = np.zeros((5, 1024), dtype=np.float32)
    np.save(dense_dir / "embeddings_shard_001.npy", emb1)
    with open(dense_dir / "metadata_shard_001.json", "w", encoding="utf-8") as f:
        json.dump([{"video_id": "L24_V008", "keyframe_id": "000001", "text_index": 0}] * 5, f)

    errors = validator.validate_bge_shards_on_disk(dense_dir, expected_shard_count=2, expected_dim=1024)
    assert any("INVALID_SHARD_SHAPE" in e for e in errors)

    # 3. Shard with row count mismatch (vector rows != metadata rows)
    emb0_correct = np.zeros((10, 1024), dtype=np.float32)
    np.save(dense_dir / "embeddings_shard_000.npy", emb0_correct)
    with open(dense_dir / "metadata_shard_000.json", "w", encoding="utf-8") as f:
        json.dump([{"video_id": "L21_V001", "keyframe_id": "000001", "text_index": 0}] * 8, f) # 8 != 10

    errors = validator.validate_bge_shards_on_disk(dense_dir, expected_shard_count=2, expected_dim=1024)
    assert any("SHARD_ROW_COUNT_MISMATCH" in e for e in errors)


def test_bge_rowmap_checksum_determinism(mock_video_registry, mock_custom_registry):
    validator = AsrOcrValidator(video_registry=mock_video_registry, custom_registry=mock_custom_registry)
    
    r1 = OcrBgeRowmapRecord("ocr_bge_m3_single_text_v1", "000", 0, "OCR:CUSTOM:L21_V001:F15:T0", "CUSTOM:L21_V001:F15", "L21_V001", 15, 500)
    r2 = OcrBgeRowmapRecord("ocr_bge_m3_single_text_v1", "000", 1, "OCR:CUSTOM:L24_V008:F30:T0", "CUSTOM:L24_V008:F30", "L24_V008", 30, 1000)

    hash1 = validator.compute_bge_rowmap_checksum([r1, r2])
    hash2 = validator.compute_bge_rowmap_checksum([r2, r1]) # Order should be sorted
    assert hash1 == hash2
    assert len(hash1) == 64

