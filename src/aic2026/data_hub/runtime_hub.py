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

