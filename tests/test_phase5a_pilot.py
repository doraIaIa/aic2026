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
