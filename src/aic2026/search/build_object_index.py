from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any


class ObjectIndexError(RuntimeError):
    pass


def _mapping(path: Path) -> dict[int, dict[str, float | int]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result: dict[int, dict[str, float | int]] = {}
    for row in rows:
        n = int(row["n"])
        if n < 1 or n in result:
            raise ObjectIndexError(f"CSV mapping không hợp lệ: {path}")
        result[n] = {"frame_idx": int(row["frame_idx"]), "pts_time": float(row["pts_time"])}
    return result


def _observations(path: Path, *, video_id: str, mapping: dict[int, dict[str, float | int]], data_root: Path) -> tuple[list[tuple[Any, ...]], int]:
    try:
        ordinal = int(path.stem)
        raw = json.loads(path.read_text(encoding="utf-8"))
        labels = raw["detection_class_entities"]
        scores = raw["detection_scores"]
        boxes = raw["detection_boxes"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ObjectIndexError(f"Object JSON malformed: {path}: {exc}") from exc
    if ordinal not in mapping or len(labels) != len(scores) or len(labels) != len(boxes):
        raise ObjectIndexError(f"Object mapping/cardinality invalid: {path}")
    keyframe = data_root / "data_extracted" / "keyframes" / video_id / f"{ordinal:03d}.jpg"
    if not keyframe.is_file():
        raise ObjectIndexError(f"Object anchor keyframe missing: {path}")
    anchor = mapping[ordinal]
    relpath = path.relative_to(data_root).as_posix()
    output: list[tuple[Any, ...]] = []
    for index, (label, score, bbox) in enumerate(zip(labels, scores, boxes)):
        if not isinstance(label, str) or not label.strip() or len(bbox) != 4:
            raise ObjectIndexError(f"Object detection malformed: {path}:{index}")
        confidence = float(score)
        if not 0 <= confidence <= 1:
            raise ObjectIndexError(f"Object confidence invalid: {path}:{index}")
        if confidence >= 0.20:
            output.append((f"{video_id}:{ordinal}:{index}", video_id, ordinal, int(anchor["frame_idx"]), float(anchor["pts_time"]), label.strip(), confidence, json.dumps(bbox, separators=(",", ":")), relpath))
    return output, len(labels)


def _write_progress(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    temporary.write_text(content, encoding="utf-8")
    for _ in range(10):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            time.sleep(0.2)
    # Progress is diagnostic only: không để lock tạm thời của Windows dừng indexing.
    try:
        path.write_text(content, encoding="utf-8")
    finally:
        temporary.unlink(missing_ok=True)


def _create_schema(connection: sqlite3.Connection, *, force: bool) -> None:
    if force:
        connection.executescript("""
            DROP TRIGGER IF EXISTS object_observations_ai;
            DROP TABLE IF EXISTS object_labels_fts;
            DROP TABLE IF EXISTS object_index_files;
            DROP TABLE IF EXISTS object_index_state;
            DROP TABLE IF EXISTS object_observations;
        """)
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS object_observations(
            observation_id TEXT PRIMARY KEY, video_id TEXT NOT NULL, csv_n INTEGER NOT NULL,
            frame_idx INTEGER NOT NULL, pts_time REAL NOT NULL, label TEXT NOT NULL,
            confidence REAL NOT NULL, bbox_json TEXT NOT NULL, source_relpath TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS object_observations_video_time ON object_observations(video_id, pts_time);
        CREATE VIRTUAL TABLE IF NOT EXISTS object_labels_fts USING fts5(label, content='object_observations', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');
        CREATE TRIGGER IF NOT EXISTS object_observations_ai AFTER INSERT ON object_observations BEGIN INSERT INTO object_labels_fts(rowid,label) VALUES(new.rowid,new.label); END;
        CREATE TABLE IF NOT EXISTS object_index_files(
            source_relpath TEXT PRIMARY KEY, video_id TEXT NOT NULL, status TEXT NOT NULL,
            raw_detections INTEGER NOT NULL, indexed_observations INTEGER NOT NULL, error TEXT
        );
        CREATE TABLE IF NOT EXISTS object_index_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)


def _state(connection: sqlite3.Connection, key: str) -> str | None:
    try:
        row = connection.execute("SELECT value FROM object_index_state WHERE key=?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return str(row[0]) if row else None


def _set_state(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute("INSERT INTO object_index_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def _summary(connection: sqlite3.Connection) -> dict[str, int | str]:
    totals = connection.execute("""
        SELECT COUNT(*), COALESCE(SUM(raw_detections),0), COALESCE(SUM(indexed_observations),0),
               COALESCE(SUM(status='MALFORMED'),0), COUNT(DISTINCT video_id)
        FROM object_index_files
    """).fetchone()
    return {
        "json_artifacts": int(totals[0]), "valid_detections": int(totals[1]),
        "indexed_observations": int(totals[2]), "malformed_files": int(totals[3]),
        "videos_with_artifacts": int(totals[4]),
        "fts_rows": int(connection.execute("SELECT COUNT(*) FROM object_labels_fts").fetchone()[0]),
        "distinct_labels": int(connection.execute("SELECT COUNT(DISTINCT label) FROM object_observations").fetchone()[0]),
        "corpus_videos": int(connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]),
    }


def build_object_index(
    database: str | Path, data_root: str | Path, *, backup: bool = True,
    progress_path: str | Path | None = None, force: bool = False, expected_files: int | None = None,
) -> dict[str, int | str]:
    database, data_root = Path(database), Path(data_root)
    objects_root = data_root / "data_extracted" / "objects"
    maps_root = data_root / "data_extracted" / "map-keyframes"
    if not database.is_file() or not objects_root.is_dir() or not maps_root.is_dir():
        raise ObjectIndexError("Thiếu database hoặc Object/keyframe mapping authority")
    if backup:
        backup_path = database.with_suffix(database.suffix + ".before-object-v1.bak")
        if not backup_path.exists():
            shutil.copy2(database, backup_path)
    progress = Path(progress_path) if progress_path else database.with_suffix(".object-index-progress.json")
    with sqlite3.connect(database) as progress_connection:
        previous_expected = _state(progress_connection, "expected_files")
        try:
            previous_processed = int(progress_connection.execute("SELECT COUNT(*) FROM object_index_files").fetchone()[0])
        except sqlite3.OperationalError:
            previous_processed = 0
    known_expected = int(previous_expected) if previous_expected and previous_expected.isdigit() else None
    expected_total = expected_files or known_expected
    if expected_total is None:
        # Dùng cho fixture/test hoặc run đầu tiên không có inventory; production nên truyền --expected-files.
        expected_total = sum(len(list(video_dir.glob("*.json"))) for video_dir in objects_root.iterdir() if video_dir.is_dir())
    if expected_total < 1:
        raise ObjectIndexError("Object source không có JSON hợp lệ")
    _write_progress(progress, {
        "task": "object_index", "version": "objects-partial-v1", "status": "RUNNING",
        "processed_files": previous_processed, "expected_files": expected_total,
        "percent": round(100 * previous_processed / expected_total, 3),
        "message": "Resume theo từng thư mục video; không quét recursive toàn bộ mounted source.",
    })
    started = time.monotonic()
    uri = f"file:{database.as_posix()}?mode=rwc"
    with sqlite3.connect(uri, uri=True) as connection:
        _create_schema(connection, force=force)
        if _state(connection, "expected_files") not in (None, str(expected_total)) and not force:
            raise ObjectIndexError("Object source manifest thay đổi; dùng --force để rebuild an toàn")
        _set_state(connection, "expected_files", str(expected_total))
        _set_state(connection, "status", "RUNNING")
        connection.commit()
        for video_dir in sorted(path for path in objects_root.iterdir() if path.is_dir()):
            video_id = video_dir.name
            mapping_path = maps_root / f"{video_id}.csv"
            mapping: dict[int, dict[str, float | int]] | None
            try:
                mapping = _mapping(mapping_path) if mapping_path.is_file() else None
            except ObjectIndexError:
                mapping = None
            for object_path in sorted(video_dir.glob("*.json")):
                relpath = object_path.relative_to(data_root).as_posix()
                if connection.execute("SELECT 1 FROM object_index_files WHERE source_relpath=?", (relpath,)).fetchone():
                    continue
                try:
                    if mapping is None:
                        raise ObjectIndexError(f"Object CSV mapping missing/invalid: {mapping_path}")
                    rows, raw_count = _observations(object_path, video_id=video_id, mapping=mapping, data_root=data_root)
                    connection.executemany("INSERT INTO object_observations VALUES(?,?,?,?,?,?,?,?,?)", rows)
                    connection.execute("INSERT INTO object_index_files VALUES(?,?,?,?,?,NULL)", (relpath, video_id, "OK", raw_count, len(rows)))
                except ObjectIndexError as exc:
                    connection.execute("INSERT INTO object_index_files VALUES(?,?,?,?,?,?)", (relpath, video_id, "MALFORMED", 0, 0, str(exc)))
            connection.commit()
            current = _summary(connection)
            processed = int(current["json_artifacts"])
            elapsed = time.monotonic() - started
            completed_this_run = processed - previous_processed
            rate = completed_this_run / elapsed if elapsed else 0.0
            _write_progress(progress, {"task": "object_index", "version": "objects-partial-v1", "status": "RUNNING", "current_video_id": video_id, "processed_files": processed, "expected_files": expected_total, "percent": round(100 * processed / expected_total, 3), "files_per_sec": round(rate, 3), "eta_sec": round((expected_total - processed) / rate, 1) if rate else None, "summary": current})
            print(f"[object-index] {processed}/{expected_total} ({100 * processed / expected_total:.2f}%) video={video_id}", flush=True)
        report = _summary(connection)
        if report["fts_rows"] != report["indexed_observations"]:
            raise ObjectIndexError("Object FTS count mismatch")
        _set_state(connection, "status", "DONE")
        connection.commit()
    report["videos_missing"] = int(report["corpus_videos"]) - int(report["videos_with_artifacts"])
    report["artifact_version"] = "objects-partial-v1"
    _write_progress(progress, {"task": "object_index", "version": "objects-partial-v1", "status": "DONE", "processed_files": int(report["json_artifacts"]), "expected_files": expected_total, "percent": 100.0, "summary": report})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build partial Object soft-evidence index from existing BTC artifacts.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--progress", help="JSON progress output; atomic update after mỗi video")
    parser.add_argument("--force", action="store_true", help="rebuild only Object tables; existing ASR tables không bị đụng")
    parser.add_argument("--expected-files", type=int, help="JSON Object count from local audit inventory; avoids recursive mounted-source scan")
    args = parser.parse_args(argv)
    print(json.dumps(build_object_index(args.database, args.data_root, progress_path=args.progress, force=args.force, expected_files=args.expected_files), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
