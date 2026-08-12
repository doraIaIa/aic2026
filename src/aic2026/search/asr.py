from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

from aic2026.core.config import load_config
from aic2026.core.paths import PathResolver


class AsrSearchError(RuntimeError):
    """ASR search database or query is invalid."""


def _resolve_db(config_path: str | Path, database: str | Path | None) -> Path:
    if database is not None:
        return Path(database)
    return PathResolver.from_config(load_config(config_path)).work("db/aic.sqlite")


def search_asr(
    database: str | Path,
    query: str,
    *,
    limit: int = 20,
    video_id: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(query, str) or not query.strip():
        raise AsrSearchError("Query must be a non-empty string")
    if limit <= 0 or limit > 100:
        raise AsrSearchError("limit must be between 1 and 100")
    db_path = Path(database)
    if not db_path.is_file():
        raise AsrSearchError(f"Database not found: {db_path}")

    sql = """
        SELECT
            s.segment_id,
            s.video_id,
            s.start_sec,
            s.end_sec,
            snippet(asr_segments_fts, 0, '[', ']', ' … ', 24) AS text_snippet,
            v.relpath AS source_video_path,
            bm25(asr_segments_fts) AS score
        FROM asr_segments_fts
        JOIN asr_segments AS s ON s.rowid = asr_segments_fts.rowid
        JOIN videos AS v ON v.video_id = s.video_id
        WHERE asr_segments_fts MATCH ?
    """
    parameters: list[Any] = [query.strip()]
    if video_id is not None:
        sql += " AND s.video_id = ?"
        parameters.append(video_id)
    sql += " ORDER BY score ASC, s.segment_id ASC LIMIT ?"
    parameters.append(limit)
    try:
        with closing(sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, parameters).fetchall()
    except sqlite3.Error as exc:
        raise AsrSearchError(f"FTS query failed: {exc}") from exc
    return [
        {
            "rank": rank,
            "video_id": row["video_id"],
            "start_sec": row["start_sec"],
            "end_sec": row["end_sec"],
            "text": row["text_snippet"],
            "segment_id": row["segment_id"],
            "source_video_path": row["source_video_path"],
            "score": row["score"],
        }
        for rank, row in enumerate(rows, start=1)
    ]


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No ASR results.")
        return
    for row in rows:
        print(
            f"{row['rank']:>3}. {row['video_id']} "
            f"[{row['start_sec']:.2f}-{row['end_sec']:.2f}] "
            f"score={row['score']:.6f} {row['segment_id']}"
        )
        print(f"     {row['text']}")
        print(f"     {row['source_video_path']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m aic2026.search.asr",
        description="Search canonical AIC 2026 ASR segments with SQLite FTS5.",
    )
    parser.add_argument("query", help="FTS5 query; quoted phrases are supported")
    parser.add_argument("--limit", type=int, default=20, help="number of results, 1..100")
    parser.add_argument("--video-id", help="restrict results to one canonical video_id")
    parser.add_argument("--json", action="store_true", help="emit UTF-8 JSON")
    parser.add_argument("--config", default="configs/local.toml")
    parser.add_argument("--database", help="override database path")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        rows = search_asr(
            _resolve_db(args.config, args.database),
            args.query,
            limit=args.limit,
            video_id=args.video_id,
        )
    except (AsrSearchError, OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
