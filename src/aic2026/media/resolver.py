"""AIC 2026 – Media resolver module.

Security contract:
- video_id is the only input accepted from untrusted callers.
- Absolute paths are NEVER returned to callers outside this module.
- Path traversal via video_id is rejected by the canonical manifest check
  and by an explicit safelist pattern.
- The raw filesystem path is internal-only; callers get VideoMeta.
"""
from __future__ import annotations

import re
import subprocess
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_FFPROBE_TIMEOUT = 10  # seconds


class MediaError(Exception):
    """Base for media-layer errors."""


class MediaUnavailableError(MediaError):
    """Media root is not configured or not accessible."""


class VideoNotFoundError(MediaError):
    """Requested video_id not found in the canonical manifest."""


class FrameOutOfRangeError(MediaError):
    """Requested frame_id is outside the video frame count."""


class DecodeError(MediaError):
    """ffprobe/ffmpeg returned an error or unexpected output."""


class InvalidRequestError(MediaError):
    """Caller supplied invalid or potentially malicious input."""


# ---------------------------------------------------------------------------
# Video metadata dataclass (no raw path exposed)
# ---------------------------------------------------------------------------

class VideoMeta:
    """Immutable container for video metadata. No raw path exposed."""

    __slots__ = (
        "video_id",
        "duration_sec",
        "fps",
        "frame_count",
        "width",
        "height",
        "media_available",
        "exact_frame_supported",
        "range_stream_supported",
        "frame_count_reliable",
        "fps_num",
        "fps_den",
        "time_base",
        "codec",
    )

    def __init__(
        self,
        *,
        video_id: str,
        duration_sec: float,
        fps: float,
        frame_count: int,
        width: int,
        height: int,
        media_available: bool,
        exact_frame_supported: bool = True,
        range_stream_supported: bool = True,
        frame_count_reliable: bool = True,
        fps_num: int = 25,
        fps_den: int = 1,
        time_base: str = "1/1000",
        codec: str = "h264",
    ) -> None:
        self.video_id = video_id
        self.duration_sec = duration_sec
        self.fps = fps
        self.frame_count = frame_count
        self.width = width
        self.height = height
        self.media_available = media_available
        self.exact_frame_supported = exact_frame_supported
        self.range_stream_supported = range_stream_supported
        self.frame_count_reliable = frame_count_reliable
        self.fps_num = fps_num
        self.fps_den = fps_den
        self.time_base = time_base
        self.codec = codec

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "duration_sec": self.duration_sec,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "media_available": self.media_available,
            "exact_frame_supported": self.exact_frame_supported,
            "range_stream_supported": self.range_stream_supported,
            "frame_count_reliable": self.frame_count_reliable,
            "fps_num": self.fps_num,
            "fps_den": self.fps_den,
            "time_base": self.time_base,
            "codec": self.codec,
        }


# ---------------------------------------------------------------------------
# Frame resolve result
# ---------------------------------------------------------------------------

class FrameResolveResult:
    __slots__ = (
        "video_id",
        "requested_time_sec",
        "requested_timestamp_ms",
        "requested_frame_idx",
        "decoded_frame_ordinal",
        "resolved_frame_idx",
        "decoded_pts_sec",
        "resolved_pts_ms",
        "delta_ms",
        "authority",
        "mapping_method",
        "method",
        "competition_frame_id",
        "jpeg_url",
    )

    def __init__(
        self,
        *,
        video_id: str,
        requested_time_sec: float,
        requested_timestamp_ms: Optional[int] = None,
        requested_frame_idx: Optional[int] = None,
        decoded_frame_ordinal: int,
        decoded_pts_sec: float,
        competition_frame_id: int,
        mapping_method: str = "PTS_AWARE",
        method: str = "PTS_AWARE",
        authority: str = "SOURCE_VIDEO",
    ) -> None:
        self.video_id = video_id
        self.requested_time_sec = requested_time_sec
        self.requested_timestamp_ms = (
            requested_timestamp_ms
            if requested_timestamp_ms is not None
            else int(round(requested_time_sec * 1000))
        )
        self.requested_frame_idx = requested_frame_idx
        self.decoded_frame_ordinal = decoded_frame_ordinal
        self.resolved_frame_idx = decoded_frame_ordinal
        self.decoded_pts_sec = decoded_pts_sec
        self.resolved_pts_ms = int(round(decoded_pts_sec * 1000))
        self.delta_ms = self.resolved_pts_ms - self.requested_timestamp_ms
        self.competition_frame_id = competition_frame_id
        self.mapping_method = mapping_method
        self.method = method
        self.authority = authority
        self.jpeg_url = f"/api/v1/media/{video_id}/frames/{decoded_frame_ordinal}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "requested_time_sec": self.requested_time_sec,
            "requested_timestamp_ms": self.requested_timestamp_ms,
            "requested_frame_idx": self.requested_frame_idx,
            "decoded_frame_ordinal": self.decoded_frame_ordinal,
            "resolved_frame_idx": self.resolved_frame_idx,
            "decoded_pts_sec": self.decoded_pts_sec,
            "resolved_pts_ms": self.resolved_pts_ms,
            "delta_ms": self.delta_ms,
            "authority": self.authority,
            "mapping_method": self.mapping_method,
            "method": self.method,
            "competition_frame_id": self.competition_frame_id,
            "jpeg_url": self.jpeg_url,
        }


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class MediaResolver:
    """Resolves video_id -> canonical path, enforces security, caches metadata."""

    def __init__(
        self,
        media_root: str | Path,
        *,
        manifest_path: str | Path | None = None,
        video_subdir: str = "data_extracted/video",
    ) -> None:
        self._media_root = Path(media_root)
        self._video_subdir = video_subdir
        self._manifest_path = Path(manifest_path) if manifest_path else None
        self._manifest_lock = threading.Lock()
        self._manifest: dict[str, str] | None = None  # video_id -> relative_path
        self._meta_cache: dict[str, VideoMeta] = {}
        self._cache_lock = threading.Lock()

    def is_available(self) -> bool:
        try:
            return self._media_root.is_dir()
        except OSError:
            return False

    def _load_manifest(self) -> dict[str, str]:
        with self._manifest_lock:
            if self._manifest is not None:
                return self._manifest
            result: dict[str, str] = {}
            if self._manifest_path and self._manifest_path.is_file():
                import json
                with self._manifest_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            vid = obj.get("video_id")
                            rel = obj.get("relative_path")
                            if vid and rel:
                                result[vid] = rel
                        except Exception:
                            pass
            self._manifest = result
            return result

    def _validate_video_id(self, video_id: str) -> None:
        if not isinstance(video_id, str) or not _VIDEO_ID_RE.fullmatch(video_id):
            raise InvalidRequestError(f"Invalid video_id format: {video_id!r}")

    def _resolve_path(self, video_id: str) -> Path:
        """Internal only – returns absolute path, never returned to callers."""
        if not self.is_available():
            raise MediaUnavailableError("Media root not available")
        self._validate_video_id(video_id)
        manifest = self._load_manifest()
        if manifest:
            rel = manifest.get(video_id)
            if rel is None:
                raise VideoNotFoundError(f"video_id not in manifest: {video_id}")
            candidate = self._media_root / rel
        else:
            # Fallback to subdir convention: data_extracted/video/<video_id>.mp4
            candidate = self._media_root / self._video_subdir / f"{video_id}.mp4"
        # Safety: ensure resolved path stays inside media_root
        try:
            candidate.resolve().relative_to(self._media_root.resolve())
        except ValueError:
            raise InvalidRequestError("Resolved path escapes media_root (path traversal)")
        if not candidate.exists():
            raise VideoNotFoundError(f"Video file not found for video_id={video_id}")
        return candidate

    # ------------------------------------------------------------------
    # Public API – returns only safe data, never raw paths
    # ------------------------------------------------------------------

    def video_info(self, video_id: str) -> VideoMeta:
        with self._cache_lock:
            if video_id in self._meta_cache:
                return self._meta_cache[video_id]
        path = self._resolve_path(video_id)  # raises on error
        meta = _ffprobe_video_meta(video_id, path)
        with self._cache_lock:
            self._meta_cache[video_id] = meta
        return meta

    def resolve_frame_from_time(self, video_id: str, time_sec: float) -> FrameResolveResult:
        if not isinstance(time_sec, (int, float)) or time_sec < 0:
            raise InvalidRequestError("time_sec must be a non-negative number")
        path = self._resolve_path(video_id)
        meta = self.video_info(video_id)
        if time_sec > meta.duration_sec + 0.5:
            raise FrameOutOfRangeError(
                f"time_sec={time_sec:.3f} exceeds video duration {meta.duration_sec:.3f}"
            )
        return _resolve_frame_at_time(video_id, path, time_sec, meta)

    def frame_path(self, video_id: str, frame_id: int) -> tuple[Path, float]:
        """Returns (internal path, pts_sec) for frame_id; path must not be sent outside."""
        if not isinstance(frame_id, int) or frame_id < 0:
            raise InvalidRequestError("frame_id must be a non-negative integer")
        path = self._resolve_path(video_id)
        meta = self.video_info(video_id)
        if frame_id >= meta.frame_count:
            raise FrameOutOfRangeError(
                f"frame_id={frame_id} >= frame_count={meta.frame_count}"
            )
        pts_sec = _frame_id_to_pts(path, frame_id, meta)
        return path, pts_sec

    def keyframe_path(self, video_id: str, csv_n: int) -> Path:
        """Resolve a canonical extracted keyframe by its 1-based CSV ordinal.

        This endpoint is for retrieval thumbnails only.  `csv_n` is never a
        video frame index and is deliberately kept separate from the physical
        decoded frame workflow used for candidate selection.
        """
        if not isinstance(csv_n, int) or csv_n < 1:
            raise InvalidRequestError("csv_n must be a positive 1-based ordinal")
        self._resolve_path(video_id)  # validates availability, manifest, and video id
        candidate = self._media_root / "data_extracted" / "keyframes" / video_id / f"{csv_n:03d}.jpg"
        try:
            candidate.resolve().relative_to(self._media_root.resolve())
        except ValueError as exc:
            raise InvalidRequestError("Resolved keyframe path escapes media_root") from exc
        if not candidate.is_file():
            raise VideoNotFoundError(f"Keyframe ordinal not found for video_id={video_id}: {csv_n}")
        return candidate

    def video_path_for_streaming(self, video_id: str) -> Path:
        """Internal only – returns path for streaming; caller must not expose this."""
        return self._resolve_path(video_id)


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def _run_ffprobe(args: list[str]) -> str:
    """Run ffprobe with subprocess list args (no shell=True). Returns stdout."""
    cmd = ["ffprobe"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_FFPROBE_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        raise DecodeError("ffprobe not found; install ffmpeg package")
    except subprocess.TimeoutExpired:
        raise DecodeError(f"ffprobe timed out after {_FFPROBE_TIMEOUT}s")
    if result.returncode != 0:
        raise DecodeError(f"ffprobe error (rc={result.returncode}): {result.stderr[:400]}")
    return result.stdout


def _ffprobe_video_meta(video_id: str, path: Path) -> VideoMeta:
    import json as _json
    stdout = _run_ffprobe([
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,codec_name,time_base,nb_frames:format=duration",
        "-of", "json",
        str(path),
    ])
    try:
        data = _json.loads(stdout)
    except Exception:
        raise DecodeError(f"ffprobe returned non-JSON for {video_id}")

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    if not streams:
        raise DecodeError(f"No video stream found for {video_id}")

    stream = streams[0]
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    codec = str(stream.get("codec_name", "h264"))
    time_base = str(stream.get("time_base", "1/1000"))

    # Parse rational FPS e.g. "25/1" or "30000/1001"
    rfr = stream.get("r_frame_rate", "25/1")
    try:
        num, den = map(int, rfr.split("/"))
        fps = num / den if den else 25.0
    except Exception:
        num, den = 25, 1
        fps = 25.0

    duration_sec = float(fmt.get("duration") or stream.get("duration", 0))
    # nb_frames may be absent in some formats
    nb_frames_raw = stream.get("nb_frames")
    frame_count_reliable = True
    if nb_frames_raw is not None and str(nb_frames_raw).isdigit():
        frame_count = int(nb_frames_raw)
    else:
        frame_count = max(1, round(duration_sec * fps))
        frame_count_reliable = False

    return VideoMeta(
        video_id=video_id,
        duration_sec=duration_sec,
        fps=fps,
        frame_count=frame_count,
        width=width,
        height=height,
        media_available=True,
        exact_frame_supported=True,
        range_stream_supported=True,
        frame_count_reliable=frame_count_reliable,
        fps_num=num,
        fps_den=den,
        time_base=time_base,
        codec=codec,
    )


def _resolve_frame_at_time(
    video_id: str, path: Path, time_sec: float, meta: VideoMeta
) -> FrameResolveResult:
    """Convert time_sec to a resolved dual-identity frame."""
    from aic2026.media.mapper import FrameIdentityMapper
    
    fps = meta.fps if meta.fps > 0 else 25.0
    
    identity = FrameIdentityMapper.resolve_and_map(video_id, time_sec, fps)
    
    # Clamp bounds for physical ordinal
    clamped_ordinal = max(0, min(meta.frame_count - 1, identity.decoded_frame_ordinal))
    if clamped_ordinal != identity.decoded_frame_ordinal:
        # Re-map if it was clamped
        time_clamped = clamped_ordinal / fps
        identity = FrameIdentityMapper.resolve_and_map(video_id, time_clamped, fps)
        
    return FrameResolveResult(
        video_id=video_id,
        requested_time_sec=time_sec,
        requested_timestamp_ms=int(round(time_sec * 1000)),
        decoded_frame_ordinal=identity.decoded_frame_ordinal,
        decoded_pts_sec=identity.decoded_pts_sec,
        competition_frame_id=identity.competition_frame_id,
        mapping_method=identity.mapping_method,
        method="PTS_AWARE",
        authority="SOURCE_VIDEO",
    )


def _frame_id_to_pts(path: Path, frame_id: int, meta: VideoMeta) -> float:
    """Convert frame_id to estimated PTS. Uses fps since PTS enumeration is expensive."""
    # For CFR video, frame PTS = frame_id / fps
    # For VFR, this is an approximation. We expose this limitation clearly.
    return round(frame_id / meta.fps, 6) if meta.fps > 0 else 0.0


def decode_frame_jpeg(path: Path, frame_id: int, meta: VideoMeta) -> bytes:
    """Decode frame_id to JPEG bytes using exact timeline decoding and LRU cache.
    
    Instead of using `-ss {pts}` which is approximate due to keyframe snapping,
    this uses a hybrid approach:
    1. Fast coarse seek to `pts - 5` seconds using `-ss` before `-i`.
    2. `-copyts` to preserve absolute timestamps.
    3. `select='gte(t,{pts - 0.001})'` to decode exactly the requested frame.
    """
    from aic2026.media.cache import get_global_frame_cache
    cache = get_global_frame_cache()
    cached = cache.get(meta.video_id, frame_id)
    if cached:
        return cached

    target_pts = _frame_id_to_pts(path, frame_id, meta)
    seek_pts = max(0.0, target_pts - 5.0)
    
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-ss", f"{seek_pts:.6f}",
        "-i", str(path),
        "-copyts",
        "-vf", f"select='gte(t,{target_pts - 0.001})'",
        "-vsync", "vfr",
        "-vframes", "1",
        "-f", "image2",
        "-vcodec", "mjpeg",
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        cache.errors += 1
        raise DecodeError("ffmpeg not found; install ffmpeg package")
    except subprocess.TimeoutExpired:
        cache.errors += 1
        raise DecodeError("ffmpeg timed out decoding frame")
    if result.returncode != 0 or not result.stdout:
        cache.errors += 1
        raise DecodeError(f"ffmpeg decode error (rc={result.returncode}): {result.stderr[:300]}")
    
    jpeg_bytes = result.stdout
    cache.put(meta.video_id, frame_id, jpeg_bytes)
    return jpeg_bytes
