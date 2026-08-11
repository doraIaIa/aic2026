from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aic2026.asr.manifest import AsrContractError
from aic2026.asr.whisper_runner import _git_state, write_checksum_file
from aic2026.core.atomic import atomic_write_json
from aic2026.core.hashing import sha256_bytes, sha256_file


def _read_segments(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AsrContractError(f"Segments JSONL lỗi tại dòng {line_number}") from exc
            segment_id = row.get("segment_id")
            video_id = row.get("video_id")
            text = row.get("text")
            start = row.get("start_sec")
            end = row.get("end_sec")
            if (
                not isinstance(segment_id, str) or not segment_id or segment_id in seen
                or not isinstance(video_id, str) or not video_id
                or not isinstance(text, str) or not text.strip()
                or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or start < 0 or end < start
            ):
                raise AsrContractError(f"Segment malformed/trùng tại dòng {line_number}")
            seen.add(segment_id)
            rows.append(row)
    return rows


def build_asr_fts(segments_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    source = Path(segments_path)
    root = Path(output_path)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise AsrContractError("ASR FTS artifact đã tồn tại; dùng artifact version mới")
    rows = _read_segments(source)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "asr_fts.sqlite"
    temporary = target.with_name(target.name + ".tmp")
    if temporary.exists():
        raise AsrContractError("ASR FTS temporary file đã tồn tại; kiểm tra run trước")
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(
                """
                PRAGMA journal_mode=DELETE;
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE VIRTUAL TABLE asr_segments USING fts5(
                    segment_id UNINDEXED,
                    video_id UNINDEXED,
                    start_sec UNINDEXED,
                    end_sec UNINDEXED,
                    source_video_path UNINDEXED,
                    text,
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )
            connection.executemany(
                "INSERT INTO asr_segments(segment_id, video_id, start_sec, end_sec, source_video_path, text) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(
                    row["segment_id"], row["video_id"], float(row["start_sec"]), float(row["end_sec"]),
                    row.get("source_video_path"), row["text"],
                ) for row in rows],
            )
            metadata = {
                "schema_version": "1",
                "task": "asr_fts5",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_segments_file": source.name,
                "source_segments_sha256": sha256_file(source),
                "segment_count": str(len(rows)),
            }
            connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise AsrContractError(f"SQLite integrity_check thất bại: {result}")
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    config = {"engine": "sqlite-fts5", "tokenize": "unicode61 remove_diacritics 2"}
    config_hash = sha256_bytes(json.dumps(config, sort_keys=True).encode("utf-8"))
    checksums, checksum_hash = write_checksum_file(root, [target.name])
    git_commit, git_dirty = _git_state()
    marker = {
        "schema_version": 1,
        "task": "asr_fts5",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "config_hash": config_hash,
        "input_manifest_sha256": sha256_file(source),
        "expected_items": len(rows),
        "processed_items": len(rows),
        "failed_items": 0,
        "index_file": target.name,
        "index_sha256": sha256_file(target),
        "output_checksums": checksums,
        "checksum_file": "checksum.sha256",
        "checksum_sha256": checksum_hash,
        "source_segments_sha256": sha256_file(source),
        "segment_count": len(rows),
    }
    atomic_write_json(root / "DONE.json", marker)
    return marker


def _resolve_valid_index(index_path: str | Path) -> Path:
    source = Path(index_path)
    if source.is_file():
        return source
    try:
        marker = json.loads((source / "DONE.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AsrContractError(f"ASR FTS DONE.json không đọc được: {exc}") from exc
    if marker.get("schema_version") != 1 or marker.get("task") != "asr_fts5":
        raise AsrContractError("ASR FTS DONE.json sai schema/task")
    target = source / str(marker.get("index_file", ""))
    if not target.is_file() or sha256_file(target) != marker.get("index_sha256"):
        raise AsrContractError("ASR FTS index thiếu hoặc checksum không khớp")
    return target


def _literal_match_query(query: str) -> str:
    tokens = re.findall(r"[\w]+", query, flags=re.UNICODE)
    if not tokens:
        raise AsrContractError("ASR search query không có token hợp lệ")
    return " OR ".join(f'"{token}"' for token in tokens)


def search_asr(index_path: str | Path, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
    if top_k <= 0 or top_k > 100:
        raise AsrContractError("top_k phải nằm trong 1..100")
    match_query = _literal_match_query(query)
    resolved_index = _resolve_valid_index(index_path)
    try:
        with sqlite3.connect(f"file:{resolved_index.as_posix()}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT segment_id, video_id, start_sec, end_sec, source_video_path, text, bm25(asr_segments) "
                "FROM asr_segments WHERE asr_segments MATCH ? ORDER BY bm25(asr_segments), segment_id LIMIT ?",
                (match_query, top_k),
            ).fetchall()
    except sqlite3.Error as exc:
        raise AsrContractError(f"Không query được ASR FTS index: {exc}") from exc
    return [
        {
            "rank": rank,
            "segment_id": row[0],
            "video_id": row[1],
            "start_sec": row[2],
            "end_sec": row[3],
            "source_video_path": row[4],
            "text": row[5],
            "bm25": row[6],
        }
        for rank, row in enumerate(rows, start=1)
    ]
