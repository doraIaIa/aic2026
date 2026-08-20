"""Unit tests for BTC Objects Index Builder and Normalization (M5D)."""
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest
from aic2026.retrieval.btc_objects_index import (
    BtcClassInfo,
    build_btc_objects_index,
    compute_sha256,
    normalize_class_label,
)


def test_normalize_class_label():
    assert normalize_class_label("Person") == "person"
    assert normalize_class_label("  Traffic   light  ") == "traffic light"
    assert normalize_class_label("LAND VEHICLE") == "land vehicle"
    assert normalize_class_label("") == ""
    assert normalize_class_label(None) == ""


def test_build_btc_objects_index_synthetic():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # 1. Create mock mapping.sqlite
        mock_mapping_db = tmp_path / "mapping.sqlite"
        conn = sqlite3.connect(mock_mapping_db)
        conn.executescript("""
            CREATE TABLE btc_keyframes (
                keyframe_uid TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                video_ordinal INTEGER NOT NULL,
                ordinal_space_id TEXT NOT NULL,
                local_keyframe_no INTEGER NOT NULL,
                frame_idx INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                raw_pts_time REAL NOT NULL,
                fps REAL NOT NULL,
                image_relpath TEXT NOT NULL,
                frame_space TEXT NOT NULL,
                btc_space_id TEXT NOT NULL,
                map_source_id TEXT NOT NULL,
                clip_status TEXT NOT NULL,
                object_status TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO btc_keyframes VALUES
            ('BTC:L21_V001:KF000001', 'L21_V001', 0, 'v1_natural_series_video', 1, 0, 0, 0.0, 25.0, 'img1.jpg', 'BTC', 'btc_keyframes_v1', 'map_v1', 'HAS_CLIP_ROW', 'HAS_OBJECTS', 'v1', 'now'),
            ('BTC:L21_V001:KF000002', 'L21_V001', 0, 'v1_natural_series_video', 2, 25, 1000, 1.0, 25.0, 'img2.jpg', 'BTC', 'btc_keyframes_v1', 'map_v1', 'HAS_CLIP_ROW', 'HAS_OBJECTS', 'v1', 'now');
        """)
        conn.close()

        # 2. Create mock zip file
        mock_zip = tmp_path / "objects.zip"
        with zipfile.ZipFile(mock_zip, "w") as zf:
            kf1_data = {
                "detection_scores": ["0.95", "0.80", "0.40"],
                "detection_class_names": ["/m/01g317", "/m/0k4j", "/m/01g317"],
                "detection_class_entities": ["Person", "Car", "Person"],
                "detection_class_labels": ["84", "12", "84"],
                "detection_boxes": [
                    ["0.1", "0.2", "0.8", "0.9"],
                    ["0.2", "0.3", "0.6", "0.7"],
                    ["0.3", "0.4", "0.5", "0.6"],
                ]
            }
            kf2_data = {
                "detection_scores": ["0.70"],
                "detection_class_names": ["/m/0k4j"],
                "detection_class_entities": ["Car"],
                "detection_class_labels": ["12"],
                "detection_boxes": [["0.0", "0.0", "1.0", "1.0"]]
            }
            zf.writestr("objects/L21_V001/001.json", json.dumps(kf1_data))
            zf.writestr("objects/L21_V001/002.json", json.dumps(kf2_data))

        # 3. Build index
        out_dir = tmp_path / "output_index"
        res = build_btc_objects_index(
            output_dir=out_dir,
            zip_path=mock_zip,
            mapping_db=mock_mapping_db,
            build_id="test_build_01",
        )

        assert res["frames"] == 2
        assert res["detections"] == 4
        assert res["classes"] == 2
        assert res["postings"] == 3  # (kf1, person), (kf1, car), (kf2, car)

        # 4. Verify SQLite contents
        db_file = out_dir / "btc_objects_postings.sqlite"
        assert db_file.exists()
        c_conn = sqlite3.connect(db_file)
        c_conn.row_factory = sqlite3.Row
        
        classes = c_conn.execute("SELECT * FROM class_dictionary ORDER BY class_id").fetchall()
        assert len(classes) == 2
        assert classes[0]["class_entity"] == "Person"
        assert classes[0]["class_norm"] == "person"
        assert classes[0]["frame_count"] == 1
        assert classes[0]["detection_count"] == 2
        assert classes[0]["max_score"] == 0.95

        postings = c_conn.execute("SELECT * FROM object_postings ORDER BY posting_id").fetchall()
        assert len(postings) == 3
        c_conn.close()

        # 5. Check manifest and passport
        assert (out_dir / "manifest.json").exists()
        assert (out_dir / "btc_objects_passport.json").exists()
        assert (out_dir / "DONE.json").exists()
        assert (out_dir / "classes.json").exists()
