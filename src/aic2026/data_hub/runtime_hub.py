from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aic2026.data_hub.index_registry_models import (
    ArtifactRegistryRecord,
    VectorIndexRecord,
)
from aic2026.data_hub.taxonomy_models import (
    TaxonomyNodeRecord,
    VideoMembershipRecord,
)
from aic2026.data_hub.text_normalizer import TextNormalizer


class RuntimeDataHub:
    """Read-only production repository for Data Hub runtime mapping.sqlite and index registry (M1E)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Runtime mapping.sqlite not found at {self.db_path}")
        self._conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row

    @classmethod
    def load_from_directory(cls, runtime_root: Path) -> RuntimeDataHub:
        """Load Data Hub runtime from retrieval_data_v1 directory."""
        runtime_root = Path(runtime_root)
        db_path = runtime_root / "runtime" / "mapping.sqlite"
        if not db_path.exists():
            # Check direct root
            if (runtime_root / "mapping.sqlite").exists():
                db_path = runtime_root / "mapping.sqlite"
            else:
                raise FileNotFoundError(f"Could not locate mapping.sqlite inside {runtime_root}")
        return cls(db_path=db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def __enter__(self) -> RuntimeDataHub:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Core Entity Access Methods
    # ------------------------------------------------------------------

    def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get canonical video record by video_id."""
        c = self._conn.cursor()
        c.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_keyframe(self, keyframe_uid: str) -> Optional[Dict[str, Any]]:
        """Get keyframe record (BTC or CUSTOM) by keyframe_uid."""
        c = self._conn.cursor()
        if keyframe_uid.startswith("BTC:"):
            c.execute("SELECT * FROM btc_keyframes WHERE keyframe_uid = ?", (keyframe_uid,))
        else:
            c.execute("SELECT * FROM custom_keyframes WHERE keyframe_uid = ?", (keyframe_uid,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_keyframes_near(
        self,
        video_id: str,
        timestamp_ms: int,
        frame_space: str = "BTC",
        window_ms: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Get keyframes for a video within a temporal window around timestamp_ms."""
        c = self._conn.cursor()
        t_min = max(0, timestamp_ms - window_ms)
        t_max = timestamp_ms + window_ms
        if frame_space.upper() == "BTC":
            c.execute(
                """
                SELECT * FROM btc_keyframes
                WHERE video_id = ? AND timestamp_ms BETWEEN ? AND ?
                ORDER BY timestamp_ms ASC
                """,
                (video_id, t_min, t_max),
            )
        else:
            c.execute(
                """
                SELECT * FROM custom_keyframes
                WHERE video_id = ? AND timestamp_ms BETWEEN ? AND ?
                ORDER BY timestamp_ms ASC
                """,
                (video_id, t_min, t_max),
            )
        return [dict(r) for r in c.fetchall()]

    def get_asr_near(
        self,
        video_id: str,
        timestamp_ms: int,
        window_ms: int = 15000,
    ) -> List[Dict[str, Any]]:
        """Get ASR speech segments overlapping or near timestamp_ms."""
        c = self._conn.cursor()
        t_min = max(0, timestamp_ms - window_ms)
        t_max = timestamp_ms + window_ms
        c.execute(
            """
            SELECT * FROM canonical_asr_segments
            WHERE video_id = ? AND end_ms >= ? AND start_ms <= ?
            ORDER BY start_ms ASC
            """,
            (video_id, t_min, t_max),
        )
        return [dict(r) for r in c.fetchall()]

    def get_asr_segment(self, segment_uid: str) -> Optional[Dict[str, Any]]:
        """Get canonical ASR speech segment record by segment_uid."""
        c = self._conn.cursor()
        c.execute("SELECT * FROM canonical_asr_segments WHERE segment_uid = ?", (segment_uid,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_qwen(self, keyframe_uid: str) -> Optional[Dict[str, Any]]:
        """Get Qwen rich multimodal semantic annotation for a CUSTOM keyframe."""
        c = self._conn.cursor()
        c.execute("SELECT * FROM qwen_frames WHERE keyframe_uid = ?", (keyframe_uid,))
        row = c.fetchone()
        if not row:
            return None
        d = dict(row)
        d["objects"] = json.loads(d.get("objects_json") or "[]")
        d["attributes"] = json.loads(d.get("attributes_json") or "[]")
        d["spatial_relations"] = json.loads(d.get("spatial_relations_json") or "[]")
        d["counts"] = json.loads(d.get("counts_json") or "[]")
        d["scene"] = json.loads(d.get("scene_json") or "[]")
        d["visible_actions"] = json.loads(d.get("visible_actions_json") or "[]")
        return d

    def get_ocr_for_keyframe(self, keyframe_uid: str) -> List[Dict[str, Any]]:
        """Get all raw OCR text items detected on a keyframe."""
        c = self._conn.cursor()
        c.execute(
            """
            SELECT * FROM ocr_items
            WHERE keyframe_uid = ?
            ORDER BY local_text_index ASC
            """,
            (keyframe_uid,),
        )
        items = []
        for r in c.fetchall():
            d = dict(r)
            d["bbox"] = json.loads(d.get("bbox_json") or "[]")
            items.append(d)
        return items

    def get_ocr_near(
        self,
        video_id: str,
        timestamp_ms: int,
        window_ms: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Get OCR text items near timestamp_ms for a video."""
        c = self._conn.cursor()
        t_min = max(0, timestamp_ms - window_ms)
        t_max = timestamp_ms + window_ms
        c.execute(
            """
            SELECT * FROM ocr_items
            WHERE video_id = ? AND timestamp_ms BETWEEN ? AND ?
            ORDER BY timestamp_ms ASC, local_text_index ASC
            """,
            (video_id, t_min, t_max),
        )
        items = []
        for r in c.fetchall():
            d = dict(r)
            d["bbox"] = json.loads(d.get("bbox_json") or "[]")
            items.append(d)
        return items

    def get_btc_objects_status(self, keyframe_uid: str) -> Optional[Dict[str, Any]]:
        """Get BTC object detection coverage status and count for a BTC keyframe."""
        c = self._conn.cursor()
        c.execute("SELECT * FROM btc_object_coverage WHERE keyframe_uid = ?", (keyframe_uid,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_media_info(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get YouTube media-info prior for a video."""
        c = self._conn.cursor()
        c.execute("SELECT * FROM media_info WHERE video_id = ?", (video_id,))
        row = c.fetchone()
        if not row:
            return None
        d = dict(row)
        d["keywords"] = json.loads(d.get("keywords_json") or "[]")
        return d

    def get_memberships(self, video_id: str) -> List[Dict[str, Any]]:
        """Get all taxonomy memberships (Program, Subject, etc.) for a video."""
        c = self._conn.cursor()
        c.execute(
            """
            SELECT vm.*, tn.label_vi, tn.label_en, tn.branch_type
            FROM video_memberships vm
            JOIN taxonomy_nodes tn ON vm.branch_id = tn.branch_id
            WHERE vm.video_id = ?
            ORDER BY vm.membership_type ASC
            """,
            (video_id,),
        )
        return [dict(r) for r in c.fetchall()]

    def get_branch_videos(self, branch_id: str) -> List[str]:
        """Get all video IDs belonging to a taxonomy branch."""
        c = self._conn.cursor()
        c.execute(
            """
            SELECT video_id FROM video_memberships
            WHERE branch_id = ?
            ORDER BY video_id ASC
            """,
            (branch_id,),
        )
        return [r[0] for r in c.fetchall()]

    def branch_count(self, branch_id: str) -> int:
        """Count videos in a taxonomy branch."""
        c = self._conn.cursor()
        c.execute("SELECT COUNT(*) FROM video_memberships WHERE branch_id = ?", (branch_id,))
        return c.fetchone()[0]

    def get_vector_index(self, index_id: str) -> Optional[Dict[str, Any]]:
        """Get vector index registry record by index_id."""
        c = self._conn.cursor()
        c.execute("SELECT * FROM vector_indexes WHERE index_id = ?", (index_id,))
        row = c.fetchone()
        if not row:
            return None
        d = dict(row)
        d["notes"] = json.loads(d.get("notes_json") or "[]")
        return d

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Get canonical artifact registry record by artifact_id."""
        c = self._conn.cursor()
        c.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,))
        row = c.fetchone()
        if not row:
            return None
        d = dict(row)
        d["notes"] = json.loads(d.get("notes_json") or "[]")
        return d

    # ------------------------------------------------------------------
    # Cross-Space Timeline & Nearest Keyframe Services (M1F)
    # ------------------------------------------------------------------

    def nearest_keyframe(
        self,
        video_id: str,
        timestamp_ms: int,
        frame_space: str = "BTC",
    ) -> Dict[str, Any]:
        """Find the nearest keyframe in requested frame_space using deterministic tie-breaking.

        Tie-breaking rules:
        1. Smallest abs_delta_ms
        2. Earliest timestamp_ms
        3. Alphabetically smallest keyframe_uid
        """
        space = frame_space.upper()
        if space not in ("BTC", "CUSTOM"):
            raise ValueError(f"Invalid frame_space '{frame_space}'. Must be 'BTC' or 'CUSTOM'.")

        v = self.get_video(video_id)
        if not v:
            raise ValueError(f"Unknown video_id '{video_id}'")

        table = "btc_keyframes" if space == "BTC" else "custom_keyframes"
        c = self._conn.cursor()

        # Predecessor (largest timestamp <= timestamp_ms)
        c.execute(
            f"""
            SELECT keyframe_uid, timestamp_ms, frame_idx, image_relpath
            FROM {table}
            WHERE video_id = ? AND timestamp_ms <= ?
            ORDER BY timestamp_ms DESC, keyframe_uid ASC
            LIMIT 1
            """,
            (video_id, timestamp_ms),
        )
        pred = c.fetchone()

        # Successor (smallest timestamp >= timestamp_ms)
        c.execute(
            f"""
            SELECT keyframe_uid, timestamp_ms, frame_idx, image_relpath
            FROM {table}
            WHERE video_id = ? AND timestamp_ms >= ?
            ORDER BY timestamp_ms ASC, keyframe_uid ASC
            LIMIT 1
            """,
            (video_id, timestamp_ms),
        )
        succ = c.fetchone()

        if not pred and not succ:
            return {
                "status": "NO_KEYFRAME_IN_SPACE",
                "requested_video_id": video_id,
                "requested_timestamp_ms": timestamp_ms,
                "frame_space": space,
                "keyframe_uid": None,
                "matched_timestamp_ms": None,
                "delta_ms": None,
                "abs_delta_ms": None,
                "frame_idx": None,
                "image_relpath": None,
                "relation_type": "DERIVED_ASSOCIATION",
            }

        candidates = []
        if pred:
            candidates.append(dict(pred))
        if succ and (not pred or succ["keyframe_uid"] != pred["keyframe_uid"]):
            candidates.append(dict(succ))

        best = min(
            candidates,
            key=lambda row: (
                abs(row["timestamp_ms"] - timestamp_ms),
                row["timestamp_ms"],
                row["keyframe_uid"],
            ),
        )

        matched_ts = best["timestamp_ms"]
        delta_ms = matched_ts - timestamp_ms
        abs_delta_ms = abs(delta_ms)

        return {
            "status": "MATCHED",
            "requested_video_id": video_id,
            "requested_timestamp_ms": timestamp_ms,
            "frame_space": space,
            "keyframe_uid": best["keyframe_uid"],
            "matched_timestamp_ms": matched_ts,
            "delta_ms": delta_ms,
            "abs_delta_ms": abs_delta_ms,
            "frame_idx": best["frame_idx"],
            "image_relpath": best["image_relpath"],
            "relation_type": "DERIVED_ASSOCIATION",
        }

    def compare_keyframe_spaces(self, video_id: str, timestamp_ms: int) -> Dict[str, Any]:
        """Return independent nearest BTC and CUSTOM keyframes for a requested time."""
        btc_res = self.nearest_keyframe(video_id, timestamp_ms, "BTC")
        custom_res = self.nearest_keyframe(video_id, timestamp_ms, "CUSTOM")
        return {
            "video_id": video_id,
            "requested_timestamp_ms": timestamp_ms,
            "btc": btc_res,
            "custom": custom_res,
        }

    def nearest_other_space(self, keyframe_uid: str) -> Dict[str, Any]:
        """Query the opposite frame space from a given keyframe UID."""
        is_btc = keyframe_uid.startswith("BTC:")
        kf = self.get_keyframe(keyframe_uid)
        if not kf:
            raise ValueError(f"Unknown keyframe_uid '{keyframe_uid}'")
        target_space = "CUSTOM" if is_btc else "BTC"
        return self.nearest_keyframe(kf["video_id"], kf["timestamp_ms"], target_space)

    # ------------------------------------------------------------------
    # Rich Multimodal Drilldown Services (M1F)
    # ------------------------------------------------------------------

    def get_video_drilldown(self, video_id: str) -> Dict[str, Any]:
        """Compact structured summary for a canonical video traversing all Data Hub spaces."""
        v = self.get_video(video_id)
        if not v:
            raise ValueError(f"Unknown video_id '{video_id}'")

        c = self._conn.cursor()
        media = self.get_media_info(video_id)
        memberships = self.get_memberships(video_id)

        # ASR stats
        c.execute("SELECT * FROM asr_video_coverage WHERE video_id = ?", (video_id,))
        asr_cov = c.fetchone()
        c.execute(
            """
            SELECT COUNT(*), MIN(start_ms), MAX(end_ms)
            FROM canonical_asr_segments WHERE video_id = ?
            """,
            (video_id,),
        )
        asr_stats = c.fetchone()
        asr_dict = {
            "status": asr_cov["asr_status"] if asr_cov else "UNKNOWN",
            "coverage_segment_count": asr_cov["segment_count"] if asr_cov else 0,
            "actual_segment_count": asr_stats[0],
            "first_start_ms": asr_stats[1],
            "last_end_ms": asr_stats[2],
        }

        # BTC stats
        c.execute(
            """
            SELECT COUNT(*), MIN(timestamp_ms), MAX(timestamp_ms)
            FROM btc_keyframes WHERE video_id = ?
            """,
            (video_id,),
        )
        btc_stats = c.fetchone()
        c.execute("SELECT COUNT(*) FROM btc_clip_rows WHERE video_id = ?", (video_id,))
        btc_clip_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM btc_object_coverage WHERE video_id = ?", (video_id,))
        btc_obj_cov_count = c.fetchone()[0]
        btc_dict = {
            "keyframe_count": btc_stats[0],
            "first_timestamp_ms": btc_stats[1],
            "last_timestamp_ms": btc_stats[2],
            "clip_row_count": btc_clip_count,
            "object_coverage_count": btc_obj_cov_count,
        }

        # CUSTOM stats
        c.execute(
            """
            SELECT COUNT(*), MIN(timestamp_ms), MAX(timestamp_ms)
            FROM custom_keyframes WHERE video_id = ?
            """,
            (video_id,),
        )
        custom_stats = c.fetchone()
        c.execute("SELECT COUNT(*) FROM qwen_frames WHERE video_id = ?", (video_id,))
        qwen_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM ocr_keyframes WHERE video_id = ?", (video_id,))
        ocr_kf_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM ocr_items WHERE video_id = ?", (video_id,))
        ocr_item_count = c.fetchone()[0]
        custom_dict = {
            "keyframe_count": custom_stats[0],
            "first_timestamp_ms": custom_stats[1],
            "last_timestamp_ms": custom_stats[2],
            "qwen_coverage_count": qwen_count,
            "ocr_keyframe_count": ocr_kf_count,
            "ocr_item_count": ocr_item_count,
            "siglip_mapped_row_count": custom_stats[0],
        }

        return {
            "video": v,
            "media_info": media,
            "memberships": memberships,
            "asr": asr_dict,
            "btc": btc_dict,
            "custom": custom_dict,
        }

    def get_frame_drilldown(
        self,
        keyframe_uid: str,
        nearby_asr_window_ms: int = 15000,
        include_objects: bool = False,
        object_limit: int = 10,
    ) -> Dict[str, Any]:
        """Rich multimodal frame drilldown for BTC or CUSTOM keyframe without inflating memory."""
        c = self._conn.cursor()
        is_btc = keyframe_uid.startswith("BTC:")

        kf = self.get_keyframe(keyframe_uid)
        if not kf:
            raise ValueError(f"Unknown keyframe_uid '{keyframe_uid}'")

        vid = kf["video_id"]
        ts = kf["timestamp_ms"]

        video = self.get_video(vid)
        media = self.get_media_info(vid)
        memberships = self.get_memberships(vid)
        nearby_asr = self.get_asr_near(vid, ts, nearby_asr_window_ms)

        if is_btc:
            c.execute("SELECT * FROM btc_clip_rows WHERE keyframe_uid = ?", (keyframe_uid,))
            clip_row = c.fetchone()
            obj_cov = self.get_btc_objects_status(keyframe_uid)
            nearest_custom = self.nearest_keyframe(vid, ts, "CUSTOM")

            res = {
                "keyframe_uid": keyframe_uid,
                "frame_space": "BTC",
                "video_id": vid,
                "local_keyframe_no": kf.get("local_keyframe_no"),
                "frame_idx": kf.get("frame_idx"),
                "timestamp_ms": ts,
                "raw_pts_time": kf.get("raw_pts_time"),
                "fps": kf.get("fps"),
                "image_relpath": kf.get("image_relpath"),
                "clip_row": dict(clip_row) if clip_row else None,
                "existing_faiss_status": "READY",
                "object_coverage": obj_cov,
                "nearby_asr": nearby_asr,
                "taxonomy_memberships": memberships,
                "media_info": media,
                "source_video_relpath": video.get("relpath") if video else None,
                "nearest_other_space": nearest_custom,
            }
            if include_objects:
                c.execute(
                    "SELECT * FROM btc_objects WHERE keyframe_uid = ? LIMIT ?",
                    (keyframe_uid, object_limit),
                )
                res["sample_objects"] = [dict(r) for r in c.fetchall()]
            return res

        else:
            qwen = self.get_qwen(keyframe_uid)
            ocr_items = self.get_ocr_for_keyframe(keyframe_uid)
            nearest_btc = self.nearest_keyframe(vid, ts, "BTC")

            return {
                "keyframe_uid": keyframe_uid,
                "frame_space": "CUSTOM",
                "video_id": vid,
                "frame_idx": kf.get("frame_idx"),
                "timestamp_ms": ts,
                "raw_pts_time": kf.get("raw_pts_time"),
                "embedding_index": kf.get("embedding_index"),
                "image_relpath": kf.get("image_relpath"),
                "qwen_semantic": qwen,
                "ocr_items": ocr_items,
                "ocr_item_count": len(ocr_items),
                "siglip_row_ref": f"output/embeddings/{vid}.npy[row={kf.get('frame_idx')}]",
                "siglip_status": "EMBEDDINGS_READY_INDEX_NOT_BUILT",
                "nearby_asr": nearby_asr,
                "taxonomy_memberships": memberships,
                "media_info": media,
                "source_video_relpath": video.get("relpath") if video else None,
                "nearest_other_space": nearest_btc,
            }


    # ------------------------------------------------------------------
    # Low-Level FTS5 Query Smoke Utilities (Not Ranking Engines)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_fts_query(query: str) -> str:
        norm_q = TextNormalizer.normalize_text(query)
        acc_q = TextNormalizer.strip_accents(query)
        # Escape double quotes
        norm_tokens = [f'"{t.replace(chr(34), "")}"' for t in norm_q.split() if t]
        acc_tokens = [f'"{t.replace(chr(34), "")}"' for t in acc_q.split() if t]
        if not norm_tokens:
            return '""'
        norm_clause = " AND ".join(norm_tokens)
        acc_clause = " AND ".join(acc_tokens)
        if norm_clause == acc_clause:
            return norm_clause
        return f"({norm_clause}) OR ({acc_clause})"

    def search_asr_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Smoke test search on asr_fts with matching canonical ASR segment entity."""
        c = self._conn.cursor()
        fts_expr = self._build_fts_query(query)
        c.execute(
            """
            SELECT fts.segment_uid, fts.video_id, fts.text_raw, seg.start_ms, seg.end_ms, bm25(asr_fts) as rank
            FROM asr_fts fts
            JOIN canonical_asr_segments seg ON fts.segment_uid = seg.segment_uid
            WHERE asr_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_expr, limit),
        )
        return [dict(r) for r in c.fetchall()]

    def search_ocr_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Smoke test search on ocr_fts with matching canonical OCR item entity."""
        c = self._conn.cursor()
        fts_expr = self._build_fts_query(query)
        c.execute(
            """
            SELECT fts.ocr_uid, fts.keyframe_uid, fts.video_id, fts.text_raw, ocr.timestamp_ms, bm25(ocr_fts) as rank
            FROM ocr_fts fts
            JOIN ocr_items ocr ON fts.ocr_uid = ocr.ocr_uid
            WHERE ocr_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_expr, limit),
        )
        return [dict(r) for r in c.fetchall()]

    def search_qwen_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Smoke test search on qwen_caption_fts with matching canonical Qwen frame entity."""
        c = self._conn.cursor()
        fts_expr = self._build_fts_query(query)
        c.execute(
            """
            SELECT fts.keyframe_uid, fts.video_id, fts.caption_raw, qf.timestamp_ms, bm25(qwen_caption_fts) as rank
            FROM qwen_caption_fts fts
            JOIN qwen_frames qf ON fts.keyframe_uid = qf.keyframe_uid
            WHERE qwen_caption_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_expr, limit),
        )
        return [dict(r) for r in c.fetchall()]

    def search_media_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Smoke test search on media_fts with matching media_info entity."""
        c = self._conn.cursor()
        fts_expr = self._build_fts_query(query)
        c.execute(
            """
            SELECT fts.video_id, fts.title_raw, mi.publish_date, bm25(media_fts) as rank
            FROM media_fts fts
            JOIN media_info mi ON fts.video_id = mi.video_id
            WHERE media_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_expr, limit),
        )
        return [dict(r) for r in c.fetchall()]

