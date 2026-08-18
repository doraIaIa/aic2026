from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from aic2026.data_hub import (
    CustomKeyframeRecord,
    CustomKeyframeRegistry,
    CustomKeyframeValidator,
    CustomSpace,
    QwenMissingRecord,
    QwenSemanticRecord,
    VideoRecord,
    VideoRegistry,
    build_custom_and_qwen_records,
    materialize_custom_qwen_catalog,
    normalize_custom_image_relpath,
)


def _create_mock_video_registry() -> VideoRegistry:
    """Mock video registry with 3 videos: L21_V001, L21_V002, L22_V001."""
    records = [
        VideoRecord(video_id="L21_V001", ordinal=0, ordinal_space_id="v1_natural_series_video", series="L21", source_relpath="data_extracted/video/L21_V001.mp4"),
        VideoRecord(video_id="L21_V002", ordinal=1, ordinal_space_id="v1_natural_series_video", series="L21", source_relpath="data_extracted/video/L21_V002.mp4"),
        VideoRecord(video_id="L22_V001", ordinal=2, ordinal_space_id="v1_natural_series_video", series="L22", source_relpath="data_extracted/video/L22_V001.mp4"),
    ]
    return VideoRegistry(records=records)


def _create_mock_custom_and_qwen_items() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    custom_items = [
        {"video_id": "L21_V001", "frame_idx": 15, "pts_time": 0.5, "keyframe_id": 1, "file_name": "000001.jpg", "image_path": "/content/drive/MyDrive/AIC_2026/output/keyframes/L21_V001/000001.jpg"},
        {"video_id": "L21_V001", "frame_idx": 45, "pts_time": 1.5, "keyframe_id": 2, "file_name": "000002.jpg", "image_path": "output/keyframes/L21_V001/000002.jpg"},
        {"video_id": "L21_V002", "frame_idx": 30, "pts_time": 1.0, "keyframe_id": 1, "file_name": "000001.jpg", "image_path": "output/keyframes/L21_V002/000001.jpg"},
        {"video_id": "L22_V001", "frame_idx": 60, "pts_time": 2.0, "keyframe_id": 1, "file_name": "000001.jpg", "image_path": "output/keyframes/L22_V001/000001.jpg"},
    ]

    qwen_items = [
        {
            "video_id": "L21_V001",
            "frame_idx": 15,
            "pts_time": 0.5,
            "objects": ["car", "tree"],
            "attributes": ["red car", "green tree"],
            "spatial_relations": ["car is next to tree"],
            "counts": ["one car", "one tree"],
            "scene": ["outdoor road"],
            "visible_actions": ["car moving"],
            "caption": "A red car driving near a green tree.",
        },
        {
            "video_id": "L21_V001",
            "frame_idx": 45,
            "pts_time": 1.5,
            "objects": [],
            "attributes": [],
            "spatial_relations": [],
            "counts": [],
            "scene": [],
            "visible_actions": [],
            "caption": "",  # Empty caption -> will be treated as MISSING
        },
        {
            "video_id": "L21_V002",
            "frame_idx": 30,
            "pts_time": 1.0,
            "objects": ["person"],
            "attributes": ["blue shirt"],
            "spatial_relations": [],
            "counts": ["one person"],
            "scene": ["office"],
            "visible_actions": ["walking"],
            "caption": "A person in a blue shirt walking in an office.",
        },
        # L22_V001 frame 60 is omitted from qwen_items -> will be treated as MISSING
    ]

    return custom_items, qwen_items


def test_custom_uid_and_image_relpath_normalization():
    """Verify UID format CUSTOM:{video_id}:F{frame_idx} and image path relativization."""
    rel = normalize_custom_image_relpath(
        "/content/drive/MyDrive/AIC_2026/output/keyframes/L21_V001/000001.jpg",
        "L21_V001",
        "000001.jpg",
    )
    assert rel == "output/keyframes/L21_V001/000001.jpg"

    vreg = _create_mock_video_registry()
    custom_items, qwen_items = _create_mock_custom_and_qwen_items()
    c_records, q_records, m_records = build_custom_and_qwen_records(custom_items, qwen_items, vreg)

    assert len(c_records) == 4
    assert c_records[0].keyframe_uid == "CUSTOM:L21_V001:F15"
    assert c_records[0].video_ordinal == 0
    assert c_records[0].timestamp_ms == 500
    assert c_records[0].qwen_status == "OK"

    # Frame 45 has empty semantics but is present in raw shard -> OK
    assert c_records[1].qwen_status == "OK"
    # Frame 60 was omitted from qwen_items -> MISSING
    assert c_records[3].qwen_status == "MISSING"
    assert len(q_records) == 3
    assert len(m_records) == 1


def test_validator_passes_on_valid_data():
    """Validator passes when all constraints and joins are valid."""
    vreg = _create_mock_video_registry()
    custom_items, qwen_items = _create_mock_custom_and_qwen_items()
    c_records, q_records, m_records = build_custom_and_qwen_records(custom_items, qwen_items, vreg)

    validator = CustomKeyframeValidator(
        expected_keyframe_count=4,
        expected_video_count=3,
        video_registry=vreg,
    )
    res = validator.validate(c_records, q_records, m_records)
    assert res.is_valid is True
    assert res.errors == []
    assert res.custom_keyframe_count == 4
    assert res.qwen_valid_count == 3
    assert res.qwen_missing_count == 1


def test_validator_rejects_unknown_video_id():
    """Validator fails closed if a custom keyframe references an unknown video."""
    vreg = _create_mock_video_registry()
    bad_record = CustomKeyframeRecord(
        keyframe_uid="CUSTOM:L99_V999:F10",
        video_id="L99_V999",
        video_ordinal=999,
        ordinal_space_id="v1_natural_series_video",
        frame_idx=10,
        timestamp_ms=333,
        raw_pts_time=0.333,
        shot_id=0,
        cluster_id=0,
        embedding_index=0,
        source_keyframe_id=1,
        file_name="000001.jpg",
        image_relpath="output/keyframes/L99_V999/000001.jpg",
    )
    validator = CustomKeyframeValidator(expected_keyframe_count=1, expected_video_count=1, video_registry=vreg)
    res = validator.validate([bad_record])
    assert res.is_valid is False
    assert any("UNKNOWN_VIDEO_ID" in err for err in res.errors)


def test_validator_rejects_duplicate_join_key():
    """Validator fails closed if duplicate (video_id, frame_idx) exists in custom records."""
    vreg = _create_mock_video_registry()
    custom_items, qwen_items = _create_mock_custom_and_qwen_items()
    # Duplicate first item
    custom_items.append(dict(custom_items[0]))
    c_records, _, _ = build_custom_and_qwen_records(custom_items, qwen_items, vreg)

    validator = CustomKeyframeValidator(expected_keyframe_count=5, expected_video_count=3, video_registry=vreg)
    res = validator.validate(c_records)
    assert res.is_valid is False
    assert any("DUPLICATE_KEYFRAME_UID" in err or "DUPLICATE_VIDEO_FRAME" in err for err in res.errors)


def test_validator_rejects_qwen_pts_mismatch():
    """Validator fails closed if Qwen pts_time differs from custom keyframe pts_time."""
    vreg = _create_mock_video_registry()
    custom_items, qwen_items = _create_mock_custom_and_qwen_items()
    # Mutate Qwen pts_time
    qwen_items[0]["pts_time"] = 999.0
    c_records, q_records, m_records = build_custom_and_qwen_records(custom_items, qwen_items, vreg)

    validator = CustomKeyframeValidator(expected_keyframe_count=4, expected_video_count=3, video_registry=vreg)
    res = validator.validate(c_records, q_records, m_records)
    assert res.is_valid is False
    assert any("PTS_MISMATCH" in err for err in res.errors)


def test_validator_rejects_orphan_qwen():
    """Validator fails closed if Qwen has an entry not present in custom keyframes."""
    vreg = _create_mock_video_registry()
    custom_items, qwen_items = _create_mock_custom_and_qwen_items()
    c_records, q_records, m_records = build_custom_and_qwen_records(custom_items, qwen_items, vreg)

    # Inject orphan Qwen record
    orphan = QwenSemanticRecord(
        keyframe_uid="CUSTOM:L21_V001:F99999",
        video_id="L21_V001",
        frame_idx=99999,
        timestamp_ms=999000,
        raw_pts_time=999.0,
        caption="Orphan caption",
    )
    bad_qwen = list(q_records) + [orphan]

    validator = CustomKeyframeValidator(expected_keyframe_count=4, expected_video_count=3, video_registry=vreg)
    res = validator.validate(c_records, bad_qwen, m_records)
    assert res.is_valid is False
    assert any("ORPHAN_QWEN_RECORD" in err for err in res.errors)


def test_materialization_and_read_api(tmp_path: Path):
    """Verify materializer creates JSONL/Passport files and CustomKeyframeRegistry read interface works."""
    vreg = _create_mock_video_registry()
    custom_items, qwen_items = _create_mock_custom_and_qwen_items()
    c_records, q_records, m_records = build_custom_and_qwen_records(custom_items, qwen_items, vreg)

    out_dir = tmp_path / "custom_catalog"
    files = materialize_custom_qwen_catalog(c_records, q_records, m_records, out_dir, video_registry=vreg)

    assert files["custom_keyframes"].exists()
    assert files["qwen_semantics"].exists()
    assert files["qwen_missing"].exists()
    assert files["custom_space"].exists()
    assert files["source_registry"].exists()
    assert files["build_manifest"].exists()

    # Load registry
    registry = CustomKeyframeRegistry.load_from_directory(out_dir, video_registry=vreg)
    assert registry.keyframe_count() == 4
    assert registry.qwen_count() == 3
    assert registry.qwen_missing_count() == 1

    # Query keyframe
    kf = registry.get_custom_keyframe("CUSTOM:L21_V001:F15")
    assert kf is not None
    assert kf.frame_idx == 15
    assert kf.qwen_status == "OK"

    # Query Qwen semantics
    q = registry.get_qwen("CUSTOM:L21_V001:F15")
    assert q is not None
    assert "red car" in q.caption

    # Check frame 45 (present in raw shard with empty semantics -> OK)
    assert registry.qwen_status("CUSTOM:L21_V001:F45") == "OK"
    q45 = registry.get_qwen("CUSTOM:L21_V001:F45")
    assert q45 is not None
    assert q45.caption == ""

    # Check frame 60 (omitted from raw shard -> MISSING)
    assert registry.qwen_status("CUSTOM:L22_V001:F60") == "MISSING"
    assert registry.get_qwen("CUSTOM:L22_V001:F60") is None


def test_cli_custom_qwen_catalog(tmp_path: Path):
    """Verify CLI build-custom-qwen-catalog and validate-custom-qwen-catalog commands."""
    from aic2026.cli import main
    from aic2026.data_hub.builder import materialize_video_catalog

    vreg = _create_mock_video_registry()
    vcat_dir = tmp_path / "video_catalog"
    materialize_video_catalog(vreg.to_records(), vcat_dir)

    custom_items, qwen_items = _create_mock_custom_and_qwen_items()
    custom_file = tmp_path / "custom.jsonl"
    custom_file.write_text("\n".join(json.dumps(r) for r in custom_items) + "\n", encoding="utf-8")

    qwen_file = tmp_path / "qwen.jsonl"
    qwen_file.write_text("\n".join(json.dumps(r) for r in qwen_items) + "\n", encoding="utf-8")

    out_dir = tmp_path / "custom_qwen_out"
    rc = main([
        "build-custom-qwen-catalog",
        "--custom-input", str(custom_file),
        "--qwen-input", str(qwen_file),
        "--video-catalog", str(vcat_dir),
        "--out", str(out_dir),
    ])
    assert rc == 0

    rc_val = main([
        "validate-custom-qwen-catalog",
        "--catalog-dir", str(out_dir),
        "--video-catalog", str(vcat_dir),
        "--expected-count", "4",
        "--expected-video-count", "3",
    ])
    assert rc_val == 0


def test_validator_rejects_absolute_paths_and_traversal():
    """Validator rejects Windows absolute, POSIX absolute, and path traversal in image_relpath."""
    vreg = _create_mock_video_registry()

    # Windows absolute
    bad_win = CustomKeyframeRecord(
        keyframe_uid="CUSTOM:L21_V001:F1",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        frame_idx=1,
        timestamp_ms=33,
        raw_pts_time=0.033,
        shot_id=0,
        cluster_id=0,
        embedding_index=0,
        source_keyframe_id=1,
        file_name="000001.jpg",
        image_relpath=r"G:\AIC_2026\output\keyframes\L21_V001\000001.jpg",
    )
    res_win = CustomKeyframeValidator(expected_keyframe_count=1, expected_video_count=1, video_registry=vreg).validate([bad_win])
    assert res_win.is_valid is False
    assert any("ABSOLUTE_PATH_FORBIDDEN" in err for err in res_win.errors)

    # POSIX absolute
    bad_posix = CustomKeyframeRecord(
        keyframe_uid="CUSTOM:L21_V001:F1",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        frame_idx=1,
        timestamp_ms=33,
        raw_pts_time=0.033,
        shot_id=0,
        cluster_id=0,
        embedding_index=0,
        source_keyframe_id=1,
        file_name="000001.jpg",
        image_relpath="/content/drive/MyDrive/000001.jpg",
    )
    res_posix = CustomKeyframeValidator(expected_keyframe_count=1, expected_video_count=1, video_registry=vreg).validate([bad_posix])
    assert res_posix.is_valid is False
    assert any("ABSOLUTE_PATH_FORBIDDEN" in err for err in res_posix.errors)

    # Path traversal
    bad_trav = CustomKeyframeRecord(
        keyframe_uid="CUSTOM:L21_V001:F1",
        video_id="L21_V001",
        video_ordinal=0,
        ordinal_space_id="v1_natural_series_video",
        frame_idx=1,
        timestamp_ms=33,
        raw_pts_time=0.033,
        shot_id=0,
        cluster_id=0,
        embedding_index=0,
        source_keyframe_id=1,
        file_name="000001.jpg",
        image_relpath="output/../secret/000001.jpg",
    )
    res_trav = CustomKeyframeValidator(expected_keyframe_count=1, expected_video_count=1, video_registry=vreg).validate([bad_trav])
    assert res_trav.is_valid is False
    assert any("PATH_TRAVERSAL_FORBIDDEN" in err for err in res_trav.errors)


def test_empty_semantic_arrays_are_valid_ok():
    """A valid completed observation with all semantic fields empty is still classified as OK."""
    vreg = _create_mock_video_registry()
    custom_items = [
        {"video_id": "L21_V001", "frame_idx": 15, "pts_time": 0.5, "keyframe_id": 1, "file_name": "000001.jpg", "image_path": "output/keyframes/L21_V001/000001.jpg"}
    ]
    qwen_items = [
        {"video_id": "L21_V001", "frame_idx": 15, "pts_time": 0.5, "objects": [], "attributes": [], "spatial_relations": [], "counts": [], "scene": [], "visible_actions": [], "caption": ""}
    ]
    c_rec, q_rec, m_rec = build_custom_and_qwen_records(custom_items, qwen_items, vreg)
    assert len(c_rec) == 1
    assert c_rec[0].qwen_status == "OK"
    assert len(q_rec) == 1
    assert len(m_rec) == 0


def test_complete_1_to_1_coverage_zero_missing():
    """When all custom keyframes have corresponding Qwen entries in the shard, missing count is 0."""
    vreg = _create_mock_video_registry()
    custom_items = [
        {"video_id": "L21_V001", "frame_idx": 15, "pts_time": 0.5, "keyframe_id": 1, "file_name": "000001.jpg", "image_path": "output/keyframes/L21_V001/000001.jpg"},
        {"video_id": "L21_V002", "frame_idx": 30, "pts_time": 1.0, "keyframe_id": 1, "file_name": "000001.jpg", "image_path": "output/keyframes/L21_V002/000001.jpg"},
    ]
    qwen_items = [
        {"video_id": "L21_V001", "frame_idx": 15, "pts_time": 0.5, "caption": "first"},
        {"video_id": "L21_V002", "frame_idx": 30, "pts_time": 1.0, "caption": "second"},
    ]
    c_rec, q_rec, m_rec = build_custom_and_qwen_records(custom_items, qwen_items, vreg)
    assert len(c_rec) == 2
    assert len(q_rec) == 2
    assert len(m_rec) == 0
    assert all(r.qwen_status == "OK" for r in c_rec)


def test_accounting_valid_plus_missing_equals_total(tmp_path: Path):
    """Verify Valid + Missing == Total custom keyframes accounting invariant."""
    vreg = _create_mock_video_registry()
    custom_items, qwen_items = _create_mock_custom_and_qwen_items()
    c_rec, q_rec, m_rec = build_custom_and_qwen_records(custom_items, qwen_items, vreg)

    assert len(q_rec) + len(m_rec) == len(c_rec)
    res = CustomKeyframeValidator(expected_keyframe_count=4, expected_video_count=3, video_registry=vreg).validate(c_rec, q_rec, m_rec)
    assert res.is_valid is True

