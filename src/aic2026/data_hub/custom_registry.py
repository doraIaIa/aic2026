from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from aic2026.data_hub.custom_models import (
    CustomKeyframeRecord,
    CustomSpace,
    QwenMissingRecord,
    QwenSemanticRecord,
)
from aic2026.data_hub.custom_validator import CustomKeyframeValidator
from aic2026.data_hub.video_registry import VideoRegistry


class CustomKeyframeRegistry:
    """In-memory read interface and repository abstraction for CUSTOM keyframes and Qwen semantics."""

    def __init__(
        self,
        custom_records: List[CustomKeyframeRecord],
        qwen_records: Optional[List[QwenSemanticRecord]] = None,
        missing_records: Optional[List[QwenMissingRecord]] = None,
        custom_space: Optional[CustomSpace] = None,
    ) -> None:
        self._custom_records = sorted(custom_records, key=lambda r: (r.video_ordinal, r.frame_idx))
        self._custom_by_uid: Dict[str, CustomKeyframeRecord] = {r.keyframe_uid: r for r in self._custom_records}
        self._custom_by_video_frame: Dict[Tuple[str, int], CustomKeyframeRecord] = {
            (r.video_id, r.frame_idx): r for r in self._custom_records
        }

        self._qwen_records = qwen_records or []
        self._qwen_by_uid: Dict[str, QwenSemanticRecord] = {q.keyframe_uid: q for q in self._qwen_records}
        self._qwen_by_video_frame: Dict[Tuple[str, int], QwenSemanticRecord] = {
            (q.video_id, q.frame_idx): q for q in self._qwen_records
        }

        self._missing_records = missing_records or []
        self._missing_by_uid: Dict[str, QwenMissingRecord] = {m.keyframe_uid: m for m in self._missing_records}
        self._custom_space = custom_space

    @property
    def custom_space(self) -> Optional[CustomSpace]:
        return self._custom_space

    @property
    def custom_space_id(self) -> str:
        if self._custom_space:
            return self._custom_space.custom_space_id
        return "custom_keyframes_v1"

    def keyframe_count(self) -> int:
        return len(self._custom_records)

    def qwen_count(self) -> int:
        return len(self._qwen_records)

    def qwen_missing_count(self) -> int:
        return len(self._missing_records)

    def get_custom_keyframe(self, keyframe_uid: str) -> Optional[CustomKeyframeRecord]:
        return self._custom_by_uid.get(keyframe_uid)

    def get_custom_keyframe_by_video_frame(self, video_id: str, frame_idx: int) -> Optional[CustomKeyframeRecord]:
        return self._custom_by_video_frame.get((video_id, frame_idx))

    def iter_custom_keyframes(self, video_id: Optional[str] = None) -> Iterator[CustomKeyframeRecord]:
        if video_id is None:
            return iter(self._custom_records)
        return (r for r in self._custom_records if r.video_id == video_id)

    def get_qwen(self, keyframe_uid: str) -> Optional[QwenSemanticRecord]:
        return self._qwen_by_uid.get(keyframe_uid)

    def get_qwen_by_video_frame(self, video_id: str, frame_idx: int) -> Optional[QwenSemanticRecord]:
        return self._qwen_by_video_frame.get((video_id, frame_idx))

    def qwen_status(self, keyframe_uid: str) -> str:
        if keyframe_uid in self._qwen_by_uid:
            return "OK"
        if keyframe_uid in self._missing_by_uid:
            return "MISSING"
        if keyframe_uid in self._custom_by_uid:
            return self._custom_by_uid[keyframe_uid].qwen_status
        return "UNKNOWN"

    def to_custom_records(self) -> List[CustomKeyframeRecord]:
        return list(self._custom_records)

    def to_qwen_records(self) -> List[QwenSemanticRecord]:
        return list(self._qwen_records)

    @classmethod
    def load_from_directory(
        cls,
        catalog_dir: Path | str,
        video_registry: Optional[VideoRegistry] = None,
        validate: bool = True,
    ) -> CustomKeyframeRegistry:
        """Load CustomKeyframeRegistry from catalog directory containing custom_keyframes.jsonl and qwen_semantics_normalized.jsonl."""
        d = Path(catalog_dir)
        c_file = d / "custom_keyframes.jsonl"
        q_file = d / "qwen_semantics_normalized.jsonl"
        m_file = d / "qwen_missing_keyframes.jsonl"
        s_file = d / "custom_space.json"

        if not c_file.exists():
            raise FileNotFoundError(f"custom_keyframes.jsonl not found at {c_file}")

        custom_records: List[CustomKeyframeRecord] = []
        with open(c_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    custom_records.append(CustomKeyframeRecord.from_dict(json.loads(line)))

        qwen_records: List[QwenSemanticRecord] = []
        if q_file.exists():
            with open(q_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        qwen_records.append(QwenSemanticRecord.from_dict(json.loads(line)))

        missing_records: List[QwenMissingRecord] = []
        if m_file.exists():
            with open(m_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        missing_records.append(QwenMissingRecord.from_dict(json.loads(line)))

        custom_space: Optional[CustomSpace] = None
        if s_file.exists():
            with open(s_file, "r", encoding="utf-8") as f:
                custom_space = CustomSpace.from_dict(json.load(f))

        if validate:
            validator = CustomKeyframeValidator(
                expected_keyframe_count=len(custom_records),
                expected_video_count=len(set(r.video_id for r in custom_records)),
                video_registry=video_registry,
            )
            res = validator.validate(custom_records, qwen_records, missing_records, custom_space)
            if not res.is_valid:
                raise ValueError(f"CustomKeyframeRegistry validation failed: {res.errors}")

        return cls(
            custom_records=custom_records,
            qwen_records=qwen_records,
            missing_records=missing_records,
            custom_space=custom_space,
        )
