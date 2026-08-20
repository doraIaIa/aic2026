"""Unit tests for BTC Objects Retrieval Provider Lane (M5D)."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.btc_objects import (
    BtcObjectsProvider,
    BtcObjectsQuery,
)


@pytest.fixture
def mock_objects_artifact():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        dir_path = Path(tmp_dir)
        db_path = dir_path / "btc_objects_postings.sqlite"
        classes_path = dir_path / "classes.json"
        passport_path = dir_path / "btc_objects_passport.json"
        done_path = dir_path / "DONE.json"

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
            (1, '/m/01g317', 'Person', '84', 'person', 3, 5, 0.95, 0.30),
            (2, '/m/0k4j', 'Car', '12', 'car', 2, 2, 0.90, 0.40),
            (3, '/m/04_sv', 'Motorcycle', '150', 'motorcycle', 2, 2, 0.85, 0.50);

            -- Frame 1: Person (0.95), Motorcycle (0.85) in L21_V001
            INSERT INTO object_postings VALUES
            (1, 1, 'BTC:L21_V001:KF000001', 'L21_V001', 1, 0, 0, 0.95, 2, '[0.1,0.2,0.8,0.9]', '[{"score": 0.95, "bbox": [0.1,0.2,0.8,0.9], "label": "84"}]'),
            (2, 3, 'BTC:L21_V001:KF000001', 'L21_V001', 1, 0, 0, 0.85, 1, '[0.3,0.4,0.7,0.8]', '[{"score": 0.85, "bbox": [0.3,0.4,0.7,0.8], "label": "150"}]');

            -- Frame 2: Person (0.80), Car (0.90) in L21_V001
            INSERT INTO object_postings VALUES
            (3, 1, 'BTC:L21_V001:KF000002', 'L21_V001', 2, 25, 1000, 0.80, 1, '[0.2,0.2,0.6,0.6]', '[{"score": 0.80, "bbox": [0.2,0.2,0.6,0.6], "label": "84"}]'),
            (4, 2, 'BTC:L21_V001:KF000002', 'L21_V001', 2, 25, 1000, 0.90, 1, '[0.1,0.1,0.5,0.5]', '[{"score": 0.90, "bbox": [0.1,0.1,0.5,0.5], "label": "12"}]');

            -- Frame 3: Person (0.60), Motorcycle (0.75), Car (0.40) in L21_V002
            INSERT INTO object_postings VALUES
            (5, 1, 'BTC:L21_V002:KF000001', 'L21_V002', 1, 0, 0, 0.60, 2, '[0.0,0.0,1.0,1.0]', '[{"score": 0.60, "bbox": [0.0,0.0,1.0,1.0], "label": "84"}]'),
            (6, 3, 'BTC:L21_V002:KF000001', 'L21_V002', 1, 0, 0, 0.75, 1, '[0.2,0.2,0.8,0.8]', '[{"score": 0.75, "bbox": [0.2,0.2,0.8,0.8], "label": "150"}]'),
            (7, 2, 'BTC:L21_V002:KF000001', 'L21_V002', 1, 0, 0, 0.40, 1, '[0.5,0.5,0.9,0.9]', '[{"score": 0.40, "bbox": [0.5,0.5,0.9,0.9], "label": "12"}]');
        """)
        conn.close()

        classes_data = [
            {"class_id": 1, "class_name": "/m/01g317", "class_entity": "Person", "class_label": "84", "class_norm": "person", "frame_count": 3, "detection_count": 5, "max_score": 0.95, "min_score": 0.30},
            {"class_id": 2, "class_name": "/m/0k4j", "class_entity": "Car", "class_label": "12", "class_norm": "car", "frame_count": 2, "detection_count": 2, "max_score": 0.90, "min_score": 0.40},
            {"class_id": 3, "class_name": "/m/04_sv", "class_entity": "Motorcycle", "class_label": "150", "class_norm": "motorcycle", "frame_count": 2, "detection_count": 2, "max_score": 0.85, "min_score": 0.50},
        ]
        with open(classes_path, "w", encoding="utf-8") as fp:
            json.dump(classes_data, fp)

        passport_data = {
            "provider": "btc_objects",
            "lane_id": "btc_objects",
            "entity_type": "FRAME",
            "frame_space": "BTC",
            "score_type": "btc_object_support",
            "score_direction": "HIGHER_IS_BETTER",
            "build_id": "test_mock",
            "database_sha256": "mock_sha",
            "classes_sha256": "mock_sha",
        }
        with open(passport_path, "w", encoding="utf-8") as fp:
            json.dump(passport_data, fp)

        with open(done_path, "w", encoding="utf-8") as fp:
            json.dump({"status": "COMPLETED"}, fp)

        yield dir_path


def test_provider_health_and_capabilities(mock_objects_artifact):
    provider = BtcObjectsProvider(artifact_dir=mock_objects_artifact)
    try:
        cap = provider.capabilities()
        assert cap.status == "OK"
        assert cap.provider == "btc_objects"
        assert cap.counts["indexed_classes"] == 3
        assert cap.counts["total_postings"] == 7

        h = provider.health()
        assert h["lane_id"] == "btc_objects"
        assert h["frame_space"] == "BTC"
        assert h["entity_type"] == "FRAME"
        assert h["score_type"] == "btc_object_support"
        assert h["score_direction"] == "HIGHER_IS_BETTER"
    finally:
        provider.close()


def test_single_class_search(mock_objects_artifact):
    provider = BtcObjectsProvider(artifact_dir=mock_objects_artifact)
    try:
        hits = provider.search_objects(BtcObjectsQuery(
            classes=["person"],
            match_mode="ALL",
            min_detector_score=0.1,
            top_k=10,
        ))
        assert len(hits) == 3
        assert hits[0].video_id == "L21_V001"
        assert hits[0].payload["keyframe_uid"] == "BTC:L21_V001:KF000001"
        assert hits[0].raw_score == 0.95
        assert hits[0].payload["matched_classes"] == ["Person"]
        assert hits[0].payload["top_bboxes"]["Person"] == [0.1, 0.2, 0.8, 0.9]
    finally:
        provider.close()


def test_multi_class_all_mode(mock_objects_artifact):
    provider = BtcObjectsProvider(artifact_dir=mock_objects_artifact)
    try:
        hits = provider.search_objects(BtcObjectsQuery(
            classes=["person", "motorcycle"],
            match_mode="ALL",
            min_detector_score=0.1,
            top_k=10,
        ))
        assert len(hits) == 2
        assert hits[0].payload["keyframe_uid"] == "BTC:L21_V001:KF000001"
        assert hits[0].raw_score == 0.85
        assert set(hits[0].payload["matched_classes"]) == {"Person", "Motorcycle"}

        assert hits[1].payload["keyframe_uid"] == "BTC:L21_V002:KF000001"
        assert hits[1].raw_score == 0.60
    finally:
        provider.close()


def test_multi_class_any_mode(mock_objects_artifact):
    provider = BtcObjectsProvider(artifact_dir=mock_objects_artifact)
    try:
        hits = provider.search_objects(BtcObjectsQuery(
            classes=["car", "motorcycle"],
            match_mode="ANY",
            min_detector_score=0.1,
            top_k=10,
        ))
        assert len(hits) == 3
        assert hits[0].payload["keyframe_uid"] == "BTC:L21_V001:KF000002"
        assert hits[0].raw_score == 0.90
        assert hits[1].payload["keyframe_uid"] == "BTC:L21_V001:KF000001"
        assert hits[1].raw_score == 0.85
        assert hits[2].payload["keyframe_uid"] == "BTC:L21_V002:KF000001"
        assert hits[2].raw_score == 0.75
    finally:
        provider.close()


def test_min_detector_score_filtering(mock_objects_artifact):
    provider = BtcObjectsProvider(artifact_dir=mock_objects_artifact)
    try:
        hits_low = provider.search_objects(BtcObjectsQuery(classes=["car"], min_detector_score=0.3))
        assert len(hits_low) == 2

        hits_high = provider.search_objects(BtcObjectsQuery(classes=["car"], min_detector_score=0.5))
        assert len(hits_high) == 1
        assert hits_high[0].payload["keyframe_uid"] == "BTC:L21_V001:KF000002"
    finally:
        provider.close()


def test_candidate_video_ids_scope(mock_objects_artifact):
    provider = BtcObjectsProvider(artifact_dir=mock_objects_artifact)
    try:
        hits = provider.search_objects(BtcObjectsQuery(
            classes=["person"],
            candidate_video_ids=["L21_V002"],
        ))
        assert len(hits) == 1
        assert hits[0].video_id == "L21_V002"

        hits_empty = provider.search_objects(BtcObjectsQuery(
            classes=["person"],
            candidate_video_ids=[],
        ))
        assert len(hits_empty) == 0

        hits_none = provider.search_objects(BtcObjectsQuery(
            classes=["person"],
            candidate_video_ids=["NON_EXISTENT_VIDEO"],
        ))
        assert len(hits_none) == 0
    finally:
        provider.close()


def test_unknown_class_fail_closed(mock_objects_artifact):
    provider = BtcObjectsProvider(artifact_dir=mock_objects_artifact)
    try:
        hits_all = provider.search_objects(BtcObjectsQuery(
            classes=["person", "unknown_alien_object_xyz"],
            match_mode="ALL",
        ))
        assert len(hits_all) == 0

        hits_any = provider.search_objects(BtcObjectsQuery(
            classes=["person", "unknown_alien_object_xyz"],
            match_mode="ANY",
        ))
        assert len(hits_any) == 3
    finally:
        provider.close()


def test_no_hidden_query_intelligence(mock_objects_artifact):
    provider = BtcObjectsProvider(artifact_dir=mock_objects_artifact)
    try:
        assert provider.resolve_class("motorbike") is None
        assert provider.resolve_class("human") is None

        assert provider.resolve_class("Person")["class_norm"] == "person"
        assert provider.resolve_class("/m/01g317")["class_norm"] == "person"
        assert provider.resolve_class("person")["class_norm"] == "person"
    finally:
        provider.close()
