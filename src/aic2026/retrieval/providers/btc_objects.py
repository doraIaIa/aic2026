"""BTC Objects Retrieval Provider (M5D).

Provides deterministic, explainable detector-class FRAME retrieval in BTC frame space
over 177,321 canonical BTC keyframes and 17,732,100 OpenImages detections.

Identity contract:
- entity_type = FRAME
- frame_space = BTC
- provider = btc_objects
- score_type = btc_object_support
- score_direction = HIGHER_IS_BETTER
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from aic2026.retrieval.btc_objects_index import (
    CANONICAL_BTC_FRAME_COUNT,
    CANONICAL_DETECTION_COUNT,
    CANONICAL_VIDEO_COUNT,
    DEFAULT_OUTPUT_DIR,
    normalize_class_label,
)
from aic2026.retrieval.providers.base import (
    ProviderCapability,
    ProviderHit,
    ProviderIntegrityError,
    ProviderQuery,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

DEFAULT_INDEX_PATH = DEFAULT_OUTPUT_DIR / "btc_objects_postings.sqlite"
DEFAULT_PASSPORT_PATH = DEFAULT_OUTPUT_DIR / "btc_objects_passport.json"
DEFAULT_CLASSES_PATH = DEFAULT_OUTPUT_DIR / "classes.json"
MAX_TOP_K = 500


@dataclass
class BtcObjectsQuery:
    classes: list[str] = field(default_factory=list)
    match_mode: str = "ALL"  # "ALL" or "ANY"
    min_detector_score: float = 0.1
    top_k: int = 50
    candidate_video_ids: list[str] | None = None
    query_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.classes, str):
            self.classes = [self.classes]
        if not self.classes:
            raise ValueError("classes must be a non-empty list of class strings")
        self.match_mode = self.match_mode.upper()
        if self.match_mode not in ("ALL", "ANY"):
            raise ValueError("match_mode must be 'ALL' or 'ANY'")
        if not (0.0 <= self.min_detector_score <= 1.0):
            raise ValueError("min_detector_score must be between 0.0 and 1.0")
        if self.top_k <= 0 or self.top_k > MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")


class BtcObjectsProvider:
    """Deterministic structured object search provider over OpenImages BTC detections."""

    name = "btc_objects"

    def __init__(
        self,
        db_path: str | Path | None = None,
        artifact_dir: str | Path | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir) if artifact_dir else DEFAULT_OUTPUT_DIR
        self.db_path = Path(db_path) if db_path else (self.artifact_dir / "btc_objects_postings.sqlite")
        self.passport_path = self.artifact_dir / "btc_objects_passport.json"
        self.classes_path = self.artifact_dir / "classes.json"
        self._local = threading.local()
        self._classes_cache: list[dict[str, Any]] | None = None
        self._norm_to_class: dict[str, dict[str, Any]] = {}
        self._mid_to_class: dict[str, dict[str, Any]] = {}
        self._load_classes_dict()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            if not self.db_path.exists():
                raise ProviderUnavailableError(f"BTC objects postings index not found at {self.db_path}")
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

    def _load_classes_dict(self) -> None:
        if self.classes_path.exists():
            try:
                with open(self.classes_path, "r", encoding="utf-8") as fp:
                    self._classes_cache = json.load(fp)
                for item in self._classes_cache:
                    norm = item["class_norm"]
                    mid = item["class_name"]
                    entity = item["class_entity"]
                    self._norm_to_class[norm] = item
                    self._norm_to_class[normalize_class_label(entity)] = item
                    self._mid_to_class[mid] = item
                return
            except Exception as e:
                logger.warning("Failed to load classes.json: %s", e)

        # Fallback to database if available
        if self.db_path.exists():
            try:
                conn = self._get_conn()
                rows = conn.execute("SELECT * FROM class_dictionary ORDER BY frame_count DESC").fetchall()
                self._classes_cache = [dict(r) for r in rows]
                for item in self._classes_cache:
                    norm = item["class_norm"]
                    mid = item["class_name"]
                    entity = item["class_entity"]
                    self._norm_to_class[norm] = item
                    self._norm_to_class[normalize_class_label(entity)] = item
                    self._mid_to_class[mid] = item
            except Exception as e:
                logger.warning("Failed to load classes from SQLite: %s", e)

    def get_classes(self) -> list[dict[str, Any]]:
        """Return the complete list of 584 available detector classes."""
        if self._classes_cache is None:
            self._load_classes_dict()
        return self._classes_cache or []

    def resolve_class(self, query_class: str) -> dict[str, Any] | None:
        """Resolve a user-provided class query (by entity name, normalized name, or MID)."""
        if not query_class:
            return None
        norm = normalize_class_label(query_class)
        if norm in self._norm_to_class:
            return self._norm_to_class[norm]
        if query_class in self._mid_to_class:
            return self._mid_to_class[query_class]
        return None

    def capabilities(self) -> ProviderCapability:
        """Return provider status, metadata, counts, and checksums."""
        if not self.db_path.exists():
            return ProviderCapability(
                provider=self.name,
                status="UNAVAILABLE",
                reason=f"Index database not found at {self.db_path}",
                version="btc_objects_v1",
                checksums={},
                provenance={},
                counts={},
            )

        try:
            passport = {}
            if self.passport_path.exists():
                with open(self.passport_path, "r", encoding="utf-8") as fp:
                    passport = json.load(fp)

            conn = self._get_conn()
            c = conn.cursor()
            class_count = c.execute("SELECT COUNT(*) FROM class_dictionary").fetchone()[0]
            postings_count = c.execute("SELECT COUNT(*) FROM object_postings").fetchone()[0]

            counts = {
                "btc_canonical_frames": CANONICAL_BTC_FRAME_COUNT,
                "total_detections": CANONICAL_DETECTION_COUNT,
                "canonical_videos": CANONICAL_VIDEO_COUNT,
                "indexed_classes": class_count,
                "total_postings": postings_count,
            }

            checksums = {
                "database_sha256": passport.get("database_sha256", ""),
                "classes_sha256": passport.get("classes_sha256", ""),
            }

            return ProviderCapability(
                provider=self.name,
                status="OK",
                reason=None,
                version="btc_objects_v1",
                checksums=checksums,
                provenance=passport,
                counts=counts,
            )
        except Exception as e:
            return ProviderCapability(
                provider=self.name,
                status="INTEGRITY_ERROR",
                reason=str(e),
                version="btc_objects_v1",
                checksums={},
                provenance={},
                counts={},
            )

    def health(self) -> dict[str, Any]:
        """Convenient dictionary health endpoint for API / CLI."""
        cap = self.capabilities()
        return {
            "lane_id": self.name,
            "provider": self.name,
            "status": cap.status,
            "entity_type": "FRAME",
            "frame_space": "BTC",
            "score_type": "btc_object_support",
            "score_direction": "HIGHER_IS_BETTER",
            "reason": cap.reason,
            "version": cap.version,
            "counts": cap.counts,
            "checksums": cap.checksums,
            "provenance": cap.provenance,
        }

    def search(self, query: ProviderQuery | BtcObjectsQuery) -> list[ProviderHit]:
        """Entry point fulfilling SearchProvider protocol or direct BtcObjectsQuery."""
        if isinstance(query, ProviderQuery):
            # Parse comma or space separated classes if passed via generic ProviderQuery
            raw_classes = [c.strip() for c in query.query_text.split(",") if c.strip()]
            candidate_vids = list(query.video_ids) if query.video_ids else None
            obj_query = BtcObjectsQuery(
                classes=raw_classes or [query.query_text],
                match_mode="ALL",
                min_detector_score=0.1,
                top_k=query.top_k,
                candidate_video_ids=candidate_vids,
            )
            return self.search_objects(obj_query)
        elif isinstance(query, BtcObjectsQuery):
            return self.search_objects(query)
        else:
            raise ValueError(f"Unsupported query type: {type(query)}")

    def search_objects(self, query: BtcObjectsQuery) -> list[ProviderHit]:
        """Execute deterministic object search over BTC postings."""
        if not self.db_path.exists():
            raise ProviderUnavailableError(f"BTC objects index not found at {self.db_path}")

        # 1. Resolve requested classes
        resolved_classes: list[dict[str, Any]] = []
        unresolved_classes: list[str] = []
        for c_str in query.classes:
            res = self.resolve_class(c_str)
            if res:
                resolved_classes.append(res)
            else:
                unresolved_classes.append(c_str)

        match_mode = query.match_mode.upper()

        # Fail-closed semantics for ALL mode: if any requested class is unknown, 0 hits
        if match_mode == "ALL" and unresolved_classes:
            logger.info("Unresolved class '%s' in ALL mode -> returning empty result", unresolved_classes)
            return []

        # In ANY mode: if all requested classes are unknown, 0 hits
        if match_mode == "ANY" and not resolved_classes:
            logger.info("All classes unresolved in ANY mode -> returning empty result")
            return []

        # Deduplicate resolved classes by class_id
        unique_classes: dict[int, dict[str, Any]] = {c["class_id"]: c for c in resolved_classes}
        class_ids = list(unique_classes.keys())
        num_required = len(class_ids)

        conn = self._get_conn()
        c = conn.cursor()

        # Handle candidate video filtering
        vids_clause = ""
        params: list[Any] = []

        if query.candidate_video_ids is not None:
            vids = [v for v in query.candidate_video_ids if v]
            if not vids:
                return []
            placeholders = ",".join(["?"] * len(vids))
            vids_clause = f"AND video_id IN ({placeholders})"
            vids_params = list(vids)
        else:
            vids_params = []

        # Build SQL query based on match_mode and number of classes
        if match_mode == "ALL":
            if num_required == 1:
                cid = class_ids[0]
                sql = f"""
                    SELECT keyframe_uid, video_id, local_keyframe_no, frame_idx, timestamp_ms,
                           max_score as object_support_score,
                           class_id, max_score, detection_count, top_bbox_json, top_detections_json
                    FROM object_postings
                    WHERE class_id = ? AND max_score >= ? {vids_clause}
                    ORDER BY max_score DESC, video_id ASC, timestamp_ms ASC, keyframe_uid ASC
                    LIMIT ?
                """
                params = [cid, query.min_detector_score] + vids_params + [query.top_k]
                rows = c.execute(sql, params).fetchall()

                hits: list[ProviderHit] = []
                for i, r in enumerate(rows):
                    cls_entity = unique_classes[cid]["class_entity"]
                    top_bbox = json.loads(r["top_bbox_json"]) if r["top_bbox_json"] else [0, 0, 1, 1]
                    top_dets = json.loads(r["top_detections_json"]) if r["top_detections_json"] else []

                    payload = {
                        "entity_type": "FRAME",
                        "frame_space": "BTC",
                        "keyframe_uid": r["keyframe_uid"],
                        "video_id": r["video_id"],
                        "local_keyframe_no": r["local_keyframe_no"],
                        "frame_idx": r["frame_idx"],
                        "timestamp_ms": r["timestamp_ms"],
                        "score_type": "btc_object_support",
                        "score_direction": "HIGHER_IS_BETTER",
                        "match_mode": match_mode,
                        "min_detector_score": query.min_detector_score,
                        "requested_classes": query.classes,
                        "matched_classes": [cls_entity],
                        "class_scores": {cls_entity: r["max_score"]},
                        "class_counts": {cls_entity: r["detection_count"]},
                        "top_bboxes": {cls_entity: top_bbox},
                        "detections": top_dets,
                        "source_file_relpath": f"objects/{r['video_id']}/{r['local_keyframe_no']:03d}.json",
                    }

                    ts_sec = round(r["timestamp_ms"] / 1000.0, 3)
                    hit = ProviderHit(
                        provider=self.name,
                        evidence_id=f"BTC_OBJECT_HIT:{r['keyframe_uid']}",
                        video_id=r["video_id"],
                        rank=i + 1,
                        start_sec=ts_sec,
                        end_sec=ts_sec,
                        anchor_sec=ts_sec,
                        raw_score=round(r["object_support_score"], 6),
                        score_kind="btc_object_support",
                        artifact_version="btc_objects_v1",
                        payload=payload,
                        source_video_relpath=None,
                        provenance={"lane": self.name, "frame_space": "BTC"},
                    )
                    hits.append(hit)
                return hits

            else:
                # Multi-class ALL query
                cid_placeholders = ",".join(["?"] * num_required)
                sql = f"""
                    SELECT keyframe_uid, video_id, local_keyframe_no, frame_idx, timestamp_ms,
                           MIN(max_score) as object_support_score,
                           COUNT(DISTINCT class_id) as matched_count
                    FROM object_postings
                    WHERE class_id IN ({cid_placeholders}) AND max_score >= ? {vids_clause}
                    GROUP BY keyframe_uid
                    HAVING matched_count = ?
                    ORDER BY object_support_score DESC, video_id ASC, timestamp_ms ASC, keyframe_uid ASC
                    LIMIT ?
                """
                params = class_ids + [query.min_detector_score] + vids_params + [num_required, query.top_k]
                agg_rows = c.execute(sql, params).fetchall()

                if not agg_rows:
                    return []

                # Fetch detailed postings for returned keyframes
                kf_uids = [r["keyframe_uid"] for r in agg_rows]
                kf_placeholders = ",".join(["?"] * len(kf_uids))
                det_sql = f"""
                    SELECT keyframe_uid, class_id, max_score, detection_count, top_bbox_json, top_detections_json
                    FROM object_postings
                    WHERE keyframe_uid IN ({kf_placeholders}) AND class_id IN ({cid_placeholders})
                """
                det_rows = c.execute(det_sql, kf_uids + class_ids).fetchall()
                dets_by_kf: dict[str, list[sqlite3.Row]] = {}
                for dr in det_rows:
                    dets_by_kf.setdefault(dr["keyframe_uid"], []).append(dr)

                hits = []
                for i, r in enumerate(agg_rows):
                    kf_uid = r["keyframe_uid"]
                    kf_dets = dets_by_kf.get(kf_uid, [])

                    matched_classes = []
                    class_scores = {}
                    class_counts = {}
                    top_bboxes = {}
                    all_top_dets = []

                    for dr in kf_dets:
                        cid = dr["class_id"]
                        cls_info = unique_classes.get(cid)
                        cls_entity = cls_info["class_entity"] if cls_info else str(cid)
                        matched_classes.append(cls_entity)
                        class_scores[cls_entity] = dr["max_score"]
                        class_counts[cls_entity] = dr["detection_count"]
                        if dr["top_bbox_json"]:
                            top_bboxes[cls_entity] = json.loads(dr["top_bbox_json"])
                        if dr["top_detections_json"]:
                            all_top_dets.extend(json.loads(dr["top_detections_json"]))

                    all_top_dets.sort(key=lambda d: d.get("score", 0.0), reverse=True)

                    payload = {
                        "entity_type": "FRAME",
                        "frame_space": "BTC",
                        "keyframe_uid": kf_uid,
                        "video_id": r["video_id"],
                        "local_keyframe_no": r["local_keyframe_no"],
                        "frame_idx": r["frame_idx"],
                        "timestamp_ms": r["timestamp_ms"],
                        "score_type": "btc_object_support",
                        "score_direction": "HIGHER_IS_BETTER",
                        "match_mode": match_mode,
                        "min_detector_score": query.min_detector_score,
                        "requested_classes": query.classes,
                        "matched_classes": matched_classes,
                        "class_scores": class_scores,
                        "class_counts": class_counts,
                        "top_bboxes": top_bboxes,
                        "detections": all_top_dets[:10],
                        "source_file_relpath": f"objects/{r['video_id']}/{r['local_keyframe_no']:03d}.json",
                    }

                    ts_sec = round(r["timestamp_ms"] / 1000.0, 3)
                    hit = ProviderHit(
                        provider=self.name,
                        evidence_id=f"BTC_OBJECT_HIT:{kf_uid}",
                        video_id=r["video_id"],
                        rank=i + 1,
                        start_sec=ts_sec,
                        end_sec=ts_sec,
                        anchor_sec=ts_sec,
                        raw_score=round(r["object_support_score"], 6),
                        score_kind="btc_object_support",
                        artifact_version="btc_objects_v1",
                        payload=payload,
                        source_video_relpath=None,
                        provenance={"lane": self.name, "frame_space": "BTC"},
                    )
                    hits.append(hit)
                return hits

        else:
            # ANY mode
            cid_placeholders = ",".join(["?"] * num_required)
            sql = f"""
                SELECT keyframe_uid, video_id, local_keyframe_no, frame_idx, timestamp_ms,
                       MAX(max_score) as object_support_score
                FROM object_postings
                WHERE class_id IN ({cid_placeholders}) AND max_score >= ? {vids_clause}
                GROUP BY keyframe_uid
                ORDER BY object_support_score DESC, video_id ASC, timestamp_ms ASC, keyframe_uid ASC
                LIMIT ?
            """
            params = class_ids + [query.min_detector_score] + vids_params + [query.top_k]
            agg_rows = c.execute(sql, params).fetchall()

            if not agg_rows:
                return []

            kf_uids = [r["keyframe_uid"] for r in agg_rows]
            kf_placeholders = ",".join(["?"] * len(kf_uids))
            det_sql = f"""
                SELECT keyframe_uid, class_id, max_score, detection_count, top_bbox_json, top_detections_json
                FROM object_postings
                WHERE keyframe_uid IN ({kf_placeholders}) AND class_id IN ({cid_placeholders}) AND max_score >= ?
            """
            det_rows = c.execute(det_sql, kf_uids + class_ids + [query.min_detector_score]).fetchall()
            dets_by_kf = {}
            for dr in det_rows:
                dets_by_kf.setdefault(dr["keyframe_uid"], []).append(dr)

            hits = []
            for i, r in enumerate(agg_rows):
                kf_uid = r["keyframe_uid"]
                kf_dets = dets_by_kf.get(kf_uid, [])

                matched_classes = []
                class_scores = {}
                class_counts = {}
                top_bboxes = {}
                all_top_dets = []

                for dr in kf_dets:
                    cid = dr["class_id"]
                    cls_info = unique_classes.get(cid)
                    cls_entity = cls_info["class_entity"] if cls_info else str(cid)
                    matched_classes.append(cls_entity)
                    class_scores[cls_entity] = dr["max_score"]
                    class_counts[cls_entity] = dr["detection_count"]
                    if dr["top_bbox_json"]:
                        top_bboxes[cls_entity] = json.loads(dr["top_bbox_json"])
                    if dr["top_detections_json"]:
                        all_top_dets.extend(json.loads(dr["top_detections_json"]))

                all_top_dets.sort(key=lambda d: d.get("score", 0.0), reverse=True)

                payload = {
                    "entity_type": "FRAME",
                    "frame_space": "BTC",
                    "keyframe_uid": kf_uid,
                    "video_id": r["video_id"],
                    "local_keyframe_no": r["local_keyframe_no"],
                    "frame_idx": r["frame_idx"],
                    "timestamp_ms": r["timestamp_ms"],
                    "score_type": "btc_object_support",
                    "score_direction": "HIGHER_IS_BETTER",
                    "match_mode": match_mode,
                    "min_detector_score": query.min_detector_score,
                    "requested_classes": query.classes,
                    "matched_classes": matched_classes,
                    "class_scores": class_scores,
                    "class_counts": class_counts,
                    "top_bboxes": top_bboxes,
                    "detections": all_top_dets[:10],
                    "source_file_relpath": f"objects/{r['video_id']}/{r['local_keyframe_no']:03d}.json",
                }

                ts_sec = round(r["timestamp_ms"] / 1000.0, 3)
                hit = ProviderHit(
                    provider=self.name,
                    evidence_id=f"BTC_OBJECT_HIT:{kf_uid}",
                    video_id=r["video_id"],
                    rank=i + 1,
                    start_sec=ts_sec,
                    end_sec=ts_sec,
                    anchor_sec=ts_sec,
                    raw_score=round(r["object_support_score"], 6),
                    score_kind="btc_object_support",
                    artifact_version="btc_objects_v1",
                    payload=payload,
                    source_video_relpath=None,
                    provenance={"lane": self.name, "frame_space": "BTC"},
                )
                hits.append(hit)
            return hits
