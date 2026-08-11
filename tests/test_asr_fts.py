from __future__ import annotations

import json
from pathlib import Path

import pytest

from aic2026.asr.fts import build_asr_fts, search_asr
from aic2026.asr.manifest import AsrContractError


def test_build_and_search_asr_fts(tmp_path: Path) -> None:
    segments = tmp_path / "segments.jsonl"
    rows = [
        {"segment_id": "V1:000000", "video_id": "V1", "start_sec": 0.0, "end_sec": 2.0,
         "text": "Thành phố Hồ Chí Minh đón đoàn khách", "source_video_path": "video/V1.mp4"},
        {"segment_id": "V2:000000", "video_id": "V2", "start_sec": 3.0, "end_sec": 5.0,
         "text": "Dự báo thời tiết ngày mai", "source_video_path": "video/V2.mp4"},
    ]
    segments.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    index = tmp_path / "asr-fts"

    summary = build_asr_fts(segments, index)
    results = search_asr(index, "Hồ Chí Minh", top_k=20)

    assert summary["segment_count"] == 2
    assert (index / "DONE.json").is_file()
    assert (index / "checksum.sha256").is_file()
    assert results[0]["video_id"] == "V1"
    assert results[0]["start_sec"] == 0.0
    with pytest.raises(AsrContractError, match="đã tồn tại"):
        build_asr_fts(segments, index)


def test_asr_fts_rejects_malformed_segment(tmp_path: Path) -> None:
    segments = tmp_path / "segments.jsonl"
    segments.write_text(json.dumps({
        "segment_id": "bad", "video_id": "V1", "start_sec": 3, "end_sec": 2, "text": "x",
    }) + "\n", encoding="utf-8")
    with pytest.raises(AsrContractError, match="malformed"):
        build_asr_fts(segments, tmp_path / "asr-fts")
