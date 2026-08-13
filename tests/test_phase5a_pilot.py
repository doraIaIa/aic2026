import pytest
from pathlib import Path
import json
from aic2026.evaluation.apply_verification import validate_exact_decision, validate_video_decision, apply_verifications

def test_validate_exact_decision_valid():
    base_label = {"query_type": "KIS"}
    dec = {
        "decision": "VERIFIED",
        "video_id": "L25_V058",
        "start_frame_id": 100,
        "representative_frame_id": 110,
        "end_frame_id": 120
    }
    validate_exact_decision(dec, base_label)

def test_validate_exact_decision_invalid_range():
    base_label = {"query_type": "KIS"}
    dec = {
        "decision": "VERIFIED",
        "video_id": "L25_V058",
        "start_frame_id": 120,
        "representative_frame_id": 110,
        "end_frame_id": 100
    }
    with pytest.raises(ValueError):
        validate_exact_decision(dec, base_label)

def test_validate_video_decision_valid():
    base_label = {"query_type": "KIS"}
    dec = {
        "decision": "VIDEO_VERIFIED",
        "video_id": "L25_V058"
    }
    validate_video_decision(dec, base_label)

def test_invalid_video_id_rejected():
    base_label = {"query_type": "KIS"}
    dec = {"decision": "VIDEO_VERIFIED", "video_id": ""}
    with pytest.raises(ValueError):
        validate_video_decision(dec, base_label)

    dec2 = {"decision": "VIDEO_VERIFIED"}
    with pytest.raises(ValueError):
        validate_video_decision(dec2, base_label)

class MockMediaResolver:
    def _validate_video_id(self, video_id: str):
        if not video_id or ".." in video_id or video_id.startswith("/"):
            raise ValueError("Invalid format")
    def is_available(self, video_id: str):
        return True

def test_validate_video_decision_with_resolver():
    base_label = {"query_type": "KIS"}
    resolver = MockMediaResolver()

    with pytest.raises(ValueError):
        validate_video_decision({"decision": "VIDEO_VERIFIED", "video_id": "../secret"}, base_label, resolver)

    with pytest.raises(ValueError):
        validate_video_decision({"decision": "VIDEO_VERIFIED", "video_id": "/absolute/path"}, base_label, resolver)

    validate_video_decision({"decision": "VIDEO_VERIFIED", "video_id": "L01_V001"}, base_label, resolver)
