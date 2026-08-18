from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from aic2026.data_hub.asr_ocr_models import (
    AsrSegmentRecord,
    AsrVideoCoverageRecord,
    OcrBgeRowmapRecord,
    OcrItemRecord,
    OcrKeyframeCoverageRecord,
)


class AsrOcrRegistry:
    """Read API for canonical ASR speech intervals, OCR visible text, and BGE row mappings."""

    def __init__(
        self,
        asr_segments: Optional[List[AsrSegmentRecord]] = None,
        asr_coverage: Optional[List[AsrVideoCoverageRecord]] = None,
        ocr_keyframes: Optional[List[OcrKeyframeCoverageRecord]] = None,
        ocr_items: Optional[List[OcrItemRecord]] = None,
        bge_rowmaps: Optional[List[OcrBgeRowmapRecord]] = None,
    ) -> None:
        self._asr_segments_by_uid: Dict[str, AsrSegmentRecord] = {}
        self._asr_segments_by_video: Dict[str, List[AsrSegmentRecord]] = {}
        self._asr_coverage_by_video: Dict[str, AsrVideoCoverageRecord] = {}

        self._ocr_kf_by_uid: Dict[str, OcrKeyframeCoverageRecord] = {}
        self._ocr_items_by_uid: Dict[str, OcrItemRecord] = {}
        self._ocr_items_by_kf: Dict[str, List[OcrItemRecord]] = {}
        self._ocr_items_by_video: Dict[str, List[OcrItemRecord]] = {}
        self._bge_by_ocr_uid: Dict[str, OcrBgeRowmapRecord] = {}

        if asr_coverage:
            for cov in asr_coverage:
                self._asr_coverage_by_video[cov.video_id] = cov

        if asr_segments:
            for seg in asr_segments:
                self._asr_segments_by_uid[seg.segment_uid] = seg
                if seg.video_id not in self._asr_segments_by_video:
                    self._asr_segments_by_video[seg.video_id] = []
                self._asr_segments_by_video[seg.video_id].append(seg)

        if ocr_keyframes:
            for kf in ocr_keyframes:
                self._ocr_kf_by_uid[kf.keyframe_uid] = kf

        if ocr_items:
            for it in ocr_items:
                self._ocr_items_by_uid[it.ocr_uid] = it
                if it.keyframe_uid not in self._ocr_items_by_kf:
                    self._ocr_items_by_kf[it.keyframe_uid] = []
                self._ocr_items_by_kf[it.keyframe_uid].append(it)
                if it.video_id not in self._ocr_items_by_video:
                    self._ocr_items_by_video[it.video_id] = []
                self._ocr_items_by_video[it.video_id].append(it)

        if bge_rowmaps:
            for rm in bge_rowmaps:
                self._bge_by_ocr_uid[rm.ocr_uid] = rm

    # ------------------------------------------------------------------
    # ASR Query APIs
    # ------------------------------------------------------------------
    def get_asr_segment(self, segment_uid: str) -> Optional[AsrSegmentRecord]:
        return self._asr_segments_by_uid.get(segment_uid)

    def get_asr_video_status(self, video_id: str) -> Optional[AsrVideoCoverageRecord]:
        return self._asr_coverage_by_video.get(video_id)

    def iter_asr_segments(self, video_id: Optional[str] = None) -> Iterator[AsrSegmentRecord]:
        if video_id is not None:
            yield from self._asr_segments_by_video.get(video_id, [])
        else:
            for segs in self._asr_segments_by_video.values():
                yield from segs

    def get_asr_near(self, video_id: str, timestamp_ms: int, window_ms: int = 5000) -> List[AsrSegmentRecord]:
        """Find ASR speech segments overlapping with or within window_ms around timestamp_ms."""
        segs = self._asr_segments_by_video.get(video_id, [])
        t_min = max(0, timestamp_ms - window_ms)
        t_max = timestamp_ms + window_ms
        return [s for s in segs if not (s.end_ms < t_min or s.start_ms > t_max)]

    def get_asr_overlapping(self, video_id: str, start_ms: int, end_ms: int) -> List[AsrSegmentRecord]:
        """Find ASR speech segments strictly overlapping with the interval [start_ms, end_ms]."""
        segs = self._asr_segments_by_video.get(video_id, [])
        return [s for s in segs if not (s.end_ms < start_ms or s.start_ms > end_ms)]

    # ------------------------------------------------------------------
    # OCR Query APIs
    # ------------------------------------------------------------------
    def get_keyframe_coverage(self, keyframe_uid: str) -> Optional[OcrKeyframeCoverageRecord]:
        return self._ocr_kf_by_uid.get(keyframe_uid)

    def get_ocr(self, ocr_uid: str) -> Optional[OcrItemRecord]:
        return self._ocr_items_by_uid.get(ocr_uid)

    def iter_ocr_items(self, video_id: Optional[str] = None, keyframe_uid: Optional[str] = None) -> Iterator[OcrItemRecord]:
        if keyframe_uid is not None:
            yield from self._ocr_items_by_kf.get(keyframe_uid, [])
        elif video_id is not None:
            yield from self._ocr_items_by_video.get(video_id, [])
        else:
            for items in self._ocr_items_by_video.values():
                yield from items

    def get_ocr_for_keyframe(self, keyframe_uid: str) -> List[OcrItemRecord]:
        return list(self._ocr_items_by_kf.get(keyframe_uid, []))

    def get_ocr_near(self, video_id: str, timestamp_ms: int, window_ms: int = 5000) -> List[OcrItemRecord]:
        items = self._ocr_items_by_video.get(video_id, [])
        t_min = max(0, timestamp_ms - window_ms)
        t_max = timestamp_ms + window_ms
        return [it for it in items if t_min <= it.timestamp_ms <= t_max]

    def get_ocr_vector_ref(self, ocr_uid: str) -> Optional[OcrBgeRowmapRecord]:
        return self._bge_by_ocr_uid.get(ocr_uid)

    # ------------------------------------------------------------------
    # Factory Loaders
    # ------------------------------------------------------------------
    @classmethod
    def load_from_dir(cls, directory: Path) -> AsrOcrRegistry:
        directory = Path(directory)
        asr_segments: List[AsrSegmentRecord] = []
        asr_coverage: List[AsrVideoCoverageRecord] = []
        ocr_keyframes: List[OcrKeyframeCoverageRecord] = []
        ocr_items: List[OcrItemRecord] = []
        bge_rowmaps: List[OcrBgeRowmapRecord] = []

        cov_p = directory / "asr_video_coverage.jsonl"
        if cov_p.exists():
            with open(cov_p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        asr_coverage.append(AsrVideoCoverageRecord.from_dict(json.loads(line)))

        seg_p = directory / "asr_segments_canonical.jsonl"
        if seg_p.exists():
            with open(seg_p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        asr_segments.append(AsrSegmentRecord.from_dict(json.loads(line)))

        ocr_kf_p = directory / "ocr_keyframe_coverage.jsonl"
        if ocr_kf_p.exists():
            with open(ocr_kf_p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        ocr_keyframes.append(OcrKeyframeCoverageRecord.from_dict(json.loads(line)))

        ocr_it_p = directory / "ocr_items_canonical.jsonl"
        if ocr_it_p.exists():
            with open(ocr_it_p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        ocr_items.append(OcrItemRecord.from_dict(json.loads(line)))

        bge_p = directory / "ocr_bge_rowmap.jsonl"
        if bge_p.exists():
            with open(bge_p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        bge_rowmaps.append(OcrBgeRowmapRecord.from_dict(json.loads(line)))

        return cls(
            asr_segments=asr_segments,
            asr_coverage=asr_coverage,
            ocr_keyframes=ocr_keyframes,
            ocr_items=ocr_items,
            bge_rowmaps=bge_rowmaps,
        )
