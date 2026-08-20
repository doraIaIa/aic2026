"""AIC 2026 – Media Frame Cache.

Thread-safe on-demand sparse JPEG cache for physical exact-frame extraction.
Keyed by video_id, resolved_frame_idx, and extraction_version.
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_EXTRACTION_VERSION = "v1"
DEFAULT_MAX_CACHE_ITEMS = 500
DEFAULT_MAX_CACHE_BYTES = 100 * 1024 * 1024  # 100 MB


class MediaFrameCache:
    """Bounded, thread-safe LRU cache for extracted JPEG frame bytes."""

    def __init__(
        self,
        max_items: int = DEFAULT_MAX_CACHE_ITEMS,
        max_bytes: int = DEFAULT_MAX_CACHE_BYTES,
        extraction_version: str = DEFAULT_EXTRACTION_VERSION,
    ) -> None:
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.extraction_version = extraction_version
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._current_bytes = 0
        self._lock = threading.Lock()

        # Metrics
        self.hits = 0
        self.misses = 0
        self.errors = 0

    def _make_key(self, video_id: str, frame_idx: int) -> str:
        return f"{video_id}:{frame_idx}:{self.extraction_version}"

    def get(self, video_id: str, frame_idx: int) -> Optional[bytes]:
        key = self._make_key(video_id, frame_idx)
        with self._lock:
            if key in self._cache:
                self.hits += 1
                self._cache.move_to_end(key)
                return self._cache[key]
            self.misses += 1
            return None

    def put(self, video_id: str, frame_idx: int, jpeg_bytes: bytes) -> None:
        if not jpeg_bytes:
            return
        key = self._make_key(video_id, frame_idx)
        byte_len = len(jpeg_bytes)

        with self._lock:
            if key in self._cache:
                old_bytes = self._cache.pop(key)
                self._current_bytes -= len(old_bytes)

            self._cache[key] = jpeg_bytes
            self._current_bytes += byte_len
            self._cache.move_to_end(key)

            # Evict oldest items if limits exceeded
            while len(self._cache) > self.max_items or self._current_bytes > self.max_bytes:
                if not self._cache:
                    break
                k, evicted_bytes = self._cache.popitem(last=False)
                self._current_bytes -= len(evicted_bytes)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "items": len(self._cache),
                "current_bytes": self._current_bytes,
                "max_items": self.max_items,
                "max_bytes": self.max_bytes,
                "hits": self.hits,
                "misses": self.misses,
                "errors": self.errors,
                "extraction_version": self.extraction_version,
            }

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0


# Global singleton instance for the process
_GLOBAL_FRAME_CACHE = MediaFrameCache()


def get_global_frame_cache() -> MediaFrameCache:
    return _GLOBAL_FRAME_CACHE
