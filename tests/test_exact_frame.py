"""Unit tests for exact source-frame resolution and MediaFrameCache."""
from __future__ import annotations

import pytest
from aic2026.media.cache import MediaFrameCache
from aic2026.media.resolver import FrameResolveResult, VideoMeta


def test_media_frame_cache_lru_and_metrics():
    cache = MediaFrameCache(max_items=3, max_bytes=1000)

    # Initial get miss
    assert cache.get("V1", 10) is None
    assert cache.misses == 1

    # Put and hit
    data10 = b"jpeg_frame_10"
    cache.put("V1", 10, data10)
    assert cache.get("V1", 10) == data10
    assert cache.hits == 1

    # Eviction test (max_items = 3)
    cache.put("V1", 20, b"frame_20")
    cache.put("V1", 30, b"frame_30")
    cache.put("V1", 40, b"frame_40")  # Should evict V1:10 (least recently used)

    assert cache.get("V1", 10) is None  # evicted
    assert cache.get("V1", 20) == b"frame_20"


def test_frame_resolve_result_authority_and_delta():
    result = FrameResolveResult(
        video_id="L21_V001",
        requested_time_sec=17.2,
        requested_timestamp_ms=17200,
        decoded_frame_ordinal=430,
        decoded_pts_sec=17.198,
        competition_frame_id=516,
        mapping_method="PTS_AWARE",
        method="PTS_AWARE",
        authority="SOURCE_VIDEO",
    )

    d = result.to_dict()
    assert d["video_id"] == "L21_V001"
    assert d["requested_timestamp_ms"] == 17200
    assert d["resolved_frame_idx"] == 430
    assert d["resolved_pts_ms"] == 17198
    assert d["delta_ms"] == -2
    assert d["authority"] == "SOURCE_VIDEO"
    assert d["method"] == "PTS_AWARE"
    assert d["jpeg_url"] == "/api/v1/media/L21_V001/frames/430"
