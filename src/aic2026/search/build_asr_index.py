from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.core.config import load_config
from aic2026.core.hashing import sha256_bytes, sha256_file
from aic2026.core.paths import PathContractError, PathResolver, normalize_relpath
from aic2026.search.asr import AsrSearchError, search_asr


SCHEMA_VERSION = 1
DEFAULT_EXPECTED_VIDEOS = 873
DEFAULT_EXPECTED_SEGMENTS = 107_540
DEFAULT_SMOKE_QUERIES = ("60 giây", "thành phố", "chào mừng")


class AsrIndexBuildError(RuntimeError):
    """Production ASR search index failed integrity validation."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    if path.name.endswith(".partial.jsonl"):
        raise AsrIndexBuildError(f"Partial JSONL is forbidden: {path}")
    try:
        stream = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise AsrIndexBuildError(f"Cannot open input {path}: {exc}") from exc
    with stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AsrIndexBuildError(f"Invalid JSON at {path}:{line_number}") from exc
            if not isinstance(row, dict):
                raise AsrIndexBuildError(f"Expected object at {path}:{line_number}")
            yield line_number, row


def _required_text(row: dict[str, Any], field: str, source: Path, line_number: int) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AsrIndexBuildError(f"Missing {field} at {source}:{line_number}")
    return value.strip()


def _optional_float(value: Any, field: str, source: Path, line_number: int) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AsrIndexBuildError(f"Invalid {field} at {source}:{line_number}")
    return float(value)


def _create_asr_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TRIGGER IF EXISTS asr_segments_ai;
        DROP TRIGGER IF EXISTS asr_segments_ad;
        DROP TRIGGER IF EXISTS asr_segments_au;
        DROP TABLE IF EXISTS asr_segments_fts;
        DROP TABLE IF EXISTS asr_segments;

        CREATE TABLE asr_segments (
            segment_id TEXT PRIMARY KEY,
            video_id TEXT NOT NULL REFERENCES videos(video_id),
            start_sec REAL NOT NULL CHECK(start_sec >= 0),
            end_sec REAL NOT NULL CHECK(end_sec >= start_sec),
            text TEXT NOT NULL CHECK(length(trim(text)) > 0),
            language TEXT,
            model TEXT,
            avg_logprob REAL,
            no_speech_prob REAL,
            compression_ratio REAL,
            batch_id TEXT,
            source_file TEXT NOT NULL,
            source_video_path TEXT NOT NULL
        );

        CREATE INDEX idx_asr_segments_video_time
            ON asr_segments(video_id, start_sec, end_sec);

        CREATE VIRTUAL TABLE asr_segments_fts USING fts5(
            text,
            content='asr_segments',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        );

        CREATE TRIGGER asr_segments_ai AFTER INSERT ON asr_segments BEGIN
            INSERT INTO asr_segments_fts(rowid, text) VALUES (new.rowid, new.text);
        END;
        CREATE TRIGGER asr_segments_ad AFTER DELETE ON asr_segments BEGIN
            INSERT INTO asr_segments_fts(asr_segments_fts, rowid, text)
            VALUES('delete', old.rowid, old.text);
        END;
        CREATE TRIGGER asr_segments_au AFTER UPDATE ON asr_segments BEGIN
            INSERT INTO asr_segments_fts(asr_segments_fts, rowid, text)
            VALUES('delete', old.rowid, old.text);
            INSERT INTO asr_segments_fts(rowid, text) VALUES (new.rowid, new.text);
        END;
        """
    )


def _ensure_base_schema(connection: sqlite3.Connection, schema_path: Path) -> None:
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('asr_search_schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )


def _ingest_videos(
    connection: sqlite3.Connection,
    inventory_path: Path,
    asr_videos_path: Path,
) -> tuple[int, dict[str, float]]:
    inventory: dict[str, dict[str, Any]] = {}
    for line_number, row in _iter_jsonl(inventory_path):
        video_id = _required_text(row, "video_id", inventory_path, line_number)
        if video_id in inventory:
            raise AsrIndexBuildError(f"Duplicate inventory video_id: {video_id}")
        try:
            relpath = normalize_relpath(_required_text(row, "relative_path", inventory_path, line_number))
        except PathContractError as exc:
            raise AsrIndexBuildError(f"Invalid video path for {video_id}: {exc}") from exc
        inventory[video_id] = {**row, "relative_path": relpath}

    asr_videos: dict[str, dict[str, Any]] = {}
    durations: dict[str, float] = {}
    for line_number, row in _iter_jsonl(asr_videos_path):
        video_id = _required_text(row, "video_id", asr_videos_path, line_number)
        if video_id in asr_videos:
            raise AsrIndexBuildError(f"Duplicate ASR video_id: {video_id}")
        duration = _optional_float(row.get("duration_sec"), "duration_sec", asr_videos_path, line_number)
        if duration is None or duration < 0:
            raise AsrIndexBuildError(f"Invalid duration for {video_id}")
        if row.get("status") != "OK":
            raise AsrIndexBuildError(f"ASR video is not OK: {video_id}")
        asr_videos[video_id] = row
        durations[video_id] = duration
    if set(inventory) != set(asr_videos):
        missing_asr = sorted(set(inventory) - set(asr_videos))
        missing_inventory = sorted(set(asr_videos) - set(inventory))
        raise AsrIndexBuildError(
            f"Video authority mismatch: missing_asr={missing_asr[:5]}, "
            f"missing_inventory={missing_inventory[:5]}"
        )

    connection.executemany(
        """
        INSERT INTO videos(video_id, relpath, duration_sec, source_sha256)
        VALUES (?, ?, ?, NULL)
        ON CONFLICT(video_id) DO UPDATE SET
            relpath=excluded.relpath,
            duration_sec=excluded.duration_sec
        """,
        [
            (video_id, inventory[video_id]["relative_path"], durations[video_id])
            for video_id in sorted(inventory)
        ],
    )
    return len(inventory), durations


def _ingest_segments(
    connection: sqlite3.Connection,
    segments_path: Path,
    durations: dict[str, float],
    *,
    duration_tolerance_sec: float,
    batch_size: int = 2_000,
) -> tuple[int, Counter[str]]:
    sql = """
        INSERT INTO asr_segments(
            segment_id, video_id, start_sec, end_sec, text, language, model,
            avg_logprob, no_speech_prob, compression_ratio, batch_id,
            source_file, source_video_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    batch: list[tuple[Any, ...]] = []
    counts: Counter[str] = Counter()
    total = 0
    for line_number, row in _iter_jsonl(segments_path):
        segment_id = _required_text(row, "segment_id", segments_path, line_number)
        video_id = _required_text(row, "video_id", segments_path, line_number)
        if video_id not in durations:
            raise AsrIndexBuildError(f"Orphan segment {segment_id}: {video_id}")
        start = _optional_float(row.get("start_sec"), "start_sec", segments_path, line_number)
        end = _optional_float(row.get("end_sec"), "end_sec", segments_path, line_number)
        if start is None or end is None or start < 0 or end < start:
            raise AsrIndexBuildError(f"Invalid timestamp for {segment_id}")
        if end > durations[video_id] + duration_tolerance_sec:
            raise AsrIndexBuildError(
                f"Segment exceeds duration+tolerance: {segment_id} end={end} duration={durations[video_id]}"
            )
        text = _required_text(row, "text", segments_path, line_number)
        try:
            source_video_path = normalize_relpath(
                _required_text(row, "source_video_path", segments_path, line_number)
            )
        except PathContractError as exc:
            raise AsrIndexBuildError(f"Invalid source_video_path for {segment_id}: {exc}") from exc
        batch.append((
            segment_id,
            video_id,
            start,
            end,
            text,
            row.get("language"),
            row.get("model"),
            _optional_float(row.get("avg_logprob"), "avg_logprob", segments_path, line_number),
            _optional_float(row.get("no_speech_prob"), "no_speech_prob", segments_path, line_number),
            _optional_float(row.get("compression_ratio"), "compression_ratio", segments_path, line_number),
            row.get("batch_id"),
            _required_text(row, "source_file", segments_path, line_number),
            source_video_path,
        ))
        counts[video_id] += 1
        total += 1
        if len(batch) >= batch_size:
            try:
                connection.executemany(sql, batch)
            except sqlite3.IntegrityError as exc:
                raise AsrIndexBuildError(f"Segment integrity failure near {segment_id}: {exc}") from exc
            batch.clear()
    if batch:
        try:
            connection.executemany(sql, batch)
        except sqlite3.IntegrityError as exc:
            raise AsrIndexBuildError(f"Segment integrity failure: {exc}") from exc
    return total, counts


def validate_asr_search_db(
    database: str | Path,
    *,
    expected_videos: int,
    expected_segments: int,
) -> dict[str, Any]:
    db_path = Path(database)
    with closing(sqlite3.connect(db_path)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        videos = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        segments = connection.execute("SELECT COUNT(*) FROM asr_segments").fetchone()[0]
        fts_rows = connection.execute("SELECT COUNT(*) FROM asr_segments_fts").fetchone()[0]
        orphans = connection.execute(
            """
            SELECT COUNT(*) FROM asr_segments s
            LEFT JOIN videos v ON v.video_id = s.video_id
            WHERE v.video_id IS NULL
            """
        ).fetchone()[0]
        duplicate_segments = connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT segment_id FROM asr_segments GROUP BY segment_id HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        fts_check = connection.execute(
            "INSERT INTO asr_segments_fts(asr_segments_fts) VALUES('integrity-check')"
        ).fetchone()
    errors: list[str] = []
    checks = {
        "integrity_check": integrity,
        "videos_count": videos,
        "asr_segments_count": segments,
        "fts_count": fts_rows,
        "orphan_segments": orphans,
        "duplicate_segment_ids": duplicate_segments,
        "fts_integrity_check": "ok" if fts_check is None else str(fts_check),
    }
    if integrity != "ok":
        errors.append(f"SQLite integrity_check={integrity}")
    if videos != expected_videos:
        errors.append(f"videos_count={videos}, expected={expected_videos}")
    if segments != expected_segments:
        errors.append(f"asr_segments_count={segments}, expected={expected_segments}")
    if fts_rows != expected_segments:
        errors.append(f"fts_count={fts_rows}, expected={expected_segments}")
    if orphans != 0:
        errors.append(f"orphan_segments={orphans}")
    if duplicate_segments != 0:
        errors.append(f"duplicate_segment_ids={duplicate_segments}")
    return {"valid": not errors, "checks": checks, "errors": errors}


def _source_fingerprint(paths: list[Path], config: dict[str, Any]) -> tuple[dict[str, str], str]:
    checksums = {path.name: sha256_file(path) for path in paths}
    payload = {"schema_version": SCHEMA_VERSION, "inputs": checksums, "config": config}
    return checksums, sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def _current_fingerprint(database: Path) -> str | None:
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key='asr_search_input_fingerprint'"
            ).fetchone()
            return row[0] if row else None
    except sqlite3.Error:
        return None


def _cleanup_temporary_database(path: Path) -> None:
    for candidate in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _write_reports(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    atomic_write_json(json_path, report)
    checks = report["validation"]["checks"]
    smoke_lines = "\n".join(
        f"- `{item['query']}`: {item['result_count']} result(s); top={item.get('top_segment_id')}"
        for item in report["smoke_tests"]
    )
    markdown = f"""# ASR Search Index Report

- Verdict: **{report['verdict']}**
- Database: `{report['database']}`
- Built at: `{report['built_at']}`
- Videos: {checks['videos_count']}
- ASR segments: {checks['asr_segments_count']}
- FTS rows: {checks['fts_count']}
- Orphans: {checks['orphan_segments']}
- Duplicate segment IDs: {checks['duplicate_segment_ids']}
- SQLite integrity: `{checks['integrity_check']}`

## Smoke queries

{smoke_lines}

## CLI examples

```powershell
python -m aic2026.search.asr "thành phố hồ chí minh"
python -m aic2026.search.asr "60 giây" --limit 20
python -m aic2026.search.asr '\"chào mừng quý vị\"' --video-id L21_V001
python -m aic2026.search.asr "bão lũ" --json
```
"""
    atomic_write_text(markdown_path, markdown)


def build_asr_search_index(
    database: str | Path,
    video_inventory: str | Path,
    asr_videos: str | Path,
    asr_segments: str | Path,
    schema_path: str | Path,
    *,
    expected_videos: int = DEFAULT_EXPECTED_VIDEOS,
    expected_segments: int = DEFAULT_EXPECTED_SEGMENTS,
    duration_tolerance_sec: float = 1.0,
    force: bool = False,
    report_json: str | Path | None = None,
    report_markdown: str | Path | None = None,
) -> dict[str, Any]:
    if duration_tolerance_sec < 0:
        raise AsrIndexBuildError("duration_tolerance_sec must be >= 0")
    target = Path(database)
    inputs = [Path(video_inventory), Path(asr_videos), Path(asr_segments)]
    for path in inputs:
        if not path.is_file():
            raise AsrIndexBuildError(f"Required input missing: {path}")
        if path.name.endswith(".partial.jsonl"):
            raise AsrIndexBuildError(f"Partial JSONL is forbidden: {path}")
    config = {
        "expected_videos": expected_videos,
        "expected_segments": expected_segments,
        "duration_tolerance_sec": duration_tolerance_sec,
        "tokenizer": "unicode61 remove_diacritics 2",
    }
    source_checksums, fingerprint = _source_fingerprint(inputs, config)
    if target.exists() and not force:
        if _current_fingerprint(target) == fingerprint:
            validation = validate_asr_search_db(
                target, expected_videos=expected_videos, expected_segments=expected_segments
            )
            if validation["valid"]:
                return {
                    "verdict": "PASS",
                    "status": "ALREADY_VALID",
                    "database": str(target),
                    "built_at": _utc_now(),
                    "input_checksums": source_checksums,
                    "input_fingerprint": fingerprint,
                    "validation": validation,
                    "smoke_tests": [],
                }
        raise AsrIndexBuildError("Database exists with different or invalid ASR index; use --force")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.building.{os.getpid()}.tmp")
    if temporary.exists():
        raise AsrIndexBuildError(f"Temporary build database already exists: {temporary}")
    backup_path: Path | None = None
    try:
        with closing(sqlite3.connect(temporary)) as output:
            output.execute("PRAGMA foreign_keys=ON")
            output.execute("PRAGMA journal_mode=DELETE")
            if target.is_file():
                with closing(sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)) as source:
                    source.backup(output)
            _ensure_base_schema(output, Path(schema_path))
            _create_asr_schema(output)
            video_count, durations = _ingest_videos(output, inputs[0], inputs[1])
            segment_count, actual_per_video = _ingest_segments(
                output,
                inputs[2],
                durations,
                duration_tolerance_sec=duration_tolerance_sec,
            )
            declared_per_video = {
                row["video_id"]: int(row["segment_count"])
                for _, row in _iter_jsonl(inputs[1])
            }
            mismatched = sorted(
                video_id for video_id, declared in declared_per_video.items()
                if actual_per_video[video_id] != declared
            )
            if mismatched:
                raise AsrIndexBuildError(f"Per-video segment_count mismatch: {mismatched[:10]}")
            if video_count != expected_videos or segment_count != expected_segments:
                raise AsrIndexBuildError(
                    f"Input count mismatch: videos={video_count}, segments={segment_count}"
                )
            output.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
                ("asr_search_input_fingerprint", fingerprint),
            )
            output.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
                ("asr_search_built_at", _utc_now()),
            )
            output.commit()
            output.execute("PRAGMA optimize")
            output.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            output.execute("PRAGMA journal_mode=DELETE")
        validation = validate_asr_search_db(
            temporary, expected_videos=expected_videos, expected_segments=expected_segments
        )
        if not validation["valid"]:
            raise AsrIndexBuildError(f"Built database failed validation: {validation['errors']}")
        smoke_tests: list[dict[str, Any]] = []
        for query in DEFAULT_SMOKE_QUERIES:
            rows = search_asr(temporary, query, limit=5)
            smoke_tests.append({
                "query": query,
                "result_count": len(rows),
                "top_segment_id": rows[0]["segment_id"] if rows else None,
            })
        if any(item["result_count"] == 0 for item in smoke_tests):
            raise AsrIndexBuildError(f"Smoke query returned no result: {smoke_tests}")
        if target.exists():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = target.with_name(f"{target.name}.backup-{timestamp}")
            if backup_path.exists():
                raise AsrIndexBuildError(f"Backup path already exists: {backup_path}")
            shutil.copy2(target, backup_path)
        os.replace(temporary, target)
        _cleanup_temporary_database(temporary)
        report = {
            "verdict": "PASS",
            "status": "BUILT",
            "database": str(target),
            "database_sha256": sha256_file(target),
            "backup_database": str(backup_path) if backup_path else None,
            "built_at": _utc_now(),
            "input_checksums": source_checksums,
            "input_fingerprint": fingerprint,
            "config": config,
            "validation": validation,
            "smoke_tests": smoke_tests,
        }
        if report_json is not None and report_markdown is not None:
            _write_reports(report, Path(report_json), Path(report_markdown))
        return report
    except Exception:
        _cleanup_temporary_database(temporary)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m aic2026.search.build_asr_index",
        description="Atomically build the canonical AIC 2026 ASR SQLite FTS5 index.",
    )
    parser.add_argument("--config", default="configs/local.toml")
    parser.add_argument("--database")
    parser.add_argument("--video-inventory")
    parser.add_argument("--asr-videos")
    parser.add_argument("--asr-segments")
    parser.add_argument("--expected-videos", type=int, default=DEFAULT_EXPECTED_VIDEOS)
    parser.add_argument("--expected-segments", type=int, default=DEFAULT_EXPECTED_SEGMENTS)
    parser.add_argument("--duration-tolerance-sec", type=float, default=1.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--report-json")
    parser.add_argument("--report-markdown")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        resolver = PathResolver.from_config(load_config(args.config))
        merged = resolver.artifact("asr/whisper-medium-vi-full-v1-colab-merged")
        report = build_asr_search_index(
            args.database or resolver.work("db/aic.sqlite"),
            args.video_inventory or resolver.work("audit/videos.jsonl"),
            args.asr_videos or merged / "asr_videos.jsonl",
            args.asr_segments or merged / "asr_segments.jsonl",
            Path(__file__).parents[1] / "db" / "schema.sql",
            expected_videos=args.expected_videos,
            expected_segments=args.expected_segments,
            duration_tolerance_sec=args.duration_tolerance_sec,
            force=args.force,
            report_json=args.report_json or resolver.work("validation/asr_search_index_report.json"),
            report_markdown=args.report_markdown or resolver.work("validation/asr_search_index_report.md"),
        )
    except (AsrIndexBuildError, AsrSearchError, OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
