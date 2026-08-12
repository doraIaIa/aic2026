from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from aic2026.search.asr import main as search_main
from aic2026.search.asr import search_asr
from aic2026.search.build_asr_index import AsrIndexBuildError, build_asr_search_index


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    inventory = tmp_path / "videos.jsonl"
    asr_videos = tmp_path / "asr_videos.jsonl"
    segments = tmp_path / "asr_segments.jsonl"
    database = tmp_path / "aic.sqlite"
    _write_jsonl(inventory, [
        {"video_id": "V1", "relative_path": "video/V1.mp4"},
        {"video_id": "V2", "relative_path": "video/V2.mp4"},
        {"video_id": "V3", "relative_path": "video/V3.mp4"},
    ])
    _write_jsonl(asr_videos, [
        {"video_id": "V1", "duration_sec": 20.0, "segment_count": 2, "status": "OK"},
        {"video_id": "V2", "duration_sec": 20.0, "segment_count": 1, "status": "OK"},
        {"video_id": "V3", "duration_sec": 20.0, "segment_count": 1, "status": "OK"},
    ])
    common = {
        "language": "vi", "model": "medium", "avg_logprob": -0.1,
        "no_speech_prob": 0.01, "compression_ratio": 1.1,
        "batch_id": "batch-0", "source_file": "asr_segments.jsonl",
    }
    _write_jsonl(segments, [
        {**common, "segment_id": "V1:000000", "video_id": "V1", "start_sec": 0.0,
         "end_sec": 4.0, "text": "Chào mừng quý vị đến chương trình 60 giây",
         "source_video_path": "video/V1.mp4"},
        {**common, "segment_id": "V1:000001", "video_id": "V1", "start_sec": 4.0,
         "end_sec": 8.0, "text": "Tin tức thành phố Hồ Chí Minh",
         "source_video_path": "video/V1.mp4"},
        {**common, "segment_id": "V2:000000", "video_id": "V2", "start_sec": 1.0,
         "end_sec": 5.0, "text": "Thành phố chuẩn bị ứng phó bão lũ",
         "source_video_path": "video/V2.mp4"},
        {**common, "segment_id": "V3:000000", "video_id": "V3", "start_sec": 2.0,
         "end_sec": 6.0, "text": "Chào mừng đoàn khách quốc tế",
         "source_video_path": "video/V3.mp4"},
    ])
    return database, inventory, asr_videos, segments


def _build(tmp_path: Path, *, force: bool = False) -> dict:
    database, inventory, asr_videos, segments = _fixture(tmp_path)
    return build_asr_search_index(
        database,
        inventory,
        asr_videos,
        segments,
        Path("src/aic2026/db/schema.sql"),
        expected_videos=3,
        expected_segments=4,
        force=force,
        report_json=tmp_path / "report.json",
        report_markdown=tmp_path / "report.md",
    )


def test_build_search_validate_and_idempotency(tmp_path: Path) -> None:
    report = _build(tmp_path)
    database = tmp_path / "aic.sqlite"

    assert report["verdict"] == "PASS"
    assert report["validation"]["checks"]["videos_count"] == 3
    assert report["validation"]["checks"]["asr_segments_count"] == 4
    assert report["validation"]["checks"]["fts_count"] == 4
    assert (tmp_path / "report.json").is_file()
    assert (tmp_path / "report.md").is_file()
    assert not list(tmp_path.glob("*.building.*"))
    assert search_asr(database, "60 giây", limit=20)[0]["video_id"] == "V1"
    assert search_asr(database, "thanh pho", limit=20)
    phrase = search_asr(database, '"chào mừng quý vị"', video_id="V1")
    assert len(phrase) == 1
    assert phrase[0]["segment_id"] == "V1:000000"
    assert phrase[0]["source_video_path"] == "video/V1.mp4"

    second = _build(tmp_path)
    assert second["status"] == "ALREADY_VALID"


def test_force_rebuild_preserves_unrelated_tables_and_makes_backup(tmp_path: Path) -> None:
    _build(tmp_path)
    database = tmp_path / "aic.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE user_notes(id INTEGER PRIMARY KEY, note TEXT)")
        connection.execute("INSERT INTO user_notes(note) VALUES ('keep me')")
        connection.commit()
    report = _build(tmp_path, force=True)

    assert Path(report["backup_database"]).is_file()
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT note FROM user_notes").fetchone()[0] == "keep me"
        assert connection.execute("SELECT COUNT(*) FROM asr_segments").fetchone()[0] == 4


def test_builder_rejects_partial_and_duplicate_segments(tmp_path: Path) -> None:
    database, inventory, asr_videos, segments = _fixture(tmp_path)
    partial = tmp_path / "asr_segments.partial.jsonl"
    partial.write_bytes(segments.read_bytes())
    with pytest.raises(AsrIndexBuildError, match="Partial JSONL"):
        build_asr_search_index(
            database, inventory, asr_videos, partial, Path("src/aic2026/db/schema.sql"),
            expected_videos=3, expected_segments=4,
        )

    rows = [json.loads(line) for line in segments.read_text(encoding="utf-8").splitlines()]
    rows.append(rows[0])
    _write_jsonl(segments, rows)
    with pytest.raises(AsrIndexBuildError, match="integrity failure"):
        build_asr_search_index(
            database, inventory, asr_videos, segments, Path("src/aic2026/db/schema.sql"),
            expected_videos=3, expected_segments=5,
        )


def test_search_cli_json_and_invalid_query(tmp_path: Path, capsys) -> None:
    _build(tmp_path)
    database = tmp_path / "aic.sqlite"
    assert search_main(["bão lũ", "--database", str(database), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["video_id"] == "V2"
    assert search_main(["\"unterminated", "--database", str(database)]) == 2
    assert "FTS query failed" in capsys.readouterr().err
