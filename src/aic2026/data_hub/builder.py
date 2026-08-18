from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.data_hub.models import SourceRecord, VideoRecord, VideoSpace
from aic2026.data_hub.validator import VideoRegistryValidator


_SERIES_VIDEO_REGEX = re.compile(r"^L(\d+)_V(\d+)$")


def natural_video_sort_key(video_id: str) -> Tuple[int, int, str]:
    """Deterministic natural sort key for video IDs like L21_V001 -> (21, 1, 'L21_V001')."""
    match = _SERIES_VIDEO_REGEX.match(video_id)
    if match:
        return (int(match.group(1)), int(match.group(2)), video_id)
    # Fallback for unexpected format: sort string
    return (999999, 999999, video_id)


def build_canonical_video_records(
    raw_video_items: List[Dict[str, Any]],
    ordinal_space_id: str = "v1_natural_series_video",
    source_id: str = "canonical_video_universe_v1",
) -> List[VideoRecord]:
    """Build deterministically sorted and indexed VideoRecords from raw metadata items."""
    # Deduplicate and extract unique video IDs
    unique_items_map: Dict[str, Dict[str, Any]] = {}
    for item in raw_video_items:
        v_id = item.get("video_id") or item.get("video_name") or item.get("id")
        if not v_id:
            continue
        v_id = str(v_id).strip()
        if v_id not in unique_items_map:
            unique_items_map[v_id] = item

    # Sort deterministically by natural order
    sorted_video_ids = sorted(unique_items_map.keys(), key=natural_video_sort_key)

    records: List[VideoRecord] = []
    for ordinal, v_id in enumerate(sorted_video_ids):
        raw_meta = unique_items_map[v_id]
        series = v_id.split("_")[0] if "_" in v_id else ""

        # Normalize relative path: ensure slashes are normalized
        source_relpath = raw_meta.get("source_relpath") or raw_meta.get("source_video_path") or raw_meta.get("relpath")
        if not source_relpath:
            source_relpath = f"data_extracted/video/{v_id}.mp4"
        else:
            source_relpath = str(source_relpath).replace("\\", "/")

        # Convert duration to milliseconds if duration_sec is present
        duration_sec = raw_meta.get("duration_sec")
        duration_ms = raw_meta.get("duration_ms")
        if duration_ms is None and duration_sec is not None:
            try:
                duration_ms = int(round(float(duration_sec) * 1000))
            except (ValueError, TypeError):
                duration_ms = None

        record = VideoRecord(
            video_id=v_id,
            ordinal=ordinal,
            ordinal_space_id=ordinal_space_id,
            series=series,
            source_relpath=source_relpath,
            duration_ms=duration_ms,
            duration_sec=float(duration_sec) if duration_sec is not None else None,
            fps=float(raw_meta["fps"]) if "fps" in raw_meta and raw_meta["fps"] is not None else None,
            width=int(raw_meta["width"]) if "width" in raw_meta and raw_meta["width"] is not None else None,
            height=int(raw_meta["height"]) if "height" in raw_meta and raw_meta["height"] is not None else None,
            status_flags=raw_meta.get("status_flags", "OK"),
            source_id=source_id,
            schema_version="v1",
        )
        records.append(record)

    return records


def materialize_video_catalog(
    records: List[VideoRecord],
    output_dir: Path | str,
    source_records: Optional[List[SourceRecord]] = None,
    video_space_id: str = "v1_natural_series_video",
    validate: bool = True,
) -> Tuple[Path, Path, Path]:
    """Materialize canonical videos.jsonl, source_registry.jsonl, and video_space.json to output directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    validator = VideoRegistryValidator(expected_count=len(records), expected_ordinal_space_id=video_space_id)
    checksum = validator.compute_catalog_checksum(records)

    # Series counts
    series_counts: Dict[str, int] = {}
    for r in records:
        series_counts[r.series] = series_counts.get(r.series, 0) + 1

    video_space = VideoSpace(
        video_space_id=video_space_id,
        schema_version="v1",
        video_count=len(records),
        ordering_rule="natural_sort_series_video_asc",
        catalog_checksum=checksum,
        created_at=datetime.now(timezone.utc).isoformat(),
        series_counts=series_counts,
    )

    if validate:
        res = validator.validate(records, video_space)
        if not res.is_valid:
            raise ValueError(f"Catalog validation failed before materialization: {res.errors}")

    # 1. Write videos.jsonl
    videos_file = out / "videos.jsonl"
    jsonl_content = "\n".join(json.dumps(r.to_dict(), ensure_ascii=False) for r in records) + "\n"
    atomic_write_text(videos_file, jsonl_content)

    # 2. Write source_registry.jsonl
    source_file = out / "source_registry.jsonl"
    sources = source_records or [
        SourceRecord(
            source_id="canonical_video_universe_v1",
            source_type="SOURCE_VIDEO_CATALOG",
            scope="CANONICAL_VIDEO_UNIVERSE",
            relative_path_or_logical_ref="videos.jsonl",
            schema_version="v1",
            record_count=len(records),
            checksum=checksum,
            producer="aic2026.data_hub.builder",
            status="READY",
            notes=["Canonical 873-video universe with deterministic natural ordinal 0..872"],
        )
    ]
    source_jsonl = "\n".join(json.dumps(s.to_dict(), ensure_ascii=False) for s in sources) + "\n"
    atomic_write_text(source_file, source_jsonl)

    # 3. Write video_space.json (Passport metadata)
    space_file = out / "video_space.json"
    atomic_write_json(space_file, video_space.to_dict())

    return (videos_file, source_file, space_file)
