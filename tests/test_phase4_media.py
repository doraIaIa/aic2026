"""Backend tests for Phase 4 – Media resolver, API handler, and TRAKE scorer.

These tests use synthetic/fixture data and do NOT require the 100GB corpus.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aic2026.media.resolver import (
    DecodeError,
    FrameOutOfRangeError,
    InvalidRequestError,
    MediaResolver,
    MediaUnavailableError,
    VideoMeta,
    VideoNotFoundError,
)
from aic2026.media.api_handler import handle_media_get


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolver(tmp_path: Path, with_manifest: bool = True) -> tuple[MediaResolver, Path]:
    """Create a MediaResolver backed by a temp directory with a stub video."""
    video_dir = tmp_path / "data_extracted" / "video"
    video_dir.mkdir(parents=True)
    # Use a minimal 1-frame dummy stub (not a real video; we'll mock ffprobe)
    stub = video_dir / "L01_V001.mp4"
    stub.write_bytes(b"STUB_VIDEO_BYTES")

    manifest_path: Path | None = None
    if with_manifest:
        manifest_path = tmp_path / "videos.jsonl"
        manifest_path.write_text(
            json.dumps({
                "video_id": "L01_V001",
                "relative_path": "data_extracted/video/L01_V001.mp4",
            }) + "\n",
            encoding="utf-8",
        )

    resolver = MediaResolver(tmp_path, manifest_path=manifest_path)
    return resolver, stub


_MOCK_META = VideoMeta(
    video_id="L01_V001",
    duration_sec=10.0,
    fps=25.0,
    frame_count=250,
    width=1920,
    height=1080,
    media_available=True,
)


# ---------------------------------------------------------------------------
# Media resolver – security tests
# ---------------------------------------------------------------------------

class TestVideoIdValidation:
    def test_valid_ids_accepted(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        # Should not raise during validation (path may not exist for other reasons)
        for vid in ("L01_V001", "L21_V100", "abc123", "A-B.C"):
            # Just test validation, not full resolve
            resolver._validate_video_id(vid)

    def test_path_traversal_rejected(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        for bad in ("../etc/passwd", "..\\windows\\system32", "%2e%2e/secret"):
            with pytest.raises(InvalidRequestError):
                resolver._validate_video_id(bad)

    def test_absolute_path_rejected(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        for bad in ("/etc/passwd", "C:\\Windows", "\\\\server\\share"):
            with pytest.raises(InvalidRequestError):
                resolver._validate_video_id(bad)

    def test_empty_id_rejected(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with pytest.raises(InvalidRequestError):
            resolver._validate_video_id("")

    def test_unknown_video_raises_not_found(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with pytest.raises(VideoNotFoundError):
            resolver._resolve_path("L99_V999")

    def test_media_unavailable_when_root_missing(self, tmp_path):
        resolver = MediaResolver(tmp_path / "nonexistent_root")
        with pytest.raises(MediaUnavailableError):
            resolver._resolve_path("L01_V001")


# ---------------------------------------------------------------------------
# Video info – no absolute path in response
# ---------------------------------------------------------------------------

class TestVideoInfo:
    def test_info_no_absolute_path(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch.object(resolver, "_ffprobe_video_meta_impl", return_value=_MOCK_META, create=True):
            # Monkey-patch _ffprobe_video_meta via resolver module
            with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
                meta = resolver.video_info("L01_V001")
        d = meta.to_dict()
        for v in d.values():
            assert not (isinstance(v, str) and (v.startswith("F:\\") or v.startswith("G:\\") or v.startswith("/"))), (
                f"Absolute path leaked in response: {v}"
            )

    def test_info_has_required_fields(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            meta = resolver.video_info("L01_V001")
        d = meta.to_dict()
        for key in ("video_id", "duration_sec", "fps", "frame_count", "width", "height", "media_available"):
            assert key in d, f"Missing field: {key}"
        assert d["video_id"] == "L01_V001"
        assert d["duration_sec"] > 0
        assert d["media_available"] is True


# ---------------------------------------------------------------------------
# Exact frame tests
# ---------------------------------------------------------------------------

class TestExactFrame:
    def test_frame_0_valid(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            path, pts = resolver.frame_path("L01_V001", 0)
        assert pts == 0.0

    def test_frame_middle_valid(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            path, pts = resolver.frame_path("L01_V001", 125)
        assert abs(pts - 5.0) < 0.1  # 125 / 25fps = 5.0

    def test_frame_last_valid(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            path, pts = resolver.frame_path("L01_V001", 249)
        assert pts > 0

    def test_frame_negative_raises(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            with pytest.raises(InvalidRequestError):
                resolver.frame_path("L01_V001", -1)

    def test_frame_out_of_range_raises(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            with pytest.raises(FrameOutOfRangeError):
                resolver.frame_path("L01_V001", 250)

    def test_adjacent_frames_have_different_pts(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            _, pts_n = resolver.frame_path("L01_V001", 10)
            _, pts_n1 = resolver.frame_path("L01_V001", 11)
        assert pts_n1 > pts_n, "frame N+1 must have later PTS than frame N"

    def test_same_frame_request_is_deterministic(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            _, pts1 = resolver.frame_path("L01_V001", 50)
            _, pts2 = resolver.frame_path("L01_V001", 50)
        assert pts1 == pts2


# ---------------------------------------------------------------------------
# Time-to-frame resolve tests
# ---------------------------------------------------------------------------

class TestResolveFrame:
    def test_time_0_returns_frame_0(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        _mock_result = MagicMock()
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            with patch("aic2026.media.resolver._resolve_frame_at_time") as mock_resolve:
                from aic2026.media.resolver import FrameResolveResult
                mock_resolve.return_value = FrameResolveResult(
                    video_id="L01_V001", requested_time_sec=0.0, decoded_frame_ordinal=0, decoded_pts_sec=0.0, competition_frame_id=0, mapping_method="deterministic_int_truncation"
                )
                result = resolver.resolve_frame_from_time("L01_V001", 0.0)
        assert result.decoded_frame_ordinal == 0
        assert result.competition_frame_id == 0

    def test_negative_time_rejected(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with pytest.raises(InvalidRequestError):
            resolver.resolve_frame_from_time("L01_V001", -1.0)

    def test_time_beyond_duration_rejected(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            with pytest.raises(FrameOutOfRangeError):
                resolver.resolve_frame_from_time("L01_V001", 9999.0)


# ---------------------------------------------------------------------------
# API handler – path matching & error codes
# ---------------------------------------------------------------------------

class TestApiHandler:
    def test_info_unknown_video(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        with patch("aic2026.media.resolver._ffprobe_video_meta", return_value=_MOCK_META):
            result = handle_media_get("/api/v1/media/L99_UNKNOWN/info", "", None, resolver)
        assert result is not None
        status, body, _ = result
        assert status == HTTPStatus.NOT_FOUND
        payload = json.loads(body)
        assert payload["status"] == "ERROR"

    def test_info_path_traversal(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        result = handle_media_get("/api/v1/media/../etc/passwd/info", "", None, resolver)
        # Either not matched or bad request
        if result is not None:
            status, body, _ = result
            assert status in (HTTPStatus.NOT_FOUND, HTTPStatus.BAD_REQUEST)

    def test_unmatched_path_returns_none(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        result = handle_media_get("/api/v1/unknown/path", "", None, resolver)
        assert result is None

    def test_resolve_missing_time_sec(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        result = handle_media_get("/api/v1/media/L01_V001/resolve-frame", "", None, resolver)
        assert result is not None
        status, body, _ = result
        assert status == HTTPStatus.BAD_REQUEST

    def test_resolve_invalid_time_sec(self, tmp_path):
        resolver, _ = _make_resolver(tmp_path)
        result = handle_media_get("/api/v1/media/L01_V001/resolve-frame", "time_sec=abc", None, resolver)
        assert result is not None
        status, _, _ = result
        assert status == HTTPStatus.BAD_REQUEST

    def test_no_resolver_returns_none(self):
        result = handle_media_get("/api/v1/media/L01_V001/info", "", None, None)
        assert result is None


# ---------------------------------------------------------------------------
# TRAKE scorer tests (Phase 4C)
# ---------------------------------------------------------------------------

from aic2026.evaluation.scoring import score_trake, CUTOFFS, BLOCKED_BY_SCORING_CONTRACT
from aic2026.evaluation.scoring import score_query


def _trake_query(**overrides):
    query = {
        "query_id": "tq1",
        "query_type": "TRAKE",
        "trap_category": "temporal",
        "split": "dev",
        "label_status": "labeled",
        "gt_video_id": "V1",
        "gt_events": [
            {"start_frame": 10, "end_frame": 20},
            {"start_frame": 50, "end_frame": 60},
            {"start_frame": 100, "end_frame": 110},
        ],
    }
    query.update(overrides)
    return query
