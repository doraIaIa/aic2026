from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest

from aic2026.data_hub.runtime_hub import RuntimeDataHub


@pytest.fixture
def test_db_hub(tmp_path: Path) -> RuntimeDataHub:
    db_path = tmp_path / "test_timeline.sqlite"
    schema_path = Path(__file__).resolve().parent.parent / "src" / "aic2026" / "db" / "schema.sql"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    c = conn.cursor()
    # Insert video
    c.execute(
        """
        INSERT INTO videos(video_id, ordinal, ordinal_space_id, series, relpath, duration_ms, duration_sec)
        VALUES ('L21_V001', 0, 'v1_natural_series_video', 'L21', 'videos/L21/L21_V001.mp4', 60000, 60.0)
        """
    )

    # Insert BTC keyframes at 1000ms, 5000ms, 10000ms
    c.execute(
        """
        INSERT INTO btc_keyframes(
            keyframe_uid, video_id, video_ordinal, local_keyframe_no, frame_idx, timestamp_ms, raw_pts_time, fps, image_relpath
        ) VALUES
        ('BTC:L21_V001:KF000001', 'L21_V001', 0, 1, 25, 1000, 1.0, 25.0, 'img/1.jpg'),
        ('BTC:L21_V001:KF000002', 'L21_V001', 0, 2, 125, 5000, 5.0, 25.0, 'img/2.jpg'),
        ('BTC:L21_V001:KF000003', 'L21_V001', 0, 3, 250, 10000, 10.0, 25.0, 'img/3.jpg')
        """
    )

    # Insert CUSTOM keyframes at 1200ms, 4800ms, 9500ms
    c.execute(
        """
        INSERT INTO custom_keyframes(
            keyframe_uid, video_id, video_ordinal, frame_idx, timestamp_ms, raw_pts_time, file_name, image_relpath
        ) VALUES
        ('CUSTOM:L21_V001:F0030', 'L21_V001', 0, 30, 1200, 1.2, '30.jpg', 'img/30.jpg'),
        ('CUSTOM:L21_V001:F0120', 'L21_V001', 0, 120, 4800, 4.8, '120.jpg', 'img/120.jpg'),
        ('CUSTOM:L21_V001:F0240', 'L21_V001', 0, 240, 9500, 9.5, '240.jpg', 'img/240.jpg')
        """
    )

    conn.commit()
    conn.close()

    hub = RuntimeDataHub(db_path)
    yield hub
    hub.close()


def test_nearest_keyframe_deterministic(test_db_hub: RuntimeDataHub):
    # Query exact match in BTC
    res = test_db_hub.nearest_keyframe("L21_V001", 5000, "BTC")
    assert res["status"] == "MATCHED"
    assert res["keyframe_uid"] == "BTC:L21_V001:KF000002"
    assert res["matched_timestamp_ms"] == 5000
    assert res["delta_ms"] == 0
    assert res["abs_delta_ms"] == 0
    assert res["relation_type"] == "DERIVED_ASSOCIATION"

    # Query offset in CUSTOM: 4900ms -> nearest is 4800ms
    res_c = test_db_hub.nearest_keyframe("L21_V001", 4900, "CUSTOM")
    assert res_c["status"] == "MATCHED"
    assert res_c["keyframe_uid"] == "CUSTOM:L21_V001:F0120"
    assert res_c["matched_timestamp_ms"] == 4800
    assert res_c["delta_ms"] == -100
    assert res_c["abs_delta_ms"] == 100


def test_nearest_keyframe_tie_breaking(tmp_path: Path):
    # Create DB with equidistant candidates: 2000ms vs 4000ms from target 3000ms
    db_path = tmp_path / "test_tie.sqlite"
    schema_path = Path(__file__).resolve().parent.parent / "src" / "aic2026" / "db" / "schema.sql"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    c = conn.cursor()
    c.execute("INSERT INTO videos(video_id, ordinal, series, relpath) VALUES ('L21_V001', 0, 'L21', 'v.mp4')")
    c.execute(
        """
        INSERT INTO btc_keyframes(keyframe_uid, video_id, video_ordinal, local_keyframe_no, frame_idx, timestamp_ms, raw_pts_time, fps, image_relpath)
        VALUES
        ('BTC:L21_V001:KF000001', 'L21_V001', 0, 1, 50, 2000, 2.0, 25.0, '1.jpg'),
        ('BTC:L21_V001:KF000002', 'L21_V001', 0, 2, 100, 4000, 4.0, 25.0, '2.jpg')
        """
    )
    conn.commit()
    conn.close()

    hub = RuntimeDataHub(db_path)
    # Target 3000ms: equidistant from 2000ms (delta=-1000) and 4000ms (delta=+1000)
    # Tie-break chooses earlier timestamp: 2000ms
    res = hub.nearest_keyframe("L21_V001", 3000, "BTC")
    assert res["matched_timestamp_ms"] == 2000
    assert res["keyframe_uid"] == "BTC:L21_V001:KF000001"
    assert res["delta_ms"] == -1000
    assert res["abs_delta_ms"] == 1000
    hub.close()


def test_compare_keyframe_spaces(test_db_hub: RuntimeDataHub):
    res = test_db_hub.compare_keyframe_spaces("L21_V001", 5000)
    assert res["requested_timestamp_ms"] == 5000
    assert res["btc"]["keyframe_uid"] == "BTC:L21_V001:KF000002"
    assert res["btc"]["delta_ms"] == 0
    assert res["custom"]["keyframe_uid"] == "CUSTOM:L21_V001:F0120"
    assert res["custom"]["delta_ms"] == -200


def test_nearest_other_space(test_db_hub: RuntimeDataHub):
    # From BTC KF2 (5000ms) -> nearest CUSTOM is F0120 (4800ms)
    other = test_db_hub.nearest_other_space("BTC:L21_V001:KF000002")
    assert other["frame_space"] == "CUSTOM"
    assert other["keyframe_uid"] == "CUSTOM:L21_V001:F0120"
    assert other["delta_ms"] == -200

    # From CUSTOM F0030 (1200ms) -> nearest BTC is KF000001 (1000ms)
    other_btc = test_db_hub.nearest_other_space("CUSTOM:L21_V001:F0030")
    assert other_btc["frame_space"] == "BTC"
    assert other_btc["keyframe_uid"] == "BTC:L21_V001:KF000001"
    assert other_btc["delta_ms"] == -200


def test_unknown_video_and_space_fails_closed(test_db_hub: RuntimeDataHub):
    with pytest.raises(ValueError, match="Unknown video_id"):
        test_db_hub.nearest_keyframe("UNKNOWN_VID", 1000, "BTC")

    with pytest.raises(ValueError, match="Invalid frame_space"):
        test_db_hub.nearest_keyframe("L21_V001", 1000, "INVALID_SPACE")
