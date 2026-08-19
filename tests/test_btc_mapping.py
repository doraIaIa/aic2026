from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import List

import numpy as np
import pytest

from aic2026.data_hub.btc_builder import BtcCatalogBuilder
from aic2026.data_hub.btc_models import (
    BtcClipRowRecord,
    BtcKeyframeRecord,
    BtcMediaInfoRecord,
    BtcObjectCoverageRecord,
    BtcObjectDetectionRecord,
    BtcSpace,
)
from aic2026.data_hub.btc_registry import BtcRegistry
from aic2026.data_hub.btc_validator import BtcValidator
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
        created_at="2026-08-19T00:00:00Z",
    )
    return VideoRegistry(records=[v1, v2], video_space=space)


# ----------------------------------------------------------------------
# 1. Identity & Format Tests
# ----------------------------------------------------------------------
def test_btc_keyframe_deterministic_uid_and_ms_derivation(mock_video_registry: VideoRegistry):
    kf = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
    )
    assert kf.keyframe_uid == "BTC:L21_V001:KF000001"
    assert kf.frame_space == "BTC"
    assert kf.timestamp_ms == 0

    kf2 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000002",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=2,
        frame_idx=75,
        timestamp_ms=3000,
        raw_pts_time=3.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/002.jpg",
    )
    assert kf2.timestamp_ms == 3000


def test_validator_rejects_non_btc_namespace(mock_video_registry: VideoRegistry):
    validator = BtcValidator(video_registry=mock_video_registry, expected_video_count=1, expected_keyframe_count=1)
    bad_kf = BtcKeyframeRecord(
        keyframe_uid="CUSTOM:L21_V001:F0",  # Wrong namespace
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
        frame_space="CUSTOM",
    )
    res = validator.validate([bad_kf])
    assert not res.is_valid
    assert any("INVALID_BTC_UID_FORMAT" in e for e in res.errors)
    assert any("INVALID_FRAME_SPACE" in e for e in res.errors)


def test_validator_rejects_duplicate_video_n_and_unknown_video(mock_video_registry: VideoRegistry):
    validator = BtcValidator(video_registry=mock_video_registry, expected_video_count=2, expected_keyframe_count=2)
    kf1 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
    )
    # Duplicate (video_id, local_keyframe_no=1)
    kf2 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=25,
        timestamp_ms=1000,
        raw_pts_time=1.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
    )
    res = validator.validate([kf1, kf2])
    assert not res.is_valid
    assert any("DUPLICATE_KEYFRAME_UID" in e for e in res.errors)
    assert any("DUPLICATE_VIDEO_N" in e for e in res.errors)


def test_validator_rejects_negative_timestamps_and_invalid_paths(mock_video_registry: VideoRegistry):
    validator = BtcValidator(video_registry=mock_video_registry, expected_video_count=1, expected_keyframe_count=1)
    bad_kf = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=-500,
        raw_pts_time=-0.5,
        fps=-25.0,
        image_relpath="C:\\absolute\\path\\001.jpg",  # Windows absolute path
    )
    res = validator.validate([bad_kf])
    assert not res.is_valid
    assert any("NEGATIVE_TIMESTAMP" in e for e in res.errors)
    assert any("INVALID_PTS_TIME" in e for e in res.errors)
    assert any("INVALID_FPS" in e for e in res.errors)
    assert any("WINDOWS_SEPARATOR_IN_RELPATH" in e or "ABSOLUTE_IMAGE_PATH_REJECTED" in e for e in res.errors)


# ----------------------------------------------------------------------
# 2. Raw CLIP Mapping Tests
# ----------------------------------------------------------------------
def test_clip_row_formula_and_validation(mock_video_registry: VideoRegistry):
    validator = BtcValidator(video_registry=mock_video_registry, expected_video_count=1, expected_keyframe_count=2)
    kf1 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
    )
    kf2 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000002",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=2,
        frame_idx=25,
        timestamp_ms=1000,
        raw_pts_time=1.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/002.jpg",
    )
    # Valid rowmaps (row 0 -> n=1, row 1 -> n=2)
    rm0 = BtcClipRowRecord(
        clip_source_id="btc_clip_features_32_v1",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        row_in_video=0,
        keyframe_uid="BTC:L21_V001:KF000001",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        feature_relpath="data_extracted/clip-features-32/L21_V001.npy",
        dimension=512,
        dtype="float16",
    )
    rm1 = BtcClipRowRecord(
        clip_source_id="btc_clip_features_32_v1",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        row_in_video=1,
        keyframe_uid="BTC:L21_V001:KF000002",
        local_keyframe_no=2,
        frame_idx=25,
        timestamp_ms=1000,
        feature_relpath="data_extracted/clip-features-32/L21_V001.npy",
        dimension=512,
        dtype="float16",
    )
    res = validator.validate(btc_keyframes=[kf1, kf2], clip_rowmaps=[rm0, rm1])
    assert res.is_valid
    assert res.raw_clip_mapped_rows == 2
    assert res.raw_clip_unmapped_rows == 0


def test_clip_validator_rejects_wrong_formula_or_dimension(mock_video_registry: VideoRegistry):
    validator = BtcValidator(video_registry=mock_video_registry, expected_video_count=1, expected_keyframe_count=1)
    kf1 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
    )
    # Wrong formula: row 0 mapped to n=2, dimension 768 instead of 512
    bad_rm = BtcClipRowRecord(
        clip_source_id="btc_clip_features_32_v1",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        row_in_video=0,
        keyframe_uid="BTC:L21_V001:KF000001",
        local_keyframe_no=2,
        frame_idx=0,
        timestamp_ms=0,
        feature_relpath="data_extracted/clip-features-32/L21_V001.npy",
        dimension=768,
        dtype="float16",
    )
    res = validator.validate(btc_keyframes=[kf1], clip_rowmaps=[bad_rm])
    assert not res.is_valid
    assert any("CLIP_ROW_FORMULA_MISMATCH" in e for e in res.errors)
    assert any("INVALID_CLIP_DIMENSION" in e for e in res.errors)


# ----------------------------------------------------------------------
# 3. Object Detections & Coverage Tests
# ----------------------------------------------------------------------
def test_object_detection_and_coverage_validation(mock_video_registry: VideoRegistry):
    validator = BtcValidator(video_registry=mock_video_registry, expected_video_count=1, expected_keyframe_count=2)
    kf1 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
    )
    kf2 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000002",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=2,
        frame_idx=25,
        timestamp_ms=1000,
        raw_pts_time=1.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/002.jpg",
    )
    det1 = BtcObjectDetectionRecord(
        detection_uid="BTC_OBJECT:BTC:L21_V001:KF000001:D0",
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        local_detection_index=0,
        class_name="/m/01jfsr",
        class_entity="Lantern",
        class_label="84",
        confidence=0.796738,
        bbox=[0.468603, 0.366423, 0.636186, 0.467148],
    )
    cov1 = BtcObjectCoverageRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        detection_count=1,
        object_status="HAS_OBJECTS",
        source_file_relpath="data/objects-aic25-b1.zip#objects/L21_V001/001.json",
    )
    cov2 = BtcObjectCoverageRecord(
        keyframe_uid="BTC:L21_V001:KF000002",
        video_id="L21_V001",
        video_ordinal=0,
        local_keyframe_no=2,
        frame_idx=25,
        timestamp_ms=1000,
        detection_count=0,
        object_status="EMPTY",
        source_file_relpath="data/objects-aic25-b1.zip#objects/L21_V001/002.json",
    )
    res = validator.validate(
        btc_keyframes=[kf1, kf2],
        object_detections=[det1],
        object_coverage=[cov1, cov2],
    )
    assert res.is_valid
    assert res.object_detection_count == 1
    assert res.object_empty_keyframe_count == 1
    assert res.object_unavailable_keyframe_count == 0


# ----------------------------------------------------------------------
# 4. Media-Info Tests
# ----------------------------------------------------------------------
def test_media_info_validation(mock_video_registry: VideoRegistry):
    validator = BtcValidator(video_registry=mock_video_registry, expected_video_count=2, expected_keyframe_count=2)
    kf1 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
    )
    kf2 = BtcKeyframeRecord(
        keyframe_uid="BTC:L24_V008:KF000001",
        video_id="L24_V008",
        video_ordinal=1,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L24_V008/001.jpg",
    )
    m1 = BtcMediaInfoRecord(
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        title="60 Giay Sang",
        author="60 Giay Official",
        keywords=["HTV", "News"],
        duration_sec=1262,
    )
    m2 = BtcMediaInfoRecord(
        video_id="L24_V008",
        video_ordinal=1,
        ordinal_space_id="v1_natural_series_video",
        title="Mua Lan Su Rong",
        duration_sec=450,
    )
    res = validator.validate(btc_keyframes=[kf1, kf2], media_info=[m1, m2])
    assert res.is_valid
    assert res.media_info_count == 2


# ----------------------------------------------------------------------
# 5. Registry Queries Test
# ----------------------------------------------------------------------
def test_btc_registry_queries():
    kf1 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000001",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=1,
        frame_idx=0,
        timestamp_ms=0,
        raw_pts_time=0.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/001.jpg",
    )
    kf2 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000002",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=2,
        frame_idx=75,
        timestamp_ms=3000,
        raw_pts_time=3.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/002.jpg",
    )
    kf3 = BtcKeyframeRecord(
        keyframe_uid="BTC:L21_V001:KF000003",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        local_keyframe_no=3,
        frame_idx=250,
        timestamp_ms=10000,
        raw_pts_time=10.0,
        fps=25.0,
        image_relpath="data_extracted/keyframes/L21_V001/003.jpg",
    )

    reg = BtcRegistry(keyframes=[kf1, kf2, kf3])
    assert reg.total_keyframes == 3
    assert reg.total_videos == 1

    assert reg.get_btc_keyframe("BTC:L21_V001:KF000002") == kf2
    assert reg.get_btc_keyframe_by_video_n("L21_V001", 2) == kf2

    # Query near 3200ms with window 1000ms -> [2200, 4200] -> should find kf2
    near = reg.get_btc_keyframes_near("L21_V001", timestamp_ms=3200, window_ms=1000)
    assert len(near) == 1
    assert near[0] == kf2

    # Nearest to 8000ms -> kf3 (10000ms diff 2000 vs kf2 3000ms diff 5000)
    nearest = reg.get_nearest_btc_keyframe("L21_V001", timestamp_ms=8000)
    assert nearest == kf3


# ----------------------------------------------------------------------
# 6. Builder End-to-End Mock Test
# ----------------------------------------------------------------------
def test_btc_builder_materialization(tmp_path: Path, mock_video_registry: VideoRegistry):
    # Setup mock map-keyframes
    map_dir = tmp_path / "map-keyframes"
    map_dir.mkdir()
    with open(map_dir / "L21_V001.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["n", "pts_time", "fps", "frame_idx"])
        writer.writerow(["1", "0.0", "25.0", "0"])
        writer.writerow(["2", "3.0", "25.0", "75"])

    with open(map_dir / "L24_V008.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["n", "pts_time", "fps", "frame_idx"])
        writer.writerow(["1", "0.0", "25.0", "0"])

    # Setup mock clip-features
    clip_dir = tmp_path / "clip-features-32"
    clip_dir.mkdir()
    np.save(clip_dir / "L21_V001.npy", np.zeros((2, 512), dtype=np.float16))
    np.save(clip_dir / "L24_V008.npy", np.zeros((1, 512), dtype=np.float16))

    # Setup mock objects zip
    obj_zip = tmp_path / "objects.zip"
    with zipfile.ZipFile(obj_zip, "w") as zf:
        zf.writestr(
            "objects/L21_V001/001.json",
            json.dumps({
                "detection_scores": ["0.95"],
                "detection_class_names": ["/m/01jfsr"],
                "detection_class_entities": ["Lantern"],
                "detection_boxes": [["0.1", "0.2", "0.3", "0.4"]],
                "detection_class_labels": ["84"],
            }),
        )
        zf.writestr(
            "objects/L21_V001/002.json",
            json.dumps({
                "detection_scores": [],
                "detection_class_names": [],
                "detection_class_entities": [],
                "detection_boxes": [],
                "detection_class_labels": [],
            }),
        )
        zf.writestr(
            "objects/L24_V008/001.json",
            json.dumps({
                "detection_scores": ["0.80"],
                "detection_class_names": ["/m/0138tl"],
                "detection_class_entities": ["Toy"],
                "detection_boxes": [["0.0", "0.1", "0.9", "0.8"]],
                "detection_class_labels": ["11"],
            }),
        )

    # Setup mock media-info zip
    media_zip = tmp_path / "media-info.zip"
    with zipfile.ZipFile(media_zip, "w") as zf:
        zf.writestr(
            "media-info/L21_V001.json",
            json.dumps({"title": "Video 1", "length": 60, "keywords": ["v1"]}),
        )
        zf.writestr(
            "media-info/L24_V008.json",
            json.dumps({"title": "Video 2", "length": 45, "keywords": ["v2"]}),
        )

    out_dir = tmp_path / "materialized_btc"
    validator = BtcValidator(
        video_registry=mock_video_registry,
        expected_video_count=2,
        expected_keyframe_count=3,
    )
    builder = BtcCatalogBuilder(video_registry=mock_video_registry, validator=validator)

    res = builder.materialize(
        output_dir=out_dir,
        map_keyframes_dir=map_dir,
        clip_features_dir=clip_dir,
        objects_zip_path=obj_zip,
        media_info_zip_path=media_zip,
    )

    assert res.is_valid
    assert res.btc_keyframe_count == 3
    assert res.btc_video_count == 2
    assert res.raw_clip_row_count == 3
    assert res.raw_clip_mapped_rows == 3
    assert res.object_detection_count == 2
    assert res.object_empty_keyframe_count == 1
    assert res.media_info_count == 2

    # Verify materialized files exist
    assert (out_dir / "btc_keyframes.jsonl").exists()
    assert (out_dir / "btc_clip_raw_rowmap.jsonl").exists()
    assert (out_dir / "btc_objects.jsonl").exists()
    assert (out_dir / "btc_object_coverage.jsonl").exists()
    assert (out_dir / "media_info.jsonl").exists()
    assert (out_dir / "btc_space.json").exists()
    assert (out_dir / "btc_clip_raw_passport.json").exists()
    assert (out_dir / "btc_object_space.json").exists()
    assert (out_dir / "source_registry.jsonl").exists()
    assert (out_dir / "build_manifest_m1d.json").exists()

    # Load via BtcRegistry
    reg = BtcRegistry.load_from_dir(out_dir)
    assert reg.total_keyframes == 3
    assert reg.total_videos == 2
    assert len(reg.get_btc_objects("BTC:L21_V001:KF000001")) == 1
    assert reg.get_media_info("L21_V001").title == "Video 1"
