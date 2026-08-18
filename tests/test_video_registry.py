from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from aic2026.data_hub.builder import (
    build_canonical_video_records,
    materialize_video_catalog,
    natural_video_sort_key,
)
from aic2026.data_hub.models import SourceRecord, VideoRecord, VideoSpace
from aic2026.data_hub.validator import (
    EXPECTED_SERIES_COUNTS_873,
    VideoRegistryValidator,
)
from aic2026.data_hub.video_registry import VideoRegistry


def _generate_synthetic_873_items() -> List[Dict[str, Any]]:
    """Helper to generate standard 873 video metadata items for testing."""
    items = []
    series_map = {
        "L21": 29,
        "L22": 31,
        "L23": 25,
        "L24": 43,
        "L25": 88,
        "L26": 498,
        "L27": 16,
        "L28": 24,
        "L29": 23,
        "L30": 96,
    }
    for series, count in series_map.items():
        for i in range(1, count + 1):
            v_id = f"{series}_V{i:03d}"
            items.append({
                "video_id": v_id,
                "duration_sec": 120.5,
                "source_relpath": f"data_extracted/video/{v_id}.mp4",
                "fps": 25.0,
                "width": 1280,
                "height": 720,
            })
    return items


def test_natural_video_sort_key():
    """Verify natural sort orders series and video numbers numerically, not lexicographically."""
    unsorted = ["L26_V100", "L21_V002", "L21_V001", "L21_V010", "L30_V001", "L26_V002"]
    sorted_ids = sorted(unsorted, key=natural_video_sort_key)
    assert sorted_ids == ["L21_V001", "L21_V002", "L21_V010", "L26_V002", "L26_V100", "L30_V001"]


def test_canonical_video_records_builder_873():
    """Verify builder produces exactly 873 records with 0..872 ordinals and duration_ms conversion."""
    raw_items = _generate_synthetic_873_items()
    records = build_canonical_video_records(raw_items)

    assert len(records) == 873
    assert records[0].video_id == "L21_V001"
    assert records[0].ordinal == 0
    assert records[0].duration_ms == 120500
    assert records[-1].video_id == "L30_V096"
    assert records[-1].ordinal == 872

    # Check validator passes
    validator = VideoRegistryValidator(expected_count=873)
    res = validator.validate(records)
    assert res.is_valid is True
    assert res.errors == []
    assert res.series_counts == EXPECTED_SERIES_COUNTS_873


def test_validation_rejects_duplicate_video_id():
    """Validator fails closed when duplicate video IDs exist."""
    raw_items = _generate_synthetic_873_items()
    records = build_canonical_video_records(raw_items)
    # Inject duplicate
    bad_records = list(records)
    bad_records[1] = VideoRecord(
        video_id="L21_V001",  # duplicate of record 0
        ordinal=1,
        ordinal_space_id="v1_natural_series_video",
        series="L21",
        source_relpath="data_extracted/video/L21_V001.mp4",
    )
    validator = VideoRegistryValidator(expected_count=873)
    res = validator.validate(bad_records)
    assert res.is_valid is False
    assert any("DUPLICATE_VIDEO_ID" in err for err in res.errors)


def test_validation_rejects_duplicate_ordinal():
    """Validator fails closed when duplicate ordinals exist."""
    raw_items = _generate_synthetic_873_items()
    records = build_canonical_video_records(raw_items)
    bad_records = list(records)
    bad_records[1] = VideoRecord(
        video_id=records[1].video_id,
        ordinal=0,  # duplicate ordinal 0
        ordinal_space_id="v1_natural_series_video",
        series=records[1].series,
        source_relpath=records[1].source_relpath,
    )
    validator = VideoRegistryValidator(expected_count=873)
    res = validator.validate(bad_records)
    assert res.is_valid is False
    assert any("DUPLICATE_ORDINAL" in err for err in res.errors)


def test_validation_rejects_absolute_windows_path():
    """Validator fails closed if a canonical source path contains a Windows drive letter."""
    raw_items = _generate_synthetic_873_items()
    raw_items[0]["source_relpath"] = r"G:\AIC_2026\data_extracted\video\L21_V001.mp4"
    records = build_canonical_video_records(raw_items)
    validator = VideoRegistryValidator(expected_count=873)
    res = validator.validate(records)
    assert res.is_valid is False
    assert any("ABSOLUTE_PATH_FORBIDDEN" in err for err in res.errors)


def test_validation_rejects_absolute_posix_path():
    """Validator fails closed if a canonical source path contains an absolute POSIX root."""
    raw_items = _generate_synthetic_873_items()
    raw_items[0]["source_relpath"] = "/content/drive/MyDrive/data_extracted/video/L21_V001.mp4"
    records = build_canonical_video_records(raw_items)
    validator = VideoRegistryValidator(expected_count=873)
    res = validator.validate(records)
    assert res.is_valid is False
    assert any("ABSOLUTE_PATH_FORBIDDEN" in err for err in res.errors)


def test_validation_rejects_path_traversal():
    """Validator fails closed if a canonical source path contains '..'."""
    raw_items = _generate_synthetic_873_items()
    raw_items[0]["source_relpath"] = "../secret/L21_V001.mp4"
    records = build_canonical_video_records(raw_items)
    validator = VideoRegistryValidator(expected_count=873)
    res = validator.validate(records)
    assert res.is_valid is False
    assert any("PATH_TRAVERSAL_FORBIDDEN" in err for err in res.errors)


def test_validation_rejects_malformed_video_id():
    """Validator fails closed if video_id does not conform to standard format."""
    raw_items = _generate_synthetic_873_items()
    raw_items[0]["video_id"] = "INVALID_NAME_999"
    records = build_canonical_video_records(raw_items)
    validator = VideoRegistryValidator(expected_count=873)
    res = validator.validate(records)
    assert res.is_valid is False
    assert any("MALFORMED_VIDEO_ID" in err for err in res.errors)


def test_validation_rejects_series_count_mismatch():
    """Validator fails closed if total count is 873 but series distribution deviates from frozen universe."""
    raw_items = _generate_synthetic_873_items()
    # Move one item from L21 to L22
    raw_items[0]["video_id"] = "L22_V999"
    records = build_canonical_video_records(raw_items)
    validator = VideoRegistryValidator(expected_count=873)
    res = validator.validate(records)
    assert res.is_valid is False
    assert any("SERIES_COUNT_MISMATCH" in err for err in res.errors)


def test_validation_rejects_ordinal_space_mismatch():
    """Validator fails closed if an entry belongs to an unexpected ordinal space."""
    raw_items = _generate_synthetic_873_items()
    records = build_canonical_video_records(raw_items, ordinal_space_id="unexpected_space_id")
    validator = VideoRegistryValidator(expected_count=873, expected_ordinal_space_id="v1_natural_series_video")
    res = validator.validate(records)
    assert res.is_valid is False
    assert any("ORDINAL_SPACE_MISMATCH" in err for err in res.errors)


def test_materialization_and_read_api(tmp_path: Path):
    """Verify materializer creates JSONL/Passport files and VideoRegistry read interface works."""
    raw_items = _generate_synthetic_873_items()
    records = build_canonical_video_records(raw_items)

    out_dir = tmp_path / "canonical"
    v_file, s_file, p_file = materialize_video_catalog(records, out_dir)

    assert v_file.exists()
    assert s_file.exists()
    assert p_file.exists()

    # Load via directory
    registry = VideoRegistry.load_from_directory(out_dir)
    assert registry.video_count() == 873
    assert registry.video_space_id == "v1_natural_series_video"

    # Query by ID
    v = registry.get_video("L21_V001")
    assert v is not None
    assert v.ordinal == 0
    assert v.series == "L21"

    # Query by ordinal
    v872 = registry.get_video_by_ordinal(872)
    assert v872 is not None
    assert v872.video_id == "L30_V096"

    # Non-existent
    assert registry.get_video("NON_EXISTENT") is None
    assert registry.get_video_by_ordinal(999) is None


def test_deterministic_builds_across_runs(tmp_path: Path):
    """Verify two independent materializations produce bit-for-bit identical checksums."""
    raw_items = _generate_synthetic_873_items()
    records1 = build_canonical_video_records(raw_items)
    records2 = build_canonical_video_records(list(reversed(raw_items)))  # reversed input order

    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"
    _, _, p1 = materialize_video_catalog(records1, dir1)
    _, _, p2 = materialize_video_catalog(records2, dir2)

    s1 = json.loads(p1.read_text(encoding="utf-8"))
    s2 = json.loads(p2.read_text(encoding="utf-8"))
    assert s1["catalog_checksum"] == s2["catalog_checksum"]
    assert s1["video_count"] == s2["video_count"] == 873


def test_cli_build_and_validate_subcommands(tmp_path: Path):
    """Verify CLI build-video-catalog and validate-video-catalog commands work end-to-end."""
    from aic2026.cli import main

    raw_items = _generate_synthetic_873_items()
    input_file = tmp_path / "raw_videos.jsonl"
    input_file.write_text("\n".join(json.dumps(r) for r in raw_items) + "\n", encoding="utf-8")

    out_dir = tmp_path / "cli_catalog"
    rc = main(["build-video-catalog", "--input", str(input_file), "--out", str(out_dir)])
    assert rc == 0

    assert (out_dir / "videos.jsonl").exists()
    assert (out_dir / "video_space.json").exists()
    assert (out_dir / "source_registry.jsonl").exists()

    # Validate via CLI
    rc_val = main(["validate-video-catalog", "--catalog-dir", str(out_dir)])
    assert rc_val == 0

