"""Unit tests for BTC Objects Benchmark Suite (M5D)."""
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest
from aic2026.evaluation.btc_objects_benchmark import (
    run_btc_objects_benchmark,
    run_class_validation_probes,
    run_scope_probes,
    run_single_class_probes,
    run_threshold_probes,
)
from aic2026.retrieval.providers.btc_objects import BtcObjectsProvider


@pytest.fixture
def mock_benchmark_env():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_path = Path(tmp_dir)
        art_dir = tmp_path / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        db_path = art_dir / "btc_objects_postings.sqlite"
        classes_path = art_dir / "classes.json"
        passport_path = art_dir / "btc_objects_passport.json"

        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE class_dictionary (
                class_id INTEGER PRIMARY KEY,
                class_name TEXT NOT NULL,
                class_entity TEXT NOT NULL,
                class_label TEXT NOT NULL,
                class_norm TEXT NOT NULL UNIQUE,
                frame_count INTEGER NOT NULL,
                detection_count INTEGER NOT NULL,
                max_score REAL NOT NULL,
                min_score REAL NOT NULL
            );

            CREATE TABLE object_postings (
                posting_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL,
                keyframe_uid TEXT NOT NULL,
                video_id TEXT NOT NULL,
                local_keyframe_no INTEGER NOT NULL,
                frame_idx INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                max_score REAL NOT NULL,
                detection_count INTEGER NOT NULL,
                top_bbox_json TEXT NOT NULL,
                top_detections_json TEXT NOT NULL
            );

            CREATE INDEX idx_postings_class_score ON object_postings(class_id, max_score DESC);
            CREATE INDEX idx_postings_class_video ON object_postings(class_id, video_id, max_score DESC);
            CREATE INDEX idx_postings_kf ON object_postings(keyframe_uid);
            CREATE INDEX idx_class_dict_norm ON class_dictionary(class_norm);

            INSERT INTO class_dictionary VALUES
            (1, '/m/01g317', 'Person', '84', 'person', 2, 2, 0.95, 0.50),
            (2, '/m/0k4j', 'Car', '12', 'car', 2, 2, 0.85, 0.40),
            (3, '/m/04_sv', 'Motorcycle', '150', 'motorcycle', 2, 2, 0.90, 0.60);

            INSERT INTO object_postings VALUES
            (1, 1, 'BTC:L21_V001:KF000001', 'L21_V001', 1, 0, 0, 0.95, 1, '[0.1,0.2,0.8,0.9]', '[{"score": 0.95, "bbox": [0.1,0.2,0.8,0.9], "label": "84"}]'),
            (2, 2, 'BTC:L21_V001:KF000001', 'L21_V001', 1, 0, 0, 0.85, 1, '[0.2,0.2,0.6,0.6]', '[{"score": 0.85, "bbox": [0.2,0.2,0.6,0.6], "label": "12"}]'),
            (3, 3, 'BTC:L21_V001:KF000001', 'L21_V001', 1, 0, 0, 0.90, 1, '[0.3,0.3,0.7,0.7]', '[{"score": 0.90, "bbox": [0.3,0.3,0.7,0.7], "label": "150"}]'),
            (4, 1, 'BTC:L21_V002:KF000001', 'L21_V002', 1, 0, 0, 0.50, 1, '[0.0,0.0,1.0,1.0]', '[{"score": 0.50, "bbox": [0.0,0.0,1.0,1.0], "label": "84"}]'),
            (5, 2, 'BTC:L21_V002:KF000001', 'L21_V002', 1, 0, 0, 0.40, 1, '[0.4,0.4,0.8,0.8]', '[{"score": 0.40, "bbox": [0.4,0.4,0.8,0.8], "label": "12"}]'),
            (6, 3, 'BTC:L21_V002:KF000001', 'L21_V002', 1, 0, 0, 0.60, 1, '[0.5,0.5,0.9,0.9]', '[{"score": 0.60, "bbox": [0.5,0.5,0.9,0.9], "label": "150"}]');
        """)
        conn.close()

        classes_data = [
            {"class_id": 1, "class_name": "/m/01g317", "class_entity": "Person", "class_label": "84", "class_norm": "person", "frame_count": 2, "detection_count": 2, "max_score": 0.95, "min_score": 0.50},
            {"class_id": 2, "class_name": "/m/0k4j", "class_entity": "Car", "class_label": "12", "class_norm": "car", "frame_count": 2, "detection_count": 2, "max_score": 0.85, "min_score": 0.40},
            {"class_id": 3, "class_name": "/m/04_sv", "class_entity": "Motorcycle", "class_label": "150", "class_norm": "motorcycle", "frame_count": 2, "detection_count": 2, "max_score": 0.90, "min_score": 0.60},
        ]
        with open(classes_path, "w", encoding="utf-8") as fp:
            json.dump(classes_data, fp)

        passport_data = {"status": "OK", "build_id": "test_bench"}
        with open(passport_path, "w", encoding="utf-8") as fp:
            json.dump(passport_data, fp)

        yield art_dir


def test_scope_and_threshold_probes(mock_benchmark_env):
    provider = BtcObjectsProvider(artifact_dir=mock_benchmark_env)
    try:
        scope_results = run_scope_probes(provider)
        assert all(r["status"] == "PASS" for r in scope_results)

        valid_results = run_class_validation_probes(provider)
        assert all(r["status"] == "PASS" for r in valid_results)
    finally:
        provider.close()
