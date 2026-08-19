"""OCR Trigram Index Builder and Runtime Index (M4C).

Provides character 3-gram typo-tolerant lexical retrieval over canonical raw OCR items.
Uses SQLite FTS5 with tokenize='trigram'.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

NORMALIZER_VERSION = "v1_nfc_trigram_accentless"
DEFAULT_BATCH_SIZE = 50000


def strip_accents(text: str) -> str:
    """Strip Vietnamese diacritics / accents from text while preserving base characters."""
    nfkd = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Handle Vietnamese special d/D
    stripped = stripped.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", stripped)


def clean_text_for_trigram(text: str) -> str:
    """Normalize whitespace and strip control characters for trigram indexing."""
    norm = unicodedata.normalize("NFC", text or "").strip()
    return re.sub(r"\s+", " ", norm)


@dataclass(frozen=True)
class OcrTrigramHit:
    ocr_uid: str
    video_id: str
    keyframe_uid: str
    frame_idx: int
    timestamp_ms: int
    raw_score: float
    rank: int
    score_kind: str = "bm25_lower_is_better"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize_trigram_query(query_text: str) -> str:
    """Sanitize query string for safe FTS5 trigram MATCH execution."""
    cleaned = unicodedata.normalize("NFC", query_text or "").strip()
    # Remove FTS5 special characters that could cause syntax errors
    cleaned = re.sub(r'["\'\*\^\:\(\)\{\}\[\]\+\-\~]', " ", cleaned)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return ""
    full_phrase = " ".join(tokens)
    valid_tokens = [t for t in tokens if len(t) >= 3]

    if len(tokens) > 1:
        if valid_tokens and len(valid_tokens) == len(tokens):
            tok_and = " AND ".join(f'"{t}"' for t in valid_tokens)
            return f'"{full_phrase}" OR ({tok_and})'
        elif valid_tokens:
            tok_and = " AND ".join(f'"{t}"' for t in valid_tokens)
            return f'"{full_phrase}" OR ({tok_and})'
        else:
            return f'"{full_phrase}"'
    else:
        if len(full_phrase) >= 3:
            return f'"{full_phrase}"'
        return ""



def build_ocr_trigram_index(
    canonical_db_path: Path | str,
    output_dir: Path | str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
) -> dict[str, Any]:
    """Build the standalone SQLite FTS5 trigram database from canonical ocr_items."""
    canonical_db_path = Path(canonical_db_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_out = output_dir / "ocr_trigram.sqlite"
    passport_file = output_dir / "ocr_trigram_passport.json"
    done_file = output_dir / "DONE.json"

    # Remove previous partial build if exists
    if db_out.exists():
        db_out.unlink()

    t0 = time.perf_counter()

    # Read from canonical SQLite
    src_conn = sqlite3.connect(f"file:{canonical_db_path}?mode=ro", uri=True)
    src_cur = src_conn.cursor()

    query = """
    SELECT ocr_uid, video_id, keyframe_uid, frame_idx, timestamp_ms, text_raw, text_norm
    FROM ocr_items
    ORDER BY ocr_uid ASC
    """
    if limit is not None:
        query += f" LIMIT {limit}"

    src_cur.execute(query)

    # Setup target DB with WAL and synchronous=OFF for fast ingestion
    tgt_conn = sqlite3.connect(str(db_out))
    tgt_cur = tgt_conn.cursor()
    tgt_cur.execute("PRAGMA journal_mode=WAL")
    tgt_cur.execute("PRAGMA synchronous=OFF")
    tgt_cur.execute("PRAGMA temp_store=MEMORY")

    tgt_cur.execute("""
    CREATE TABLE ocr_trigram_meta (
        row_id INTEGER PRIMARY KEY,
        ocr_uid TEXT UNIQUE NOT NULL,
        video_id TEXT NOT NULL,
        keyframe_uid TEXT NOT NULL,
        frame_idx INTEGER NOT NULL,
        timestamp_ms INTEGER NOT NULL
    )
    """)
    tgt_cur.execute("CREATE INDEX idx_ocr_trigram_meta_video ON ocr_trigram_meta(video_id)")

    tgt_cur.execute("""
    CREATE VIRTUAL TABLE ocr_trigram_fts USING fts5(
        ocr_uid UNINDEXED,
        text_clean,
        text_accentless,
        tokenize = 'trigram'
    )
    """)

    total_rows = 0
    batch_meta: list[tuple[int, str, str, str, int, int]] = []
    batch_fts: list[tuple[str, str, str]] = []

    while True:
        rows = src_cur.fetchmany(batch_size)
        if not rows:
            break

        for r in rows:
            ocr_uid, video_id, keyframe_uid, frame_idx, timestamp_ms, text_raw, text_norm = r
            raw_clean = clean_text_for_trigram(text_raw or text_norm or "")
            accentless = strip_accents(raw_clean)

            total_rows += 1
            batch_meta.append((total_rows, ocr_uid, video_id, keyframe_uid, int(frame_idx or 0), int(timestamp_ms or 0)))
            batch_fts.append((ocr_uid, raw_clean, accentless))

        tgt_cur.executemany(
            "INSERT INTO ocr_trigram_meta (row_id, ocr_uid, video_id, keyframe_uid, frame_idx, timestamp_ms) VALUES (?, ?, ?, ?, ?, ?)",
            batch_meta,
        )
        tgt_cur.executemany(
            "INSERT INTO ocr_trigram_fts (ocr_uid, text_clean, text_accentless) VALUES (?, ?, ?)",
            batch_fts,
        )
        batch_meta.clear()
        batch_fts.clear()
        tgt_conn.commit()

    src_conn.close()

    # Optimize FTS index
    tgt_cur.execute("INSERT INTO ocr_trigram_fts(ocr_trigram_fts) VALUES('optimize')")
    tgt_conn.commit()
    tgt_conn.close()

    elapsed = time.perf_counter() - t0

    # Compute checksum of the resulting sqlite file
    hasher = hashlib.sha256()
    with open(db_out, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    db_sha256 = hasher.hexdigest()
    db_size = db_out.stat().st_size

    passport_data = {
        "index_id": "ocr_trigram_v1",
        "lane_id": "ocr_trigram",
        "artifact_type": "SQLITE_FTS5_TRIGRAM",
        "tokenizer": "trigram",
        "normalizer_version": NORMALIZER_VERSION,
        "indexed_rows": total_rows,
        "sqlite_version": sqlite3.sqlite_version,
        "db_sha256": db_sha256,
        "db_bytes": db_size,
        "build_duration_sec": round(elapsed, 2),
        "source_canonical_db": str(canonical_db_path),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(passport_file, "w", encoding="utf-8") as f:
        json.dump(passport_data, f, indent=2)

    with open(done_file, "w", encoding="utf-8") as f:
        json.dump({"status": "SUCCESS", "indexed_rows": total_rows, "db_sha256": db_sha256, "elapsed_sec": round(elapsed, 2)}, f, indent=2)

    logger.info("OCR Trigram index build complete: %d rows in %.2fs (SHA: %s)", total_rows, elapsed, db_sha256[:12])
    return passport_data


class OcrTrigramIndex:
    """Thread-safe runtime reader for derived OCR FTS5 trigram index."""

    def __init__(self, artifact_dir: Path | str) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.db_path = self.artifact_dir / "ocr_trigram.sqlite"
        self.passport_path = self.artifact_dir / "ocr_trigram_passport.json"
        self.passport: dict[str, Any] = {}

        if self.passport_path.exists():
            with open(self.passport_path, "r", encoding="utf-8") as f:
                self.passport = json.load(f)

    def health(self) -> dict[str, Any]:
        """Check if database is reachable and trigram FTS5 is valid."""
        if not self.db_path.exists():
            return {
                "lane_id": "ocr_trigram",
                "status": "UNAVAILABLE",
                "sqlite_reachable": False,
                "error": f"OCR Trigram DB not found at {self.db_path}",
            }

        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM ocr_trigram_fts")
            fts_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM ocr_trigram_meta")
            meta_count = cur.fetchone()[0]
            conn.close()

            return {
                "lane_id": "ocr_trigram",
                "status": "OK",
                "sqlite_reachable": True,
                "sqlite_version": sqlite3.sqlite_version,
                "fts5_trigram_available": True,
                "indexed_rows": fts_count,
                "meta_rows": meta_count,
                "db_bytes": self.db_path.stat().st_size,
                "db_sha256": self.passport.get("db_sha256"),
                "normalizer_version": self.passport.get("normalizer_version", NORMALIZER_VERSION),
                "tokenizer": "trigram",
                "error": None,
            }
        except Exception as exc:
            return {
                "lane_id": "ocr_trigram",
                "status": "ERROR",
                "sqlite_reachable": False,
                "error": str(exc),
            }

    def search(
        self,
        query_text: str,
        top_k: int = 20,
        video_ids: Sequence[str] = (),
    ) -> list[OcrTrigramHit]:
        """Search canonical OCR items using FTS5 trigram lexical matching.
        
        Searches both clean and accentless fields.
        """
        if not query_text or not query_text.strip():
            return []

        match_clean = sanitize_trigram_query(query_text)
        match_accentless = sanitize_trigram_query(strip_accents(query_text))

        if not match_clean and not match_accentless:
            return []

        # If both are valid and distinct, query across both columns or use OR
        if match_clean == match_accentless:
            match_expr = f'text_clean : {match_clean} OR text_accentless : {match_clean}'
        else:
            match_expr = f'text_clean : {match_clean} OR text_accentless : {match_accentless}'

        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        cur = conn.cursor()

        try:
            if video_ids:
                placeholders = ",".join("?" for _ in video_ids)
                sql = f"""
                SELECT
                    f.ocr_uid,
                    m.video_id,
                    m.keyframe_uid,
                    m.frame_idx,
                    m.timestamp_ms,
                    bm25(ocr_trigram_fts) as score
                FROM ocr_trigram_fts f
                JOIN ocr_trigram_meta m ON f.ocr_uid = m.ocr_uid
                WHERE ocr_trigram_fts MATCH ? AND m.video_id IN ({placeholders})
                ORDER BY score ASC
                LIMIT ?
                """
                params = [match_expr, *video_ids, top_k]
            else:
                sql = """
                SELECT
                    f.ocr_uid,
                    m.video_id,
                    m.keyframe_uid,
                    m.frame_idx,
                    m.timestamp_ms,
                    bm25(ocr_trigram_fts) as score
                FROM ocr_trigram_fts f
                JOIN ocr_trigram_meta m ON f.ocr_uid = m.ocr_uid
                WHERE ocr_trigram_fts MATCH ?
                ORDER BY score ASC
                LIMIT ?
                """
                params = [match_expr, top_k]

            cur.execute(sql, params)
            rows = cur.fetchall()

            hits = []
            for rank, r in enumerate(rows, start=1):
                ocr_uid, video_id, keyframe_uid, frame_idx, timestamp_ms, score = r
                hits.append(
                    OcrTrigramHit(
                        ocr_uid=ocr_uid,
                        video_id=video_id,
                        keyframe_uid=keyframe_uid,
                        frame_idx=frame_idx,
                        timestamp_ms=timestamp_ms,
                        raw_score=round(float(score), 4),
                        rank=rank,
                        score_kind="bm25_lower_is_better",
                    )
                )
            return hits
        finally:
            conn.close()
