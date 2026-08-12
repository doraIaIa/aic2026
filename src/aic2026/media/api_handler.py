"""AIC 2026 – Media HTTP handler.

Adds four endpoints to the existing BaseHTTPRequestHandler-based API:
  GET /api/v1/media/{video_id}/info
  GET /api/v1/media/{video_id}/stream
  GET /api/v1/media/{video_id}/frames/{frame_id}
  GET /api/v1/media/{video_id}/resolve-frame?time_sec=...

Security invariants:
- Absolute Windows paths are NEVER returned to callers.
- Path traversal via video_id is rejected.
- Raw video path stays internal.
"""
from __future__ import annotations

import json
import re
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from aic2026.media.resolver import (
    DecodeError,
    FrameOutOfRangeError,
    InvalidRequestError,
    MediaResolver,
    MediaUnavailableError,
    VideoNotFoundError,
    decode_frame_jpeg,
)

# Pattern: /api/v1/media/{video_id}/info|stream|resolve-frame
_INFO_RE = re.compile(r"^/api/v1/media/([^/]+)/info$")
_STREAM_RE = re.compile(r"^/api/v1/media/([^/]+)/stream$")
_FRAME_RE = re.compile(r"^/api/v1/media/([^/]+)/frames/(\d+)$")
_RESOLVE_RE = re.compile(r"^/api/v1/media/([^/]+)/resolve-frame$")


def _json_error(status: int, message: str) -> tuple[int, bytes, str]:
    body = json.dumps({"status": "ERROR", "error": message}, ensure_ascii=False).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def _json_ok(payload: dict[str, Any]) -> tuple[int, bytes, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return HTTPStatus.OK, body, "application/json; charset=utf-8"


def handle_media_get(
    path: str,
    query_string: str,
    range_header: str | None,
    resolver: MediaResolver | None,
) -> tuple[int, bytes, str] | None:
    """Try to handle a media API GET request.
    
    Returns (status, body_bytes, content_type) or None if no match.
    """
    if resolver is None:
        return None  # no media endpoint available

    parsed_path = urlparse(path).path

    # --- /info ---
    m = _INFO_RE.match(parsed_path)
    if m:
        video_id = m.group(1)
        try:
            meta = resolver.video_info(video_id)
            return _json_ok(meta.to_dict())
        except MediaUnavailableError as exc:
            return _json_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        except VideoNotFoundError as exc:
            return _json_error(HTTPStatus.NOT_FOUND, str(exc))
        except InvalidRequestError as exc:
            return _json_error(HTTPStatus.BAD_REQUEST, str(exc))
        except DecodeError as exc:
            return _json_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"DECODE_ERROR: {exc}")

    # --- /resolve-frame ---
    m = _RESOLVE_RE.match(parsed_path)
    if m:
        video_id = m.group(1)
        qs = parse_qs(query_string, keep_blank_values=True)
        time_raw = (qs.get("time_sec") or [""])[0].strip()
        if not time_raw:
            return _json_error(HTTPStatus.BAD_REQUEST, "time_sec query parameter is required")
        try:
            time_sec = float(time_raw)
        except ValueError:
            return _json_error(HTTPStatus.BAD_REQUEST, "time_sec must be a number")
        try:
            result = resolver.resolve_frame_from_time(video_id, time_sec)
            return _json_ok(result.to_dict())
        except MediaUnavailableError as exc:
            return _json_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        except VideoNotFoundError as exc:
            return _json_error(HTTPStatus.NOT_FOUND, str(exc))
        except FrameOutOfRangeError as exc:
            return _json_error(HTTPStatus.UNPROCESSABLE_ENTITY, f"FRAME_OUT_OF_RANGE: {exc}")
        except InvalidRequestError as exc:
            return _json_error(HTTPStatus.BAD_REQUEST, str(exc))
        except DecodeError as exc:
            return _json_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"DECODE_ERROR: {exc}")

    # --- /frames/{frame_id} ---
    m = _FRAME_RE.match(parsed_path)
    if m:
        video_id, frame_id_str = m.group(1), m.group(2)
        try:
            frame_id = int(frame_id_str)
            video_path, pts_sec = resolver.frame_path(video_id, frame_id)
            meta = resolver.video_info(video_id)
            jpeg_bytes = decode_frame_jpeg(video_path, frame_id, meta)
        except MediaUnavailableError as exc:
            return _json_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        except VideoNotFoundError as exc:
            return _json_error(HTTPStatus.NOT_FOUND, str(exc))
        except FrameOutOfRangeError as exc:
            return _json_error(HTTPStatus.UNPROCESSABLE_ENTITY, f"FRAME_OUT_OF_RANGE: {exc}")
        except InvalidRequestError as exc:
            return _json_error(HTTPStatus.BAD_REQUEST, str(exc))
        except DecodeError as exc:
            return _json_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"DECODE_ERROR: {exc}")
        return HTTPStatus.OK, jpeg_bytes, "image/jpeg"

    # --- /stream ---
    m = _STREAM_RE.match(parsed_path)
    if m:
        video_id = m.group(1)
        try:
            video_path = resolver.video_path_for_streaming(video_id)
        except MediaUnavailableError as exc:
            return _json_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        except VideoNotFoundError as exc:
            return _json_error(HTTPStatus.NOT_FOUND, str(exc))
        except InvalidRequestError as exc:
            return _json_error(HTTPStatus.BAD_REQUEST, str(exc))
        return _stream_response(video_path, range_header)

    return None  # path not matched


def _stream_response(
    video_path: Path,
    range_header: str | None,
) -> tuple[int, bytes, str]:
    """Read video bytes respecting Range header. Chunked via bytes read."""
    total_size = video_path.stat().st_size

    start = 0
    end = total_size - 1
    partial = False

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header.strip(), re.IGNORECASE)
        if m:
            start = int(m.group(1))
            end_str = m.group(2)
            end = int(end_str) if end_str else total_size - 1
            end = min(end, total_size - 1)
            if start > end or start >= total_size:
                return _json_error(
                    HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
                    f"Range {start}-{end} not satisfiable for size {total_size}",
                )
            partial = True

    chunk_size = end - start + 1
    try:
        with video_path.open("rb") as f:
            f.seek(start)
            data = f.read(chunk_size)
    except OSError as exc:
        return _json_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Read error: {exc}")

    status = HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK
    # Return raw bytes; caller writes Content-Range etc.
    return status, data, "video/mp4"


def write_stream_response(
    handler: Any,
    path: str,
    query_string: str,
    range_header: str | None,
    resolver: MediaResolver | None,
    allowed_origins: set[str],
) -> bool:
    """Write full HTTP response for media endpoints. Returns True if handled."""
    result = handle_media_get(path, query_string, range_header, resolver)
    if result is None:
        return False

    status, body, content_type = result
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    if content_type.startswith("video/") and range_header:
        # Content-Range was already validated; derive from body size
        handler.send_header("Accept-Ranges", "bytes")
        # Re-parse to compute range headers for response
        m = re.match(r"bytes=(\d+)-(\d*)", range_header.strip(), re.IGNORECASE)
        if m:
            total_size = len(body)  # actual bytes returned
            handler.send_header("Content-Range", f"bytes */{total_size}")

    if content_type.startswith("image/jpeg") or content_type.startswith("video/"):
        # Attach frame metadata headers if available
        pass  # metadata returned in JSON for /info, not inline

    origin = handler.headers.get("Origin", "")
    if origin in allowed_origins:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
    handler.end_headers()
    handler.wfile.write(body)
    return True
