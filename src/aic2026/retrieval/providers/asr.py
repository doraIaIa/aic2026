from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from aic2026.core.hashing import sha256_file
from aic2026.core.paths import PathContractError, normalize_relpath
from aic2026.retrieval.contract import ASR_STRATEGIES, DEFAULT_ASR_STRATEGY, compile_fts_query
from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)
from aic2026.search.asr import AsrSearchError, search_asr


class AsrProvider:
    """Adapter read-only cho production SQLite FTS5; không dùng pilot ASR FTS."""

    name = "asr"

    def __init__(self, database: str | Path, *, artifact_version: str = "asr-fts5-full-v1", strategy: str = DEFAULT_ASR_STRATEGY) -> None:
        self.database = Path(database)
        self.artifact_version = artifact_version
        if strategy not in ASR_STRATEGIES:
            raise ValueError(f"ASR strategy không hợp lệ: {strategy}")
        self.strategy = strategy
        self._lock = threading.RLock()
        self._capability: ProviderCapability | None = None

    def capabilities(self) -> ProviderCapability:
        with self._lock:
            if self._capability is not None:
                return self._capability
            if not self.database.is_file():
                self._capability = ProviderCapability(self.name, "UNAVAILABLE", "ASR_DATABASE_MISSING", None, {}, {}, {})
                return self._capability
            try:
                uri = f"file:{self.database.as_posix()}?mode=ro"
                with closing(sqlite3.connect(uri, uri=True)) as connection:
                    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                    segments = int(connection.execute("SELECT COUNT(*) FROM asr_segments").fetchone()[0])
                    fts_rows = int(connection.execute("SELECT COUNT(*) FROM asr_segments_fts").fetchone()[0])
                    videos = int(connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0])
                    models = [row[0] for row in connection.execute("SELECT DISTINCT model FROM asr_segments ORDER BY model")]
                    languages = [row[0] for row in connection.execute("SELECT DISTINCT language FROM asr_segments ORDER BY language")]
                if integrity != "ok" or segments != fts_rows:
                    raise ProviderIntegrityError("ASR_DATABASE_INTEGRITY_MISMATCH")
                self._capability = ProviderCapability(
                    self.name, "OK", None, self.artifact_version,
                    {"database_sha256": sha256_file(self.database)},
                    {"models": models, "languages": languages, "read_only": True, "search_authority": "aic2026.search.asr"},
                    {"videos": videos, "segments": segments, "fts_rows": fts_rows},
                )
            except (sqlite3.Error, OSError, ProviderIntegrityError) as exc:
                self._capability = ProviderCapability(self.name, "INTEGRITY_ERROR", str(exc), self.artifact_version, {}, {"read_only": True}, {})
            return self._capability

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        capability = self.capabilities()
        if capability.status != "OK":
            raise ProviderUnavailableError(capability.reason or capability.status)
        compiled = compile_fts_query(query.query_text, strategy=self.strategy)
        try:
            rows = search_asr(self.database, compiled, limit=query.top_k, video_ids=query.video_ids)
        except AsrSearchError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        hits: list[ProviderHit] = []
        for row in rows:
            try:
                relpath = normalize_relpath(row["source_video_path"])
            except PathContractError as exc:
                raise ProviderIntegrityError(f"ASR_SOURCE_PATH_INVALID: {exc}") from exc
            start = float(row["start_sec"])
            end = float(row["end_sec"])
            hits.append(ProviderHit(
                provider=self.name, evidence_id=str(row["segment_id"]), video_id=str(row["video_id"]),
                rank=int(row["rank"]), start_sec=start, end_sec=end, anchor_sec=(start + end) / 2,
                raw_score=float(row["score"]), score_kind="bm25_lower_is_better",
                artifact_version=self.artifact_version, source_video_relpath=relpath,
                payload={"segment_id": row["segment_id"], "text": row["text"], "language": row.get("language"), "model": row.get("model"), "asr_strategy": self.strategy},
                provenance={"database_sha256": capability.checksums["database_sha256"], "query_policy": "retrieval-policy-v1", "asr_strategy": self.strategy},
            ))
        return hits
