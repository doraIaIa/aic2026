"""Unit tests for media Range streaming and HTTP API handler."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
import pytest

from aic2026.media.api_handler import handle_media_get, _stream_response
from aic2026.media.resolver import MediaResolver


@pytest.fixture
def dummy_video(tmp_path: Path):
    video_file = tmp_path / "L21_V001.mp4"
    # Write 1000 dummy bytes
    data = bytes([i % 256 for i in range(1000)])
    video_file.write_bytes(data)
    return tmp_path, video_file, data


def test_range_stream_full(dummy_video):
    tmp_path, video_file, data = dummy_video
    status, body, content_type = _stream_response(video_file, None)
    assert status == HTTPStatus.OK
    assert content_type == "video/mp4"
    assert len(body) == 1000
    assert body == data


def test_range_stream_partial(dummy_video):
    tmp_path, video_file, data = dummy_video

    # Request bytes 100-199 (100 bytes)
    status, body, content_type = _stream_response(video_file, "bytes=100-199")
    assert status == HTTPStatus.PARTIAL_CONTENT
    assert len(body) == 100
    assert body == data[100:200]


def test_range_stream_unsatisfiable(dummy_video):
    tmp_path, video_file, data = dummy_video

    # Request range past end of file (bytes=1500-2000)
    status, body, content_type = _stream_response(video_file, "bytes=1500-2000")
    assert status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE
