"""Unit tests for NearestKeyframeResolver."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from aic2026.media.nearest_keyframe import NearestKeyframeResolver


@pytest.fixture
def tmp_rowmaps(tmp_path: Path):
    custom_file = tmp_path / "custom_rowmap.jsonl"
    btc_file = tmp_path / "btc_rowmap.jsonl"

    # Write synthetic CUSTOM keyframes for video V1: 10s (10000ms), 20s (20000ms), 30s (30000ms)
    custom_lines = [
        {"video_id": "V1", "keyframe_uid": "CUSTOM:V1:F10", "frame_idx": 250, "timestamp_ms": 10000},
        {"video_id": "V1", "keyframe_uid": "CUSTOM:V1:F20", "frame_idx": 500, "timestamp_ms": 20000},
        {"video_id": "V1", "keyframe_uid": "CUSTOM:V1:F30", "frame_idx": 750, "timestamp_ms": 30000},
    ]
    with open(custom_file, "w", encoding="utf-8") as f:
        for item in custom_lines:
            f.write(json.dumps(item) + "\n")

    # Write synthetic BTC keyframes for video V1: 5s (5000ms), 15s (15000ms), 25s (25000ms)
    btc_lines = [
        {"video_id": "V1", "keyframe_uid": "BTC:V1:KF1", "frame_idx": 125, "timestamp_ms": 5000, "local_keyframe_no": 1},
        {"video_id": "V1", "keyframe_uid": "BTC:V1:KF2", "frame_idx": 375, "timestamp_ms": 15000, "local_keyframe_no": 2},
        {"video_id": "V1", "keyframe_uid": "BTC:V1:KF3", "frame_idx": 625, "timestamp_ms": 25000, "local_keyframe_no": 3},
    ]
    with open(btc_file, "w", encoding="utf-8") as f:
        for item in btc_lines:
            f.write(json.dumps(item) + "\n")

    return custom_file, btc_file


def test_nearest_keyframe_exact_match(tmp_rowmaps):
    custom_path, btc_path = tmp_rowmaps
    resolver = NearestKeyframeResolver(custom_path, btc_path)

    res = resolver.resolve_all_spaces("V1", 20000)
    assert res["video_id"] == "V1"
    assert res["target_ms"] == 20000

    # CUSTOM space exact match at 20000ms
    c = res["custom"]
    assert c["nearest_absolute"]["keyframe_uid"] == "CUSTOM:V1:F20"
    assert c["nearest_absolute"]["delta_ms"] == 0
    assert c["nearest_before"]["keyframe_uid"] == "CUSTOM:V1:F20"
    assert c["nearest_after"]["keyframe_uid"] == "CUSTOM:V1:F20"

    # BTC space closest to 20000ms is 15000ms (-5000ms) or 25000ms (+5000ms)
    # Tie-break prefers earlier (15000ms)
    b = res["btc"]
    assert b["nearest_before"]["keyframe_uid"] == "BTC:V1:KF2"
    assert b["nearest_before"]["delta_ms"] == -5000
    assert b["nearest_after"]["keyframe_uid"] == "BTC:V1:KF3"
    assert b["nearest_after"]["delta_ms"] == 5000
    assert b["nearest_absolute"]["keyframe_uid"] == "BTC:V1:KF2"


def test_nearest_keyframe_boundaries(tmp_rowmaps):
    custom_path, btc_path = tmp_rowmaps
    resolver = NearestKeyframeResolver(custom_path, btc_path)

    # Target before first keyframe (2s = 2000ms)
    res_before = resolver.resolve_space("CUSTOM", "V1", 2000)
    assert res_before["nearest_before"] is None
    assert res_before["nearest_after"]["keyframe_uid"] == "CUSTOM:V1:F10"
    assert res_before["nearest_absolute"]["keyframe_uid"] == "CUSTOM:V1:F10"

    # Target after last keyframe (40s = 40000ms)
    res_after = resolver.resolve_space("CUSTOM", "V1", 40000)
    assert res_after["nearest_before"]["keyframe_uid"] == "CUSTOM:V1:F30"
    assert res_after["nearest_after"] is None
    assert res_after["nearest_absolute"]["keyframe_uid"] == "CUSTOM:V1:F30"


def test_unknown_video(tmp_rowmaps):
    custom_path, btc_path = tmp_rowmaps
    resolver = NearestKeyframeResolver(custom_path, btc_path)

    res = resolver.resolve_all_spaces("UNKNOWN_V99", 10000)
    assert res["custom"]["nearest_absolute"] is None
    assert res["btc"]["nearest_absolute"] is None
