"""Qwen Structured Facet Retrieval Provider (M5A).

Provides deterministic, explainable FRAME retrieval in CUSTOM frame space
over 116,767 Qwen semantic observations.

Identity contract:
- entity_type = FRAME
- frame_space = CUSTOM
- provider = qwen_structured
- score_type = qwen_facet_support
- score_direction = HIGHER_IS_BETTER
"""
from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import time

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)
from aic2026.retrieval.qwen_structured_index import (
    CANONICAL_CUSTOM_FRAME_COUNT,
    CANONICAL_QWEN_ROW_COUNT,
    VALID_NAMESPACES,
    normalize_facet_phrase,
    to_accentless,
)

logger = logging.getLogger(__name__)

DEFAULT_INDEX_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\qwen_structured_v1\qwen_facets.sqlite")
MAX_TOP_K = 500


@dataclass
class MatchedFacetInfo:
    facet_ordinal: int
    facet_id: str
    namespace: str
    canonical_value: str
    raw_query_term: str
    df_frames: int
    idf: float
    namespace_weight: float
    contribution: float


@dataclass
class QwenStructuredQuery:
    query_text: str | None = None
    objects: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    counts: list[str] = field(default_factory=list)
    scenes: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    facets: list[dict[str, str]] = field(default_factory=list)
    candidate_video_ids: list[str] | None = None
    top_k: int = 50
    query_id: str | None = None


class QwenStructuredProvider:
    """Deterministic structured facet retrieval provider over Qwen observations."""

    name = "qwen_structured"

    def __init__(
        self,
        db_path: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_INDEX_PATH
        self._local = threading.local()
        self._total_frames = CANONICAL_CUSTOM_FRAME_COUNT

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            if not self.db_path.exists():
                raise ProviderUnavailableError(f"Qwen structured index not found at {self.db_path}")
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def close(self) -> None:
        """Close thread-local SQLite connection if open."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
            import gc
            gc.collect()



    def health(self) -> dict[str, Any]:
        """Check provider health and return corpus / namespace metrics."""
        try:
            conn = self._get_conn()
            c = conn.cursor()
            
            frame_cnt = c.execute("SELECT COUNT(*) FROM frame_registry").fetchone()[0]
            if frame_cnt != CANONICAL_CUSTOM_FRAME_COUNT:
                return {
                    "lane_id": self.name,
                    "status": "UNHEALTHY",
                    "error": f"Frame registry count {frame_cnt} != expected {CANONICAL_CUSTOM_FRAME_COUNT}",
                }
                
            facet_cnt = c.execute("SELECT COUNT(*) FROM facet_dictionary").fetchone()[0]
            postings_cnt = c.execute("SELECT COUNT(*) FROM frame_facets").fetchone()[0]
            
            # Count facets by namespace
            ns_counts = {}
            for r in c.execute("SELECT namespace, COUNT(*) FROM facet_dictionary GROUP BY namespace"):
                ns_counts[r[0]] = r[1]
                
            passport_path = self.db_path.parent / "qwen_structured_passport.json"
            passport = {}
            if passport_path.exists():
                try:
                    with open(passport_path, "r", encoding="utf-8") as f:
                        passport = json.load(f)
                except Exception:
                    pass
                    
            return {
                "lane_id": self.name,
                "status": "OK",
                "canonical_qwen_rows": CANONICAL_QWEN_ROW_COUNT,
                "custom_frame_rows": CANONICAL_CUSTOM_FRAME_COUNT,
                "frame_registry_rows": frame_cnt,
                "total_unique_facets": facet_cnt,
                "total_postings": postings_cnt,
                "facet_counts_by_namespace": ns_counts,
                "frames_with_zero_facets": passport.get("frames_with_zero_structured_facets", 180),
                "normalizer_version": passport.get("normalizer_version", "deterministic_text_v1"),
                "alias_policy": passport.get("alias_policy_version", "explicit_alias_v1"),
                "sqlite_checksum": passport.get("sqlite_checksum_sha256"),
                "entity_type": "FRAME",
                "frame_space": "CUSTOM",
                "score_type": "qwen_facet_support",
                "score_direction": "HIGHER_IS_BETTER",
            }
        except Exception as exc:
            logger.error("Health check failed for QwenStructuredProvider: %s", exc)
            return {
                "lane_id": self.name,
                "status": "UNAVAILABLE",
                "error": str(exc),
            }

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            lane_id=self.name,
            entity_type="FRAME",
            frame_space="CUSTOM",
            supports_candidate_scope=True,
            supports_scoring=True,
            score_type="qwen_facet_support",
            score_direction="HIGHER_IS_BETTER",
        )

    def _resolve_facets_from_explicit(
        self,
        conn: sqlite3.Connection,
        explicit_facets: list[tuple[str, str]],
    ) -> list[MatchedFacetInfo]:
        """Resolves explicit (namespace, value) pairs to facet records."""
        matched: list[MatchedFacetInfo] = []
        c = conn.cursor()
        
        for ns, raw_val in explicit_facets:
            if ns not in VALID_NAMESPACES or not raw_val:
                continue
            norm_val = normalize_facet_phrase(raw_val)
            if not norm_val:
                continue
                
            facet_id = f"{ns}/{norm_val}"
            row = c.execute(
                "SELECT facet_ordinal, canonical_value, df_frames FROM facet_dictionary WHERE facet_id = ?",
                (facet_id,),
            ).fetchone()
            
            if not row:
                # Try accentless or raw alias
                accentless_val = to_accentless(norm_val)
                row = c.execute(
                    """SELECT fd.facet_ordinal, fd.canonical_value, fd.df_frames
                       FROM facet_dictionary fd
                       JOIN facet_aliases fa ON fd.facet_ordinal = fa.facet_ordinal
                       WHERE fd.namespace = ? AND (fa.alias_value = ? OR fa.alias_value = ?)
                       LIMIT 1""",
                    (ns, raw_val, accentless_val),
                ).fetchone()
                
            if row:
                f_ord = row["facet_ordinal"]
                canon_val = row["canonical_value"]
                df_f = row["df_frames"]
                # IDF formula: log((N + 1) / (df + 1)) + 1.0
                idf = math.log((self._total_frames + 1.0) / (df_f + 1.0)) + 1.0
                ns_weight = 1.0
                contrib = ns_weight * idf
                matched.append(MatchedFacetInfo(
                    facet_ordinal=f_ord,
                    facet_id=facet_id,
                    namespace=ns,
                    canonical_value=canon_val,
                    raw_query_term=raw_val,
                    df_frames=df_f,
                    idf=round(idf, 4),
                    namespace_weight=ns_weight,
                    contribution=round(contrib, 4),
                ))
                
        return matched

    def _discover_facets_from_text(
        self,
        conn: sqlite3.Connection,
        query_text: str,
    ) -> list[MatchedFacetInfo]:
        """Discovers candidate facets from plain query text via facet_fts."""
        if not query_text or not query_text.strip():
            return []
            
        c = conn.cursor()
        norm_query = normalize_facet_phrase(query_text)
        accentless_query = to_accentless(norm_query)
        
        # 1. First attempt: exact match across dictionary
        exact_rows = c.execute(
            """SELECT facet_ordinal, facet_id, namespace, canonical_value, df_frames
               FROM facet_dictionary
               WHERE canonical_value = ? OR canonical_value = ?""",
            (norm_query, accentless_query),
        ).fetchall()
        
        matched_dict: dict[int, MatchedFacetInfo] = {}
        for r in exact_rows:
            f_ord = r["facet_ordinal"]
            df_f = r["df_frames"]
            idf = math.log((self._total_frames + 1.0) / (df_f + 1.0)) + 1.0
            contrib = 1.0 * idf
            matched_dict[f_ord] = MatchedFacetInfo(
                facet_ordinal=f_ord,
                facet_id=r["facet_id"],
                namespace=r["namespace"],
                canonical_value=r["canonical_value"],
                raw_query_term=query_text,
                df_frames=df_f,
                idf=round(idf, 4),
                namespace_weight=1.0,
                contribution=round(contrib, 4),
            )
            
        # 2. Second attempt: FTS lexical match on terms
        tokens = [t for t in re.findall(r"[\w\d]+", norm_query, flags=re.UNICODE) if len(t) > 1]
        if tokens:
            # Build phrase and token queries
            fts_query = f'"{ " ".join(tokens) }"'
            fts_rows = c.execute(
                """SELECT facet_ordinal, facet_id, namespace, term_norm
                   FROM facet_fts
                   WHERE facet_fts MATCH ?
                   LIMIT 25""",
                (fts_query,),
            ).fetchall()
            
            if not fts_rows:
                # Try individual tokens OR
                or_query = " OR ".join(f'"{t}"' for t in tokens)
                fts_rows = c.execute(
                    """SELECT facet_ordinal, facet_id, namespace, term_norm
                       FROM facet_fts
                       WHERE facet_fts MATCH ?
                       LIMIT 25""",
                    (or_query,),
                ).fetchall()
                
            for r in fts_rows:
                f_ord = r["facet_ordinal"]
                if f_ord in matched_dict:
                    continue
                dict_row = c.execute(
                    "SELECT canonical_value, df_frames FROM facet_dictionary WHERE facet_ordinal = ?",
                    (f_ord,),
                ).fetchone()
                if not dict_row:
                    continue
                df_f = dict_row["df_frames"]
                idf = math.log((self._total_frames + 1.0) / (df_f + 1.0)) + 1.0
                contrib = 1.0 * idf
                matched_dict[f_ord] = MatchedFacetInfo(
                    facet_ordinal=f_ord,
                    facet_id=r["facet_id"],
                    namespace=r["namespace"],
                    canonical_value=dict_row["canonical_value"],
                    raw_query_term=r["term_norm"],
                    df_frames=df_f,
                    idf=round(idf, 4),
                    namespace_weight=1.0,
                    contribution=round(contrib, 4),
                )
                
        return list(matched_dict.values())

    def search(
        self,
        query: ProviderQuery | QwenStructuredQuery | str,
        *,
        top_k: int = 50,
        candidate_video_ids: Sequence[str] | None = None,
        query_id: str | None = None,
        **kwargs: Any,
    ) -> list[ProviderHit]:
        """Execute structured facet search."""
        t_start = time.perf_counter()
        
        # 1. Parse query input
        explicit_facets: list[tuple[str, str]] = []
        plain_query: str | None = None
        scope_videos: list[str] | None = None
        target_top_k = min(top_k, MAX_TOP_K)
        
        if isinstance(query, str):
            plain_query = query
        elif isinstance(query, ProviderQuery):
            plain_query = query.query_text
            scope_videos = list(query.video_ids) if query.video_ids else None
            target_top_k = min(query.top_k or top_k, MAX_TOP_K)
        elif isinstance(query, QwenStructuredQuery):
            plain_query = query.query_text
            scope_videos = query.candidate_video_ids
            target_top_k = min(query.top_k or top_k, MAX_TOP_K)
            for item in query.objects:
                explicit_facets.append(("object", item))
            for item in query.attributes:
                explicit_facets.append(("attribute", item))
            for item in query.relations:
                explicit_facets.append(("relation", item))
            for item in query.counts:
                explicit_facets.append(("count", item))
            for item in query.scenes:
                explicit_facets.append(("scene", item))
            for item in query.actions:
                explicit_facets.append(("action", item))
            for f_dict in query.facets:
                ns = f_dict.get("namespace")
                val = f_dict.get("value")
                if ns and val:
                    explicit_facets.append((ns, val))

        # Check kwargs for explicit facets or scope
        for ns in VALID_NAMESPACES:
            plural = f"{ns}s" if not ns.endswith("s") else ns
            if ns in kwargs:
                vals = kwargs[ns]
                vals_list = vals if isinstance(vals, list) else [vals]
                for v in vals_list:
                    explicit_facets.append((ns, str(v)))
            elif plural in kwargs:
                vals = kwargs[plural]
                vals_list = vals if isinstance(vals, list) else [vals]
                for v in vals_list:
                    explicit_facets.append((ns, str(v)))

                    
        if candidate_video_ids:
            scope_videos = list(candidate_video_ids)
            
        # If candidate scope was provided as empty list -> return 0 hits
        if scope_videos is not None and len(scope_videos) == 0:
            return []
            
        conn = self._get_conn()
        
        # 2. Resolve or discover matched facets
        matched_facets: list[MatchedFacetInfo] = []
        if explicit_facets:
            matched_facets = self._resolve_facets_from_explicit(conn, explicit_facets)
        elif plain_query:
            matched_facets = self._discover_facets_from_text(conn, plain_query)
            
        if not matched_facets:
            return []
            
        facet_ord_map = {f.facet_ordinal: f for f in matched_facets}
        facet_ords = list(facet_ord_map.keys())
        
        # 3. Query frame postings
        placeholders = ",".join("?" for _ in facet_ords)
        params: list[Any] = list(facet_ords)
        
        sql = f"""
            SELECT ff.frame_ordinal, ff.facet_ordinal, ff.raw_value,
                   fr.keyframe_uid, fr.video_id, fr.frame_idx, fr.timestamp_ms, fr.caption, fr.semantic_status
            FROM frame_facets ff
            JOIN frame_registry fr ON ff.frame_ordinal = fr.frame_ordinal
            WHERE ff.facet_ordinal IN ({placeholders})
        """
        
        if scope_videos:
            v_placeholders = ",".join("?" for _ in scope_videos)
            sql += f" AND fr.video_id IN ({v_placeholders})"
            params.extend(scope_videos)
            
        c = conn.cursor()
        c.execute(sql, params)
        
        # Aggregate scores per frame
        # frame_ordinal -> {info, facets_matched: list, total_score: float}
        frame_accum: dict[int, dict[str, Any]] = {}
        
        for r in c:
            f_ord = r["frame_ordinal"]
            facet_ord = r["facet_ordinal"]
            raw_val = r["raw_value"]
            
            facet_info = facet_ord_map[facet_ord]
            
            if f_ord not in frame_accum:
                frame_accum[f_ord] = {
                    "keyframe_uid": r["keyframe_uid"],
                    "video_id": r["video_id"],
                    "frame_idx": r["frame_idx"],
                    "timestamp_ms": r["timestamp_ms"],
                    "caption": r["caption"],
                    "semantic_status": r["semantic_status"],
                    "total_score": 0.0,
                    "matched_facets": [],
                    "seen_facets": set(),
                }
                
            accum = frame_accum[f_ord]
            if facet_ord not in accum["seen_facets"]:
                accum["seen_facets"].add(facet_ord)
                accum["total_score"] += facet_info.contribution
                accum["matched_facets"].append({
                    "facet_id": facet_info.facet_id,
                    "namespace": facet_info.namespace,
                    "canonical_value": facet_info.canonical_value,
                    "raw_value": raw_val,
                    "idf": facet_info.idf,
                    "contribution": facet_info.contribution,
                })
                
        # 4. Rank frames: descending total_score, ascending frame_ordinal (deterministic tie break)
        sorted_frames = sorted(
            frame_accum.values(),
            key=lambda x: (-x["total_score"], x["keyframe_uid"]),
        )[:target_top_k]
        
        # 5. Build ProviderHits
        hits: list[ProviderHit] = []
        for rank, item in enumerate(sorted_frames, start=1):
            ts_sec = round(item["timestamp_ms"] / 1000.0, 3)
            matched_ns = list(set(mf["namespace"] for mf in item["matched_facets"]))
            
            hit = ProviderHit(
                provider=self.name,
                evidence_id=f"QWEN:CUSTOM:{item['keyframe_uid']}",
                video_id=item["video_id"],
                rank=rank,
                start_sec=ts_sec,
                end_sec=ts_sec,
                anchor_sec=ts_sec,
                raw_score=round(item["total_score"], 4),
                score_kind="higher_is_better",
                artifact_version="qwen_structured_v1",
                source_video_relpath=None,
                payload={
                    "entity_type": "FRAME",
                    "frame_space": "CUSTOM",
                    "lane": self.name,
                    "keyframe_uid": item["keyframe_uid"],
                    "frame_idx": item["frame_idx"],
                    "timestamp_ms": item["timestamp_ms"],
                    "caption": item["caption"],
                    "semantic_status": item["semantic_status"],
                    "matched_facets": item["matched_facets"],
                    "matched_namespaces": matched_ns,
                    "score_breakdown": {
                        "facet_contributions": item["matched_facets"],
                        "total_score": round(item["total_score"], 4),
                    },
                    "score_type": "qwen_facet_support",
                    "score_direction": "HIGHER_IS_BETTER",
                    "limitations": "visible_actions are frame observations, not temporal intervals. No source confidence claimed.",
                },
                provenance={
                    "lane": self.name,
                    "score_formula": "sum_idf_v1",
                    "normalizer_version": "deterministic_text_v1",
                    "query_id": query_id,
                    "execution_time_ms": round((time.perf_counter() - t_start) * 1000, 2),
                },
            )
            hits.append(hit)
            
        return hits
