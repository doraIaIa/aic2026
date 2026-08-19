from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import pytest

from aic2026.data_hub.runtime_hub import RuntimeDataHub


@pytest.fixture
def mock_full_hub(tmp_path: Path) -> RuntimeDataHub:
    db_path = tmp_path / "test_drilldown.sqlite"
    schema_path = Path(__file__).resolve().parent.parent / "src" / "aic2026" / "db" / "schema.sql"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    c = conn.cursor()
    # Videos
    c.execute(
        """
        INSERT INTO videos(video_id, ordinal, series, relpath, duration_ms, duration_sec)
        VALUES
        ('L21_V001', 0, 'L21', 'videos/L21/L21_V001.mp4', 60000, 60.0),
        ('L30_V096', 1, 'L30', 'videos/L30/L30_V096.mp4', 30000, 30.0),
        ('L30_V029', 2, 'L30', 'videos/L30/L30_V029.mp4', 40000, 40.0)
        """
    )

    # Media Info
    c.execute(
        """
        INSERT INTO media_info(video_id, video_ordinal, title, keywords_json)
        VALUES
        ('L21_V001', 0, '60 Giay Sang', '["60s", "news"]'),
        ('L30_V096', 1, 'Trailer Cuoc Thi', '["trailer"]'),
        ('L30_V029', 2, 'Clip Khong Loi', '[]')
        """
    )

    # Taxonomy nodes & memberships
    c.execute(
        """
        INSERT INTO taxonomy_nodes(branch_id, branch_type, label_vi, label_en)
        VALUES
        ('program/news', 'PROGRAM', 'Thời sự', 'News'),
        ('program/positive-community-local-life-feature', 'PROGRAM', 'Đời sống', 'Community')
        """
    )
    c.execute(
        """
        INSERT INTO video_memberships(membership_id, video_id, branch_id, membership_type, status, confidence, evidence)
        VALUES
        ('L21_V001#program/news', 'L21_V001', 'program/news', 'PRIMARY_PROGRAM', 'VERIFIED', 0.99, 'News ASR'),
        ('L30_V096#program/positive-community-local-life-feature', 'L30_V096', 'program/positive-community-local-life-feature', 'PRIMARY_PROGRAM', 'OUTLIER', 0.50, 'Promotional meta clip'),
        ('L30_V029#program/positive-community-local-life-feature', 'L30_V029', 'program/positive-community-local-life-feature', 'PRIMARY_PROGRAM', 'INFERRED', 0.58, 'Zero ASR')
        """
    )

    # ASR Video Coverage & Segments
    c.execute(
        """
        INSERT INTO asr_video_coverage(video_id, video_ordinal, segment_count, duration_sec, duration_ms, asr_status)
        VALUES
        ('L21_V001', 0, 1, 60.0, 60000, 'HAS_SEGMENTS'),
        ('L30_V096', 1, 1, 30.0, 30000, 'HAS_SEGMENTS'),
        ('L30_V029', 2, 0, 40.0, 40000, 'ZERO_ASR_SEGMENTS')
        """
    )
    c.execute(
        """
        INSERT INTO canonical_asr_segments(segment_uid, source_segment_id, video_id, video_ordinal, start_ms, end_ms, start_sec, end_sec, text_raw, text_norm)
        VALUES
        ('ASR:L21_V001:0001', '0001', 'L21_V001', 0, 1000, 4000, 1.0, 4.0, 'Bản tin chiều nay', 'Bản tin chiều nay'),
        ('ASR:L30_V096:0001', '0001', 'L30_V096', 1, 500, 2500, 0.5, 2.5, 'Trailer giới thiệu', 'Trailer giới thiệu')
        """
    )

    # Keyframes BTC
    c.execute(
        """
        INSERT INTO btc_keyframes(keyframe_uid, video_id, video_ordinal, local_keyframe_no, frame_idx, timestamp_ms, raw_pts_time, fps, image_relpath)
        VALUES ('BTC:L21_V001:KF000001', 'L21_V001', 0, 1, 25, 1000, 1.0, 25.0, 'btc1.jpg')
        """
    )
    c.execute(
        """
        INSERT INTO btc_clip_rows(video_id, video_ordinal, row_in_video, keyframe_uid, local_keyframe_no, frame_idx, timestamp_ms, feature_relpath)
        VALUES ('L21_V001', 0, 0, 'BTC:L21_V001:KF000001', 1, 25, 1000, 'feat.npy')
        """
    )
    c.execute(
        """
        INSERT INTO btc_object_coverage(keyframe_uid, video_id, video_ordinal, local_keyframe_no, frame_idx, timestamp_ms, detection_count, object_status, source_file_relpath)
        VALUES ('BTC:L21_V001:KF000001', 'L21_V001', 0, 1, 25, 1000, 100, 'HAS_OBJECTS', 'obj.json')
        """
    )

    # Keyframes CUSTOM
    c.execute(
        """
        INSERT INTO custom_keyframes(keyframe_uid, video_id, video_ordinal, frame_idx, timestamp_ms, raw_pts_time, file_name, image_relpath)
        VALUES ('CUSTOM:L21_V001:F0025', 'L21_V001', 0, 25, 1000, 1.0, '25.jpg', 'img25.jpg')
        """
    )
    c.execute(
        """
        INSERT INTO qwen_frames(keyframe_uid, video_id, frame_idx, timestamp_ms, raw_pts_time, caption)
        VALUES ('CUSTOM:L21_V001:F0025', 'L21_V001', 25, 1000, 1.0, 'Người dẫn chương trình đọc bản tin')
        """
    )
    c.execute(
        """
        INSERT INTO ocr_keyframes(keyframe_uid, video_id, video_ordinal, frame_idx, timestamp_ms, raw_pts_time, file_name, image_relpath)
        VALUES ('CUSTOM:L21_V001:F0025', 'L21_V001', 0, 25, 1000, 1.0, '25.jpg', 'img25.jpg')
        """
    )
    c.execute(
        """
        INSERT INTO ocr_items(ocr_uid, video_id, video_ordinal, keyframe_uid, frame_idx, timestamp_ms, raw_pts_time, local_text_index, text_raw, text_norm, ocr_confidence)
        VALUES ('OCR:CUSTOM:L21_V001:F0025:T0', 'L21_V001', 0, 'CUSTOM:L21_V001:F0025', 25, 1000, 1.0, 0, 'THỜI SỰ', 'THỜI SỰ', 0.45)
        """
    )

    conn.commit()
    conn.close()

    hub = RuntimeDataHub(db_path)
    yield hub
    hub.close()


def test_video_drilldown_structure_and_counts(mock_full_hub: RuntimeDataHub):
    dd = mock_full_hub.get_video_drilldown("L21_V001")
    assert dd["video"]["video_id"] == "L21_V001"
    assert dd["media_info"]["title"] == "60 Giay Sang"
    assert len(dd["memberships"]) == 1
    assert dd["memberships"][0]["status"] == "VERIFIED"
    assert dd["asr"]["status"] == "HAS_SEGMENTS"
    assert dd["asr"]["actual_segment_count"] == 1
    assert dd["btc"]["keyframe_count"] == 1
    assert dd["btc"]["clip_row_count"] == 1
    assert dd["btc"]["object_coverage_count"] == 1
    assert dd["custom"]["keyframe_count"] == 1
    assert dd["custom"]["qwen_coverage_count"] == 1
    assert dd["custom"]["ocr_item_count"] == 1


def test_rich_frame_drilldown_btc(mock_full_hub: RuntimeDataHub):
    f_dd = mock_full_hub.get_frame_drilldown("BTC:L21_V001:KF000001")
    assert f_dd["frame_space"] == "BTC"
    assert f_dd["video_id"] == "L21_V001"
    assert f_dd["clip_row"] is not None
    assert f_dd["object_coverage"]["object_status"] == "HAS_OBJECTS"
    assert len(f_dd["nearby_asr"]) == 1
    assert f_dd["nearest_other_space"]["keyframe_uid"] == "CUSTOM:L21_V001:F0025"
    assert f_dd["nearest_other_space"]["delta_ms"] == 0


def test_rich_frame_drilldown_custom(mock_full_hub: RuntimeDataHub):
    f_dd = mock_full_hub.get_frame_drilldown("CUSTOM:L21_V001:F0025")
    assert f_dd["frame_space"] == "CUSTOM"
    assert f_dd["video_id"] == "L21_V001"
    assert "người dẫn chương trình" in f_dd["qwen_semantic"]["caption"].lower()
    assert len(f_dd["ocr_items"]) == 1
    assert f_dd["ocr_items"][0]["text_raw"] == "THỜI SỰ"
    assert f_dd["nearest_other_space"]["keyframe_uid"] == "BTC:L21_V001:KF000001"
    assert f_dd["nearest_other_space"]["delta_ms"] == 0


def test_special_status_preservation(mock_full_hub: RuntimeDataHub):
    # ZERO_ASR preservation
    z_dd = mock_full_hub.get_video_drilldown("L30_V029")
    assert z_dd["asr"]["status"] == "ZERO_ASR_SEGMENTS"
    assert z_dd["asr"]["actual_segment_count"] == 0
    assert z_dd["memberships"][0]["status"] == "INFERRED"

    # OUTLIER taxonomy status preservation
    o_dd = mock_full_hub.get_video_drilldown("L30_V096")
    assert o_dd["memberships"][0]["status"] == "OUTLIER"

    # Low confidence OCR preservation
    ocr_items = mock_full_hub.get_ocr_for_keyframe("CUSTOM:L21_V001:F0025")
    assert len(ocr_items) == 1
    assert ocr_items[0]["ocr_confidence"] == 0.45
