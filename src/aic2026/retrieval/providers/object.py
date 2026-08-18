from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from aic2026.core.hashing import sha256_file
from aic2026.retrieval.contract import compile_relaxed_fts_query
from aic2026.retrieval.providers.base import ProviderCapability, ProviderHit, ProviderUnavailableError, ProviderQuery


_ALIASES = {
    "ô tô": "car", "xe hơi": "car", "xe máy": "motorcycle", "người": "person",
    "chó": "dog", "mèo": "cat", "xe đạp": "bicycle", "đèn giao thông": "traffic light",
}


class ObjectProvider:
    """Lane Object đọc SQLite đã lập chỉ mục; chỉ cung cấp soft evidence."""

    name = "object"

    def __init__(self, database: str | Path, *, artifact_version: str = "objects-partial-v1") -> None:
        self.database = Path(database)
        self.artifact_version = artifact_version
        self._lock = threading.RLock()
        self._capability: ProviderCapability | None = None

    @staticmethod
    def _canonical_query(value: str) -> str:
        normalized = value.casefold()
        for source, target in _ALIASES.items():
            normalized = normalized.replace(source, target)
        return normalized

    def capabilities(self) -> ProviderCapability:
        with self._lock:
            if self._capability is not None:
                return self._capability
            if not self.database.is_file():
                self._capability = ProviderCapability(self.name, "UNAVAILABLE", "OBJECT_DATABASE_MISSING", None, {}, {}, {})
                return self._capability
            try:
                uri = f"file:{self.database.as_posix()}?mode=ro"
                with closing(sqlite3.connect(uri, uri=True)) as connection:
                    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not {"object_observations", "object_labels_fts"} <= tables:
                        self._capability = ProviderCapability(self.name, "UNAVAILABLE", "OBJECT_ARTIFACT_NOT_AVAILABLE", None, {}, {}, {})
                        return self._capability
                    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                    observations = int(connection.execute("SELECT COUNT(*) FROM object_observations").fetchone()[0])
                    fts_rows = int(connection.execute("SELECT COUNT(*) FROM object_labels_fts").fetchone()[0])
                    covered = int(connection.execute("SELECT COUNT(DISTINCT video_id) FROM object_observations").fetchone()[0])
                    corpus = int(connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0])
                if integrity != "ok" or observations != fts_rows:
                    self._capability = ProviderCapability(self.name, "INTEGRITY_ERROR", "OBJECT_DATABASE_INTEGRITY_MISMATCH", self.artifact_version, {}, {}, {})
                else:
                    self._capability = ProviderCapability(
                        self.name, "OK", None, self.artifact_version,
                        {"database_sha256": sha256_file(self.database)},
                        {"read_only": True, "match_policy": "soft_evidence_v1", "query_strategy": "object_lexical_v1"},
                        {"observations": observations, "fts_rows": fts_rows, "coverage_videos": covered, "corpus_videos": corpus},
                    )
            except (sqlite3.Error, OSError) as exc:
                self._capability = ProviderCapability(self.name, "INTEGRITY_ERROR", str(exc), self.artifact_version, {}, {"read_only": True}, {})
            return self._capability

    def search(self, query: ProviderQuery) -> list[ProviderHit]:
        capability = self.capabilities()
        if capability.status != "OK":
            raise ProviderUnavailableError(capability.reason or capability.status)
        compiled = compile_relaxed_fts_query(self._canonical_query(query.query_text))
        allowed = tuple(query.video_ids)
        where = "object_labels_fts MATCH ?"
        params: list[object] = [compiled]
        if allowed:
            where += f" AND o.video_id IN ({','.join('?' for _ in allowed)})"
            params.extend(allowed)
        params.append(query.top_k)
        sql = f"""
            SELECT o.observation_id, o.video_id, o.csv_n, o.frame_idx, o.pts_time,
                   o.label, o.confidence, o.bbox_json, o.source_relpath,
                   bm25(object_labels_fts) AS score
            FROM object_labels_fts
            JOIN object_observations o ON o.rowid = object_labels_fts.rowid
            WHERE {where}
            ORDER BY score ASC, o.video_id ASC, o.pts_time ASC, o.observation_id ASC
            LIMIT ?
        """
        uri = f"file:{self.database.as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            rows = connection.execute(sql, params).fetchall()
        hits: list[ProviderHit] = []
        for rank, row in enumerate(rows, start=1):
            observation_id, video_id, csv_n, frame_idx, pts_time, label, confidence, bbox_json, source_relpath, score = row
            hits.append(ProviderHit(
                provider=self.name, evidence_id=str(observation_id), video_id=str(video_id), rank=rank,
                start_sec=float(pts_time), end_sec=float(pts_time), anchor_sec=float(pts_time),
                raw_score=float(score), score_kind="bm25_lower_is_better", artifact_version=self.artifact_version,
                source_video_relpath=None,
                payload={"observation_id": str(observation_id), "label": str(label), "confidence": float(confidence),
                         "bbox": bbox_json, "csv_n": int(csv_n), "frame_idx": int(frame_idx), "pts_time": float(pts_time),
                         "source_relpath": str(source_relpath), "object_match": "soft"},
                provenance={"database_sha256": capability.checksums["database_sha256"], "match_policy": "soft_evidence_v1"},
            ))
        return hits
