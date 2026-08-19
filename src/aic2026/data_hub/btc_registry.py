from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from aic2026.data_hub.btc_models import (
    BtcClipRowRecord,
    BtcKeyframeRecord,
    BtcMediaInfoRecord,
    BtcObjectCoverageRecord,
    BtcObjectDetectionRecord,
    BtcSpace,
)


class BtcRegistry:
    """In-memory Data Hub registry for canonical BTC keyframe space, CLIP mappings, objects, and media info."""

    def __init__(
        self,
        keyframes: List[BtcKeyframeRecord],
        clip_rowmaps: Optional[List[BtcClipRowRecord]] = None,
        object_detections: Optional[List[BtcObjectDetectionRecord]] = None,
        object_coverage: Optional[List[BtcObjectCoverageRecord]] = None,
        media_info: Optional[List[BtcMediaInfoRecord]] = None,
        btc_space: Optional[BtcSpace] = None,
    ) -> None:
        self.btc_space = btc_space
        self._keyframes_by_uid: Dict[str, BtcKeyframeRecord] = {}
        self._keyframes_by_vid_n: Dict[Tuple[str, int], BtcKeyframeRecord] = {}
        self._keyframes_by_vid: Dict[str, List[BtcKeyframeRecord]] = {}

        for kf in keyframes:
            self._keyframes_by_uid[kf.keyframe_uid] = kf
            self._keyframes_by_vid_n[(kf.video_id, kf.local_keyframe_no)] = kf
            self._keyframes_by_vid.setdefault(kf.video_id, []).append(kf)

        # Sort per-video keyframes by timestamp_ms
        for vid in self._keyframes_by_vid:
            self._keyframes_by_vid[vid].sort(key=lambda r: r.timestamp_ms)

        self._clip_by_kf_uid: Dict[str, BtcClipRowRecord] = {}
        if clip_rowmaps:
            for rm in clip_rowmaps:
                self._clip_by_kf_uid[rm.keyframe_uid] = rm

        self._objects_by_kf_uid: Dict[str, List[BtcObjectDetectionRecord]] = {}
        if object_detections:
            for det in object_detections:
                self._objects_by_kf_uid.setdefault(det.keyframe_uid, []).append(det)

        self._obj_cov_by_kf_uid: Dict[str, BtcObjectCoverageRecord] = {}
        if object_coverage:
            for cov in object_coverage:
                self._obj_cov_by_kf_uid[cov.keyframe_uid] = cov

        self._media_by_video_id: Dict[str, BtcMediaInfoRecord] = {}
        if media_info:
            for m in media_info:
                self._media_by_video_id[m.video_id] = m

    @property
    def total_keyframes(self) -> int:
        return len(self._keyframes_by_uid)

    @property
    def total_videos(self) -> int:
        return len(self._keyframes_by_vid)

    def get_btc_keyframe(self, keyframe_uid: str) -> Optional[BtcKeyframeRecord]:
        return self._keyframes_by_uid.get(keyframe_uid)

    def get_btc_keyframe_by_video_n(self, video_id: str, n: int) -> Optional[BtcKeyframeRecord]:
        return self._keyframes_by_vid_n.get((video_id, n))

    def get_btc_keyframes_by_video(self, video_id: str) -> List[BtcKeyframeRecord]:
        return list(self._keyframes_by_vid.get(video_id, []))

    def iter_btc_keyframes(self, video_id: Optional[str] = None) -> Iterator[BtcKeyframeRecord]:
        if video_id is not None:
            yield from self._keyframes_by_vid.get(video_id, [])
        else:
            for kfs in self._keyframes_by_vid.values():
                yield from kfs

    def get_btc_clip_ref(self, keyframe_uid: str) -> Optional[BtcClipRowRecord]:
        return self._clip_by_kf_uid.get(keyframe_uid)

    def get_btc_objects(self, keyframe_uid: str) -> List[BtcObjectDetectionRecord]:
        return self._objects_by_kf_uid.get(keyframe_uid, [])

    def get_btc_object_coverage(self, keyframe_uid: str) -> Optional[BtcObjectCoverageRecord]:
        return self._obj_cov_by_kf_uid.get(keyframe_uid)

    def get_media_info(self, video_id: str) -> Optional[BtcMediaInfoRecord]:
        return self._media_by_video_id.get(video_id)

    def get_btc_keyframes_near(
        self, video_id: str, timestamp_ms: int, window_ms: int = 5000
    ) -> List[BtcKeyframeRecord]:
        """Return all BTC keyframes in [timestamp_ms - window_ms, timestamp_ms + window_ms] for video_id."""
        kfs = self._keyframes_by_vid.get(video_id, [])
        t_min = timestamp_ms - window_ms
        t_max = timestamp_ms + window_ms
        return [k for k in kfs if t_min <= k.timestamp_ms <= t_max]

    def get_nearest_btc_keyframe(
        self, video_id: str, timestamp_ms: int
    ) -> Optional[BtcKeyframeRecord]:
        """Return the closest BTC keyframe in time for video_id."""
        kfs = self._keyframes_by_vid.get(video_id, [])
        if not kfs:
            return None
        return min(kfs, key=lambda k: abs(k.timestamp_ms - timestamp_ms))

    @classmethod
    def load_from_dir(
        cls,
        directory: Path,
        load_objects: bool = True,
        load_clip: bool = True,
        load_media: bool = True,
    ) -> BtcRegistry:
        """Load canonical BTC Data Hub artifacts from a materialized directory."""
        directory = Path(directory)

        # Load keyframes
        kf_file = directory / "btc_keyframes.jsonl"
        keyframes: List[BtcKeyframeRecord] = []
        if kf_file.exists():
            with open(kf_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        keyframes.append(BtcKeyframeRecord.from_dict(json.loads(line)))

        # Load CLIP rowmaps
        clip_rowmaps: Optional[List[BtcClipRowRecord]] = None
        if load_clip:
            clip_file = directory / "btc_clip_raw_rowmap.jsonl"
            if clip_file.exists():
                clip_rowmaps = []
                with open(clip_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            clip_rowmaps.append(BtcClipRowRecord.from_dict(json.loads(line)))

        # Load objects & coverage
        object_detections: Optional[List[BtcObjectDetectionRecord]] = None
        object_coverage: Optional[List[BtcObjectCoverageRecord]] = None
        if load_objects:
            obj_file = directory / "btc_objects.jsonl"
            if obj_file.exists():
                object_detections = []
                with open(obj_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            object_detections.append(BtcObjectDetectionRecord.from_dict(json.loads(line)))

            cov_file = directory / "btc_object_coverage.jsonl"
            if cov_file.exists():
                object_coverage = []
                with open(cov_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            object_coverage.append(BtcObjectCoverageRecord.from_dict(json.loads(line)))

        # Load media info
        media_info: Optional[List[BtcMediaInfoRecord]] = None
        if load_media:
            media_file = directory / "media_info.jsonl"
            if media_file.exists():
                media_info = []
                with open(media_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            media_info.append(BtcMediaInfoRecord.from_dict(json.loads(line)))

        # Load btc_space
        btc_space: Optional[BtcSpace] = None
        space_file = directory / "btc_space.json"
        if space_file.exists():
            with open(space_file, "r", encoding="utf-8") as f:
                btc_space = BtcSpace.from_dict(json.load(f))

        return cls(
            keyframes=keyframes,
            clip_rowmaps=clip_rowmaps,
            object_detections=object_detections,
            object_coverage=object_coverage,
            media_info=media_info,
            btc_space=btc_space,
        )

    load_from_directory = load_from_dir
