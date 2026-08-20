"""Unit tests for BTC Objects Retrieval HTTP Endpoints (M5D)."""
import json
import sqlite3
import tempfile
from http import HTTPStatus
from pathlib import Path

import pytest
from aic2026.retrieval.providers.btc_objects import BtcObjectsProvider
from aic2026.search.api import AsrSearchApi


@pytest.fixture
def mock_api():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "btc_objects_postings.sqlite"
        classes_path = tmp_path / "classes.json"
        passport_path = tmp_path / "btc_objects_passport.json"
        dummy_mapping = tmp_path / "mapping.sqlite"
        dummy_mapping.touch()

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

            INSERT INTO class_dictionary VALUES
            (1, '/m/01g317', 'Person', '84', 'person', 2, 2, 0.95, 0.50),
            (2, '/m/0k4j', 'Car', '12', 'car', 1, 1, 0.85, 0.85);

            INSERT INTO object_postings VALUES
            (1, 1, 'BTC:L21_V001:KF000001', 'L21_V001', 1, 0, 0, 0.95, 1, '[0.1,0.2,0.8,0.9]', '[{"score": 0.95, "bbox": [0.1,0.2,0.8,0.9], "label": "84"}]'),
            (2, 1, 'BTC:L21_V002:KF000001', 'L21_V002', 1, 0, 0, 0.80, 1, '[0.2,0.2,0.7,0.7]', '[{"score": 0.80, "bbox": [0.2,0.2,0.7,0.7], "label": "84"}]'),
            (3, 2, 'BTC:L21_V001:KF000001', 'L21_V001', 1, 0, 0, 0.85, 1, '[0.3,0.3,0.6,0.6]', '[{"score": 0.85, "bbox": [0.3,0.3,0.6,0.6], "label": "12"}]');
        """)
        conn.close()

        classes_data = [
            {"class_id": 1, "class_name": "/m/01g317", "class_entity": "Person", "class_label": "84", "class_norm": "person", "frame_count": 2, "detection_count": 2, "max_score": 0.95, "min_score": 0.50},
            {"class_id": 2, "class_name": "/m/0k4j", "class_entity": "Car", "class_label": "12", "class_norm": "car", "frame_count": 1, "detection_count": 1, "max_score": 0.85, "min_score": 0.85},
        ]
        with open(classes_path, "w", encoding="utf-8") as fp:
            json.dump(classes_data, fp)

        with open(passport_path, "w", encoding="utf-8") as fp:
            json.dump({"status": "OK"}, fp)

        provider = BtcObjectsProvider(artifact_dir=tmp_path)
        api = AsrSearchApi(dummy_mapping, btc_objects_provider=provider)
        yield api
        api.close()


def test_api_btc_objects_health(mock_api):
    status, payload = mock_api.btc_objects_health()
    assert status == HTTPStatus.OK
    assert payload["lane_id"] == "btc_objects"
    assert payload["status"] == "OK"
    assert payload["entity_type"] == "FRAME"
    assert payload["frame_space"] == "BTC"


def test_api_btc_objects_classes(mock_api):
    status, payload = mock_api.btc_objects_classes()
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["lane"] == "btc_objects"
    assert payload["count"] == 2
    assert payload["classes"][0]["class_norm"] == "person"


def test_api_btc_objects_search_single_class(mock_api):
    status, payload = mock_api.btc_objects_search({
        "classes": ["person"],
        "min_detector_score": 0.5,
        "top_k": 10,
    })
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["lane"] == "btc_objects"
    assert payload["count"] == 2
    assert payload["hits"][0]["video_id"] == "L21_V001"
    assert payload["hits"][0]["raw_score"] == 0.95


def test_api_btc_objects_search_multi_class_all(mock_api):
    status, payload = mock_api.btc_objects_search({
        "classes": ["person", "car"],
        "match_mode": "ALL",
        "min_detector_score": 0.5,
        "top_k": 10,
    })
    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["count"] == 1
    assert payload["hits"][0]["video_id"] == "L21_V001"
    assert payload["hits"][0]["raw_score"] == 0.85


def test_api_btc_objects_search_validation_errors(mock_api):
    # Missing classes
    status, payload = mock_api.btc_objects_search({})
    assert status == HTTPStatus.BAD_REQUEST

    # Empty classes
    status, payload = mock_api.btc_objects_search({"classes": []})
    assert status == HTTPStatus.BAD_REQUEST

    # Invalid match_mode
    status, payload = mock_api.btc_objects_search({"classes": ["person"], "match_mode": "INVALID"})
    assert status == HTTPStatus.BAD_REQUEST
