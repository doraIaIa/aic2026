from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from aic2026.data_hub.models import VideoRecord, VideoSpace
from aic2026.data_hub.validator import VideoRegistryValidator


class VideoRegistry:
    """In-memory read interface and repository abstraction for canonical video records."""

    def __init__(
        self,
        records: List[VideoRecord],
        video_space: Optional[VideoSpace] = None,
    ) -> None:
        self._records = sorted(records, key=lambda r: r.ordinal)
        self._by_id: Dict[str, VideoRecord] = {r.video_id: r for r in self._records}
        self._by_ordinal: Dict[int, VideoRecord] = {r.ordinal: r for r in self._records}
        self._video_space = video_space

    @property
    def video_space(self) -> Optional[VideoSpace]:
        return self._video_space

    @property
    def video_space_id(self) -> str:
        if self._video_space:
            return self._video_space.video_space_id
        if self._records:
            return self._records[0].ordinal_space_id
        return ""

    @property
    def catalog_checksum(self) -> str:
        if self._video_space and self._video_space.catalog_checksum:
            return self._video_space.catalog_checksum
        return VideoRegistryValidator().compute_catalog_checksum(self._records)

    def video_count(self) -> int:
        return len(self._records)

    def get_video(self, video_id: str) -> Optional[VideoRecord]:
        return self._by_id.get(video_id)

    def get_video_by_ordinal(self, ordinal: int) -> Optional[VideoRecord]:
        return self._by_ordinal.get(ordinal)

    def iter_videos(self) -> Iterator[VideoRecord]:
        return iter(self._records)

    def list_video_ids(self) -> List[str]:
        return [r.video_id for r in self._records]

    def series_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self._records:
            counts[r.series] = counts.get(r.series, 0) + 1
        return counts

    def to_records(self) -> List[VideoRecord]:
        return list(self._records)

    @classmethod
    def load_from_jsonl(
        cls,
        videos_jsonl_path: Path | str,
        video_space_path: Optional[Path | str] = None,
        validate: bool = True,
    ) -> VideoRegistry:
        """Load canonical VideoRegistry from videos.jsonl and optional video_space.json."""
        v_path = Path(videos_jsonl_path)
        if not v_path.exists():
            raise FileNotFoundError(f"videos.jsonl not found at {v_path}")

        records: List[VideoRecord] = []
        with open(v_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(VideoRecord.from_dict(data))
                except Exception as e:
                    raise ValueError(f"Failed to parse line {line_no} of {v_path}: {e}") from e

        video_space: Optional[VideoSpace] = None
        if video_space_path is not None:
            s_path = Path(video_space_path)
            if s_path.exists():
                with open(s_path, "r", encoding="utf-8") as f:
                    video_space = VideoSpace.from_dict(json.load(f))

        if validate:
            validator = VideoRegistryValidator(
                expected_count=len(records),
                expected_ordinal_space_id=records[0].ordinal_space_id if records else "v1_natural_series_video",
            )
            res = validator.validate(records, video_space)
            if not res.is_valid:
                raise ValueError(f"VideoRegistry validation failed: {res.errors}")

        return cls(records=records, video_space=video_space)

    @classmethod
    def load_from_directory(
        cls,
        catalog_dir: Path | str,
        validate: bool = True,
    ) -> VideoRegistry:
        """Convenience loader from a standard catalog directory containing videos.jsonl and video_space.json."""
        d = Path(catalog_dir)
        v_file = d / "videos.jsonl"
        s_file = d / "video_space.json"
        return cls.load_from_jsonl(
            videos_jsonl_path=v_file,
            video_space_path=s_file if s_file.exists() else None,
            validate=validate,
        )
