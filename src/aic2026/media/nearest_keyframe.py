"""AIC 2026 – Nearest Keyframe Resolver.

Provides deterministic nearest sampled keyframe lookup in CUSTOM and BTC frame spaces.
Uses sorted canonical keyframe timestamps with binary search.
Does NOT perform cross-space ordinal mapping.
"""
from __future__ import annotations

import bisect
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default locations for keyframe rowmaps in AIC_WORK
CUSTOM_ROWMAP_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\siglip_custom_v1\siglip_custom_rowmap.jsonl")
BTC_ROWMAP_PATH = Path(r"F:\AIC_WORK\artifacts\canonical_btc_v1\btc_clip_raw_rowmap.jsonl")


class KeyframeNode:
    """Compact container for a sampled retrieval keyframe."""
    __slots__ = ("space", "video_id", "timestamp_ms", "frame_idx", "keyframe_uid", "keyframe_no")

    def __init__(
        self,
        *,
        space: str,
        video_id: str,
        timestamp_ms: int,
        frame_idx: int,
        keyframe_uid: str,
        keyframe_no: Optional[int] = None,
    ) -> None:
        self.space = space
        self.video_id = video_id
        self.timestamp_ms = timestamp_ms
        self.frame_idx = frame_idx
        self.keyframe_uid = keyframe_uid
        self.keyframe_no = keyframe_no

    def to_dict(self, target_ms: int, relation: str) -> dict[str, Any]:
        return {
            "space": self.space,
            "target_ms": target_ms,
            "keyframe_uid": self.keyframe_uid,
            "timestamp_ms": self.timestamp_ms,
            "delta_ms": self.timestamp_ms - target_ms,
            "relation": relation,
            "frame_idx": self.frame_idx,
            "keyframe_no": self.keyframe_no,
        }


class NearestKeyframeResolver:
    """Thread-safe, lazy-loaded keyframe neighborhood resolver."""

    def __init__(
        self,
        custom_rowmap_path: Path | str = CUSTOM_ROWMAP_PATH,
        btc_rowmap_path: Path | str = BTC_ROWMAP_PATH,
    ) -> None:
        self._custom_path = Path(custom_rowmap_path)
        self._btc_path = Path(btc_rowmap_path)
        self._lock = threading.Lock()
        self._loaded = False
        # video_id -> list of KeyframeNode sorted by timestamp_ms
        self._custom_nodes: dict[str, list[KeyframeNode]] = {}
        self._btc_nodes: dict[str, list[KeyframeNode]] = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_space("CUSTOM", self._custom_path, self._custom_nodes)
            self._load_space("BTC", self._btc_path, self._btc_nodes)
            self._loaded = True

    def _load_space(self, space: str, path: Path, out_dict: dict[str, list[KeyframeNode]]) -> None:
        if not path.is_file():
            logger.warning("Keyframe rowmap for space %s not found at %s", space, path)
            return

        nodes_by_video: dict[str, list[KeyframeNode]] = {}
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    video_id = obj.get("video_id")
                    if not video_id:
                        continue
                    ts_ms = obj.get("timestamp_ms")
                    if ts_ms is None and "raw_pts_time" in obj:
                        ts_ms = int(round(float(obj["raw_pts_time"]) * 1000))
                    if ts_ms is None:
                        ts_ms = 0

                    frame_idx = int(obj.get("frame_idx", 0))
                    uid = str(obj.get("keyframe_uid") or f"{space}:{video_id}:{ts_ms}")
                    kf_no = obj.get("local_keyframe_no")
                    if kf_no is None:
                        kf_no = obj.get("csv_n") or obj.get("keyframe_no") or obj.get("keyframe_id")
                    if kf_no is None and obj.get("image_relpath"):
                        match = re.search(r"(\d+)\.jpe?g$", str(obj["image_relpath"]), re.IGNORECASE)
                        if match:
                            kf_no = int(match.group(1))

                    node = KeyframeNode(
                        space=space,
                        video_id=video_id,
                        timestamp_ms=ts_ms,
                        frame_idx=frame_idx,
                        keyframe_uid=uid,
                        keyframe_no=int(kf_no) if kf_no is not None else None,
                    )
                    nodes_by_video.setdefault(video_id, []).append(node)

            # Sort nodes by timestamp_ms for binary search
            for vid, nodes in nodes_by_video.items():
                out_dict[vid] = sorted(nodes, key=lambda n: n.timestamp_ms)
        except Exception as e:
            logger.exception("Failed loading keyframe rowmap %s: %s", path, e)

    def resolve_space(
        self, space: str, video_id: str, target_ms: int
    ) -> dict[str, Optional[dict[str, Any]]]:
        self._ensure_loaded()
        space_dict = self._custom_nodes if space.upper() == "CUSTOM" else self._btc_nodes
        nodes = space_dict.get(video_id) or []

        if not nodes:
            return {"nearest_absolute": None, "nearest_before": None, "nearest_after": None}

        timestamps = [n.timestamp_ms for n in nodes]
        idx = bisect.bisect_left(timestamps, target_ms)

        # 1. Nearest Before (<= target_ms)
        nearest_before_node: Optional[KeyframeNode] = None
        if idx < len(nodes) and nodes[idx].timestamp_ms == target_ms:
            nearest_before_node = nodes[idx]
        elif idx > 0:
            nearest_before_node = nodes[idx - 1]

        # 2. Nearest After (>= target_ms)
        nearest_after_node: Optional[KeyframeNode] = None
        if idx < len(nodes):
            nearest_after_node = nodes[idx]

        # 3. Nearest Absolute (closest delta)
        nearest_abs_node: Optional[KeyframeNode] = None
        if nearest_before_node and nearest_after_node:
            d_before = abs(nearest_before_node.timestamp_ms - target_ms)
            d_after = abs(nearest_after_node.timestamp_ms - target_ms)
            # Deterministic tie break: if equal delta, pick earlier (before)
            if d_before <= d_after:
                nearest_abs_node = nearest_before_node
            else:
                nearest_abs_node = nearest_after_node
        elif nearest_before_node:
            nearest_abs_node = nearest_before_node
        elif nearest_after_node:
            nearest_abs_node = nearest_after_node

        return {
            "nearest_absolute": nearest_abs_node.to_dict(target_ms, "NEAREST") if nearest_abs_node else None,
            "nearest_before": nearest_before_node.to_dict(target_ms, "BEFORE") if nearest_before_node else None,
            "nearest_after": nearest_after_node.to_dict(target_ms, "AFTER") if nearest_after_node else None,
        }

    def resolve_all_spaces(
        self, video_id: str, target_ms: int
    ) -> dict[str, Any]:
        return {
            "video_id": video_id,
            "target_ms": target_ms,
            "custom": self.resolve_space("CUSTOM", video_id, target_ms),
            "btc": self.resolve_space("BTC", video_id, target_ms),
        }


# Global singleton instance
_GLOBAL_KEYFRAME_RESOLVER = NearestKeyframeResolver()


def get_global_keyframe_resolver() -> NearestKeyframeResolver:
    return _GLOBAL_KEYFRAME_RESOLVER
