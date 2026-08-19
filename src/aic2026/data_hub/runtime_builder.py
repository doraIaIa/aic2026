from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aic2026.data_hub.index_registry_models import (
    ArtifactRegistryRecord,
    VectorIndexRecord,
)
from aic2026.data_hub.taxonomy_builder import TaxonomyBuilder
from aic2026.data_hub.text_normalizer import TextNormalizer
from aic2026.data_hub.video_registry import VideoRegistry


class DataHubRuntimeBuilder:
    """Production materializer for mapping.sqlite, FTS5 indexes, and Index Registry (M1E)."""

    def __init__(
        self,
        video_registry: VideoRegistry,
        schema_path: Optional[Path] = None,
    ) -> None:
        self.video_registry = video_registry
        if schema_path is None:
            schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
        self.schema_path = schema_path

    @staticmethod
    def _file_sha256(filepath: Path) -> str:
        """Compute SHA-256 checksum of a file."""
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def build(
        self,
        output_root: Path,
        canonical_universe_dir: Path,
        canonical_custom_qwen_dir: Path,
        canonical_asr_ocr_dir: Path,
        canonical_btc_dir: Path,
    ) -> Dict[str, Any]:
        """Build the complete production Data Hub runtime bundle with atomic promotion."""
        t_start = time.time()
        build_id = f"m1e_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        output_root = Path(output_root)
        parent_dir = output_root.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        tmp_dir = parent_dir / f"retrieval_data_v1.tmp-{build_id}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        manifest_dir = tmp_dir / "manifest"
        canonical_dir = tmp_dir / "canonical"
        runtime_dir = tmp_dir / "runtime"
        manifest_dir.mkdir(exist_ok=True)
        canonical_dir.mkdir(exist_ok=True)
        runtime_dir.mkdir(exist_ok=True)

        print(f"=== BUILDING DATA HUB RUNTIME ({build_id}) ===")

        # ------------------------------------------------------------------
        # 1. Materialize Taxonomy
        # ------------------------------------------------------------------
        print("1. Materializing Program V1 and L25 Subject taxonomy...")
        tax_builder = TaxonomyBuilder(video_registry=self.video_registry)
        tax_nodes, tax_memberships, tax_space = tax_builder.materialize(canonical_dir)
        print(f"   Materialized {len(tax_nodes)} nodes, {len(tax_memberships)} memberships.")

        # ------------------------------------------------------------------
        # 2. Initialize SQLite Schema
        # ------------------------------------------------------------------
        db_path = runtime_dir / "mapping.sqlite"
        print(f"2. Initializing SQLite runtime database at {db_path}...")
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")

        with open(self.schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        # ------------------------------------------------------------------
        # 3. Stream Ingest Canonical Relational & FTS Tables
        # ------------------------------------------------------------------
        print("3. Ingesting canonical entities and populating FTS5 tables...")
        cursor = conn.cursor()

        # Videos
        v_count = 0
        v_file = canonical_universe_dir / "videos.jsonl"
        with open(v_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                v = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO videos(
                        video_id, ordinal, ordinal_space_id, series, relpath,
                        duration_ms, duration_sec, fps, width, height, status_flags, source_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        v["video_id"],
                        v["ordinal"],
                        v.get("ordinal_space_id", "v1_natural_series_video"),
                        v["series"],
                        v["source_relpath"],
                        v.get("duration_ms"),
                        v.get("duration_sec"),
                        v.get("fps"),
                        v.get("width"),
                        v.get("height"),
                        v.get("status_flags", "OK"),
                        v.get("source_id", "canonical_video_universe_v1"),
                    ),
                )
                v_count += 1
        print(f"   Ingested {v_count:,} videos.")

        # Media Info & Media FTS
        media_count = 0
        media_fts_count = 0
        media_file = canonical_btc_dir / "media_info.jsonl"
        with open(media_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                m = json.loads(line)
                kw_json = json.dumps(m.get("keywords", []), ensure_ascii=False)
                cursor.execute(
                    """
                    INSERT INTO media_info(
                        video_id, video_ordinal, ordinal_space_id, title, description,
                        keywords_json, author, channel_id, channel_url, publish_date,
                        duration_sec, thumbnail_url, watch_url, source_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m["video_id"],
                        m["video_ordinal"],
                        m.get("ordinal_space_id", "v1_natural_series_video"),
                        m["title"],
                        m.get("description"),
                        kw_json,
                        m.get("author"),
                        m.get("channel_id"),
                        m.get("channel_url"),
                        m.get("publish_date"),
                        m.get("duration_sec"),
                        m.get("thumbnail_url"),
                        m.get("watch_url"),
                        m.get("source_id", "btc_media_info_raw_v1"),
                    ),
                )
                media_count += 1

                # Media FTS
                t_raw = m.get("title", "")
                t_norm = TextNormalizer.normalize_text(t_raw)
                t_acc = TextNormalizer.strip_accents(t_raw)
                kw_text = " ".join(m.get("keywords", [])) if isinstance(m.get("keywords"), list) else ""
                desc_text = m.get("description", "") or ""

                cursor.execute(
                    """
                    INSERT INTO media_fts(video_id, title_raw, title_norm, title_accentless, keywords, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (m["video_id"], t_raw, t_norm, t_acc, kw_text, desc_text),
                )
                media_fts_count += 1
        print(f"   Ingested {media_count:,} media-info records and populated {media_fts_count:,} media_fts rows.")

        # Custom Keyframes
        ckf_count = 0
        ckf_file = canonical_custom_qwen_dir / "custom_keyframes.jsonl"
        with open(ckf_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                k = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO custom_keyframes(
                        keyframe_uid, video_id, video_ordinal, ordinal_space_id,
                        frame_idx, timestamp_ms, raw_pts_time, shot_id, cluster_id,
                        embedding_index, source_keyframe_id, file_name, image_relpath, qwen_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        k["keyframe_uid"],
                        k["video_id"],
                        k["video_ordinal"],
                        k.get("ordinal_space_id", "v1_natural_series_video"),
                        k["frame_idx"],
                        k["timestamp_ms"],
                        k["raw_pts_time"],
                        k.get("shot_id", 0),
                        k.get("cluster_id", 0),
                        k.get("embedding_index", 0),
                        k.get("source_keyframe_id", 0),
                        k["file_name"],
                        k["image_relpath"],
                        k.get("qwen_status", "OK"),
                    ),
                )
                ckf_count += 1
        print(f"   Ingested {ckf_count:,} custom keyframes.")

        # Qwen Frames & Qwen Caption FTS
        qwen_count = 0
        qwen_fts_count = 0
        qwen_file = canonical_custom_qwen_dir / "qwen_semantics_normalized.jsonl"
        with open(qwen_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                q = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO qwen_frames(
                        keyframe_uid, video_id, frame_idx, timestamp_ms, raw_pts_time,
                        objects_json, attributes_json, spatial_relations_json, counts_json,
                        scene_json, visible_actions_json, caption, semantic_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q["keyframe_uid"],
                        q["video_id"],
                        q["frame_idx"],
                        q["timestamp_ms"],
                        q["raw_pts_time"],
                        json.dumps(q.get("objects", []), ensure_ascii=False),
                        json.dumps(q.get("attributes", []), ensure_ascii=False),
                        json.dumps(q.get("spatial_relations", []), ensure_ascii=False),
                        json.dumps(q.get("counts", []), ensure_ascii=False),
                        json.dumps(q.get("scene", []), ensure_ascii=False),
                        json.dumps(q.get("visible_actions", []), ensure_ascii=False),
                        q.get("caption", ""),
                        q.get("semantic_status", "OK"),
                    ),
                )
                qwen_count += 1

                cap_raw = q.get("caption", "")
                cap_norm = TextNormalizer.normalize_text(cap_raw)
                cap_acc = TextNormalizer.strip_accents(cap_raw)
                cursor.execute(
                    """
                    INSERT INTO qwen_caption_fts(keyframe_uid, video_id, caption_raw, caption_norm, caption_accentless)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (q["keyframe_uid"], q["video_id"], cap_raw, cap_norm, cap_acc),
                )
                qwen_fts_count += 1
        print(f"   Ingested {qwen_count:,} Qwen frames and populated {qwen_fts_count:,} qwen_caption_fts rows.")

        # ASR Video Coverage
        asr_cov_count = 0
        asr_cov_file = canonical_asr_ocr_dir / "asr_video_coverage.jsonl"
        with open(asr_cov_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                cov = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO asr_video_coverage(
                        video_id, video_ordinal, ordinal_space_id, segment_count,
                        duration_sec, duration_ms, asr_status, source_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cov["video_id"],
                        cov["video_ordinal"],
                        cov.get("ordinal_space_id", "v1_natural_series_video"),
                        cov["segment_count"],
                        cov["duration_sec"],
                        cov["duration_ms"],
                        cov.get("asr_status", "HAS_SEGMENTS"),
                        cov.get("source_id", "asr_whisper_medium_vi_full_v1"),
                    ),
                )
                asr_cov_count += 1
        print(f"   Ingested {asr_cov_count:,} ASR video coverage records.")

        # ASR Segments & ASR FTS
        asr_seg_count = 0
        asr_fts_count = 0
        asr_seg_file = canonical_asr_ocr_dir / "asr_segments_canonical.jsonl"
        with open(asr_seg_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                s = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO canonical_asr_segments(
                        segment_uid, source_segment_id, video_id, video_ordinal,
                        ordinal_space_id, start_ms, end_ms, start_sec, end_sec,
                        text_raw, text_norm, language, model, avg_logprob,
                        no_speech_prob, compression_ratio, batch_id, source_file,
                        source_id, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        s["segment_uid"],
                        s["source_segment_id"],
                        s["video_id"],
                        s["video_ordinal"],
                        s.get("ordinal_space_id", "v1_natural_series_video"),
                        s["start_ms"],
                        s["end_ms"],
                        s["start_sec"],
                        s["end_sec"],
                        s["text_raw"],
                        s["text_norm"],
                        s.get("language", "vi"),
                        s.get("model", "whisper-medium"),
                        s.get("avg_logprob"),
                        s.get("no_speech_prob"),
                        s.get("compression_ratio"),
                        s.get("batch_id"),
                        s.get("source_file"),
                        s.get("source_id", "asr_whisper_medium_vi_full_v1"),
                        s.get("schema_version", "v1"),
                    ),
                )
                asr_seg_count += 1

                t_raw = s["text_raw"]
                t_norm = s.get("text_norm") or TextNormalizer.normalize_text(t_raw)
                t_acc = TextNormalizer.strip_accents(t_raw)
                cursor.execute(
                    """
                    INSERT INTO asr_fts(segment_uid, video_id, text_raw, text_norm, text_accentless)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (s["segment_uid"], s["video_id"], t_raw, t_norm, t_acc),
                )
                asr_fts_count += 1
        print(f"   Ingested {asr_seg_count:,} ASR segments and populated {asr_fts_count:,} asr_fts rows.")

        # OCR Keyframe Coverage
        ocr_cov_count = 0
        ocr_cov_file = canonical_asr_ocr_dir / "ocr_keyframe_coverage.jsonl"
        with open(ocr_cov_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                cov = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO ocr_keyframes(
                        keyframe_uid, video_id, video_ordinal, frame_idx,
                        timestamp_ms, raw_pts_time, file_name, image_relpath,
                        item_count, source_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cov["keyframe_uid"],
                        cov["video_id"],
                        cov["video_ordinal"],
                        cov["frame_idx"],
                        cov["timestamp_ms"],
                        cov["raw_pts_time"],
                        cov["file_name"],
                        cov["image_relpath"],
                        cov["item_count"],
                        cov.get("source_id", "ocr_custom_manifest_v1"),
                    ),
                )
                ocr_cov_count += 1
        print(f"   Ingested {ocr_cov_count:,} OCR keyframe coverage records.")

        # OCR Items & OCR FTS
        ocr_item_count = 0
        ocr_fts_count = 0
        ocr_item_file = canonical_asr_ocr_dir / "ocr_items_canonical.jsonl"
        with open(ocr_item_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                item = json.loads(line)
                bbox_json = json.dumps(item.get("bbox", []), ensure_ascii=False)
                cursor.execute(
                    """
                    INSERT INTO ocr_items(
                        ocr_uid, video_id, video_ordinal, ordinal_space_id,
                        frame_space, keyframe_uid, frame_idx, timestamp_ms,
                        raw_pts_time, local_text_index, text_raw, text_norm,
                        bbox_json, ocr_confidence, ocr_type, dense_embedding_ref,
                        source_id, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["ocr_uid"],
                        item["video_id"],
                        item["video_ordinal"],
                        item.get("ordinal_space_id", "v1_natural_series_video"),
                        item.get("frame_space", "CUSTOM"),
                        item["keyframe_uid"],
                        item["frame_idx"],
                        item["timestamp_ms"],
                        item["raw_pts_time"],
                        item["local_text_index"],
                        item["text_raw"],
                        item["text_norm"],
                        bbox_json,
                        item.get("ocr_confidence"),
                        item.get("ocr_type"),
                        item.get("dense_embedding_ref"),
                        item.get("source_id", "ocr_custom_manifest_v1"),
                        item.get("schema_version", "v1"),
                    ),
                )
                ocr_item_count += 1

                t_raw = item["text_raw"]
                t_norm = item.get("text_norm") or TextNormalizer.normalize_text(t_raw)
                t_acc = TextNormalizer.strip_accents(t_raw)
                cursor.execute(
                    """
                    INSERT INTO ocr_fts(ocr_uid, keyframe_uid, video_id, text_raw, text_norm, text_accentless)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (item["ocr_uid"], item["keyframe_uid"], item["video_id"], t_raw, t_norm, t_acc),
                )
                ocr_fts_count += 1
        print(f"   Ingested {ocr_item_count:,} OCR items and populated {ocr_fts_count:,} ocr_fts rows.")

        # OCR BGE Rowmap
        ocr_bge_count = 0
        ocr_bge_file = canonical_asr_ocr_dir / "ocr_bge_rowmap.jsonl"
        with open(ocr_bge_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rm = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO ocr_bge_rowmap(
                        index_id, shard_id, row_in_shard, global_row,
                        ocr_uid, keyframe_uid, video_id, frame_idx,
                        timestamp_ms, source_metadata_ref
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rm.get("index_id", "ocr_bge_m3_single_text_v1"),
                        rm["shard_id"],
                        rm["row_in_shard"],
                        rm.get("global_row"),
                        rm["ocr_uid"],
                        rm["keyframe_uid"],
                        rm["video_id"],
                        rm["frame_idx"],
                        rm["timestamp_ms"],
                        rm.get("source_metadata_ref"),
                    ),
                )
                ocr_bge_count += 1
        print(f"   Ingested {ocr_bge_count:,} OCR BGE row mappings.")

        # BTC Keyframes
        btc_kf_count = 0
        btc_kf_file = canonical_btc_dir / "btc_keyframes.jsonl"
        with open(btc_kf_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                bkf = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO btc_keyframes(
                        keyframe_uid, video_id, video_ordinal, ordinal_space_id,
                        local_keyframe_no, frame_idx, timestamp_ms, raw_pts_time,
                        fps, image_relpath, frame_space, btc_space_id, map_source_id,
                        clip_status, object_status, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bkf["keyframe_uid"],
                        bkf["video_id"],
                        bkf["video_ordinal"],
                        bkf.get("ordinal_space_id", "v1_natural_series_video"),
                        bkf["local_keyframe_no"],
                        bkf["frame_idx"],
                        bkf["timestamp_ms"],
                        bkf["raw_pts_time"],
                        bkf["fps"],
                        bkf["image_relpath"],
                        bkf.get("frame_space", "BTC"),
                        bkf.get("btc_space_id", "btc_keyframes_v1"),
                        bkf.get("map_source_id", "btc_map_keyframes_raw_v1"),
                        bkf.get("clip_status", "HAS_CLIP_ROW"),
                        bkf.get("object_status", "HAS_OBJECTS"),
                        bkf.get("schema_version", "v1"),
                    ),
                )
                btc_kf_count += 1
        print(f"   Ingested {btc_kf_count:,} BTC keyframes.")

        # BTC CLIP Rows
        btc_clip_count = 0
        btc_clip_file = canonical_btc_dir / "btc_clip_raw_rowmap.jsonl"
        with open(btc_clip_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                bclip = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO btc_clip_rows(
                        clip_source_id, video_id, video_ordinal, ordinal_space_id,
                        row_in_video, keyframe_uid, local_keyframe_no, frame_idx,
                        timestamp_ms, feature_relpath, dimension, dtype, normalized
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bclip.get("clip_source_id", "btc_clip_features_32_v1"),
                        bclip["video_id"],
                        bclip["video_ordinal"],
                        bclip.get("ordinal_space_id", "v1_natural_series_video"),
                        bclip["row_in_video"],
                        bclip["keyframe_uid"],
                        bclip["local_keyframe_no"],
                        bclip["frame_idx"],
                        bclip["timestamp_ms"],
                        bclip["feature_relpath"],
                        bclip.get("dimension", 512),
                        bclip.get("dtype", "float16"),
                        1 if bclip.get("normalized", True) else 0,
                    ),
                )
                btc_clip_count += 1
        print(f"   Ingested {btc_clip_count:,} BTC CLIP row mappings.")

        # BTC Object Coverage
        btc_cov_count = 0
        btc_cov_file = canonical_btc_dir / "btc_object_coverage.jsonl"
        with open(btc_cov_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                bcov = json.loads(line)
                cursor.execute(
                    """
                    INSERT INTO btc_object_coverage(
                        keyframe_uid, video_id, video_ordinal, local_keyframe_no,
                        frame_idx, timestamp_ms, detection_count, object_status,
                        source_file_relpath
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bcov["keyframe_uid"],
                        bcov["video_id"],
                        bcov["video_ordinal"],
                        bcov["local_keyframe_no"],
                        bcov["frame_idx"],
                        bcov["timestamp_ms"],
                        bcov["detection_count"],
                        bcov.get("object_status", "HAS_OBJECTS"),
                        bcov["source_file_relpath"],
                    ),
                )
                btc_cov_count += 1
        print(f"   Ingested {btc_cov_count:,} BTC object coverage records.")

        # Taxonomy Nodes
        for n in tax_nodes:
            cursor.execute(
                """
                INSERT INTO taxonomy_nodes(
                    branch_id, branch_type, label_vi, label_en, parent_ids_json,
                    aliases_json, requires_region_index, active, schema_version, source_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    n.branch_id,
                    n.branch_type,
                    n.label_vi,
                    n.label_en,
                    json.dumps(n.parent_ids, ensure_ascii=False),
                    json.dumps(n.aliases, ensure_ascii=False),
                    1 if n.requires_region_index else 0,
                    1 if n.active else 0,
                    n.schema_version,
                    n.source_id,
                ),
            )

        # Video Memberships
        for m in tax_memberships:
            cursor.execute(
                """
                INSERT INTO video_memberships(
                    membership_id, video_id, branch_id, membership_type, status,
                    confidence, score_type, evidence, prune_override, schema_version, source_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    m.membership_id,
                    m.video_id,
                    m.branch_id,
                    m.membership_type,
                    m.status,
                    m.confidence,
                    m.score_type,
                    m.evidence,
                    m.prune_override,
                    m.schema_version,
                    m.source_id,
                ),
            )
        print(f"   Ingested {len(tax_nodes)} taxonomy nodes and {len(tax_memberships)} video memberships.")

        # ------------------------------------------------------------------
        # 4. Register Vector Indexes & Artifacts
        # ------------------------------------------------------------------
        print("4. Registering vector indexes and canonical artifacts...")

        # Vector Indexes
        vector_index_records = [
            VectorIndexRecord(
                index_id="btc_clip_raw_features_v1",
                artifact_type="RAW_EMBEDDING_MATRIX",
                entity_space="KEYFRAME",
                frame_space="BTC",
                model_id="openai/clip-vit-base-patch32",
                dimension=512,
                dtype="float16",
                normalized=True,
                row_count=177321,
                status="READY",
                logical_ref="canonical_btc_v1/btc_clip_raw_rowmap.jsonl",
                built_from="data_extracted/clip-features-32/*.npy",
                rowmap_count=177321,
                rowmap_checksum="08921ac7c016e22030bcfe03928a5306da69cbc8bb79ce79f536c2bf4439075f",
                notes=["873 float16 512D arrays mapped 1:1 via row i <-> n = i + 1"],
            ),
            VectorIndexRecord(
                index_id="clip-faiss-btc-v1",
                artifact_type="FAISS_INDEX",
                entity_space="KEYFRAME",
                frame_space="BTC",
                model_id="openai/clip-vit-base-patch32",
                dimension=512,
                dtype="float32",
                normalized=True,
                row_count=177321,
                metric="cosine_via_normalized_inner_product",
                status="READY",
                logical_ref="artifacts/m1/clip-faiss-btc-v1/clip.index",
                built_from="data_extracted/clip-features-32/*.npy",
                rowmap_count=177321,
                artifact_checksum="08ed3cdbe250401560d04a4a26f9958c92672739141b664c5c59b75bfcfac0b3",
                notes=["Existing production BTC FAISS IndexFlatIP mapped 177,321 / 177,321 (0 gap)"],
            ),
            VectorIndexRecord(
                index_id="ocr_bge_m3_sharded_v1",
                artifact_type="SHARDED_EMBEDDINGS",
                entity_space="OCR_ITEM",
                frame_space="CUSTOM",
                model_id="BAAI/bge-m3",
                dimension=1024,
                dtype="float32",
                normalized=True,
                row_count=612813,
                status="EMBEDDINGS_READY_INDEX_NOT_BUILT",
                logical_ref="canonical_asr_ocr_v1/ocr_bge_rowmap.jsonl",
                built_from="ocr_single_text_retrieval/embeddings_shard_*.npy",
                rowmap_count=612813,
                rowmap_checksum="bca42b47ea56ee7f1fffe8479e0a2948eb97e744ec4e3c5483ea3fc092e07198",
                notes=["10 BGE-M3 float32 shards, dense row mapping validated 1:1, FAISS index not built in M1E"],
            ),
            VectorIndexRecord(
                index_id="custom_siglip2_raw_features_v1",
                artifact_type="RAW_EMBEDDING_MATRIX",
                entity_space="KEYFRAME",
                frame_space="CUSTOM",
                model_id="google/siglip2-base-patch16-224",
                dimension=768,
                dtype="float32",
                normalized=True,
                row_count=116767,
                status="EMBEDDINGS_READY_INDEX_NOT_BUILT",
                logical_ref="output/embeddings/*.npy",
                built_from="output/embeddings/*.npy",
                rowmap_count=116767,
                notes=["873 float32 768D arrays mapped 1:1 to CUSTOM keyframe_uid, FAISS index not built in M1E"],
            ),
        ]

        for vi in vector_index_records:
            cursor.execute(
                """
                INSERT INTO vector_indexes(
                    index_id, artifact_type, entity_space, frame_space, model_id,
                    dimension, dtype, normalized, row_count, status, logical_ref,
                    built_from, model_revision, metric, rowmap_count, rowmap_checksum,
                    artifact_checksum, query_preprocessing_version, ordinal_space_id, notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vi.index_id,
                    vi.artifact_type,
                    vi.entity_space,
                    vi.frame_space,
                    vi.model_id,
                    vi.dimension,
                    vi.dtype,
                    1 if vi.normalized else 0,
                    vi.row_count,
                    vi.status,
                    vi.logical_ref,
                    vi.built_from,
                    vi.model_revision,
                    vi.metric,
                    vi.rowmap_count,
                    vi.rowmap_checksum,
                    vi.artifact_checksum,
                    vi.query_preprocessing_version,
                    vi.ordinal_space_id,
                    json.dumps(vi.notes, ensure_ascii=False),
                ),
            )

        # Artifacts
        artifact_registry_records = [
            ArtifactRegistryRecord(
                artifact_id="canonical_video_universe_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="VIDEO",
                logical_ref="canonical_universe_v1/videos.jsonl",
                record_count=v_count,
                checksum="cf4b23861c8340d2105157864aa9a7852c02052b610c14b7e802a4bf7fe7444c",
                status="READY",
                built_from="asr_master_videos.jsonl",
                producer="M1A_VIDEO_REGISTRY",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_custom_keyframes_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="CUSTOM_KEYFRAME",
                logical_ref="canonical_custom_qwen_v1/custom_keyframes.jsonl",
                record_count=ckf_count,
                checksum="7a4fb2e260905471d2b8fe0901e67c8fcb5cf07c47d337d11ce3bbbb13854964",
                status="READY",
                built_from="data_extracted/map_keyframes/*.csv",
                producer="M1B_CUSTOM_KEYFRAMES",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_qwen_semantics_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="CUSTOM_KEYFRAME",
                logical_ref="canonical_custom_qwen_v1/qwen_semantics_normalized.jsonl",
                record_count=qwen_count,
                checksum="735c03df39cbbca10787e9eb7b37ca9899f8d95139049a4e3fae9e248b625cf0",
                status="READY",
                built_from="output_llm/shard_000.jsonl",
                producer="M1B_QWEN_NORMALIZER",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_asr_segments_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="ASR_SEGMENT",
                logical_ref="canonical_asr_ocr_v1/asr_segments_canonical.jsonl",
                record_count=asr_seg_count,
                checksum="f5ff17b9b1aa92e27be76cb581f18538ef43389bf449eeea2b27376a9a7d2b48",
                status="READY",
                built_from="master_segments.jsonl",
                producer="M1C_ASR_CANONICAL",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_ocr_items_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="OCR_ITEM",
                logical_ref="canonical_asr_ocr_v1/ocr_items_canonical.jsonl",
                record_count=ocr_item_count,
                checksum="2bfd7ba8564177c385db1f99c27fe76d05fdbf7ff3b10b0b8c6e25da898a3b8e",
                status="READY",
                built_from="ocr_results/*.json",
                producer="M1C_OCR_RAW_UNIVERSE",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_ocr_bge_rowmap_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="OCR_ITEM",
                logical_ref="canonical_asr_ocr_v1/ocr_bge_rowmap.jsonl",
                record_count=ocr_bge_count,
                checksum="bca42b47ea56ee7f1fffe8479e0a2948eb97e744ec4e3c5483ea3fc092e07198",
                status="READY",
                built_from="ocr_single_text_retrieval/metadata_shard_*.json",
                producer="M1C_OCR_BGE_ROWMAP",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_btc_keyframes_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="BTC_KEYFRAME",
                logical_ref="canonical_btc_v1/btc_keyframes.jsonl",
                record_count=btc_kf_count,
                checksum="70332506a7d7f5bf2ce5f4ec72cd91a4bffe3c551a7aeeed3a7d7b0c1056cd12",
                status="READY",
                built_from="data_extracted/map-keyframes/*.csv",
                producer="M1D_BTC_KEYFRAMES",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_btc_clip_rowmap_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="BTC_KEYFRAME",
                logical_ref="canonical_btc_v1/btc_clip_raw_rowmap.jsonl",
                record_count=btc_clip_count,
                checksum="08921ac7c016e22030bcfe03928a5306da69cbc8bb79ce79f536c2bf4439075f",
                status="READY",
                built_from="data_extracted/clip-features-32/*.npy",
                producer="M1D_BTC_CLIP_ROWMAP",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_btc_object_coverage_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="BTC_KEYFRAME",
                logical_ref="canonical_btc_v1/btc_object_coverage.jsonl",
                record_count=btc_cov_count,
                checksum="074b1e9c20a442e39ec2b15e4785ca8dbcc7ba64757c9ec92b3a0f1fa44ecb36",
                status="READY",
                built_from="data/objects-aic25-b1.zip",
                producer="M1D_BTC_OBJECT_COVERAGE",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_btc_objects_raw_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="BTC_OBJECT_DETECTION",
                logical_ref="canonical_btc_v1/btc_objects.jsonl",
                record_count=17732100,
                checksum="78f087b931d94e2efd0c69c8e6dd4072abdb23ccf55c9b3ea253aea85aeaf24c",
                status="READY_EXTERNAL",
                built_from="data/objects-aic25-b1.zip",
                producer="M1D_BTC_OBJECTS",
                notes=["Kept external in canonical_btc_v1 to avoid mapping.sqlite bloat; coverage table imported"],
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_media_info_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="VIDEO",
                logical_ref="canonical_btc_v1/media_info.jsonl",
                record_count=media_count,
                checksum="7b16a48ff935d5a690980e1b02391b15b09c3cd010844eea83ea6725d225999d",
                status="READY",
                built_from="data/media-info-aic25-b1.zip",
                producer="M1D_MEDIA_INFO",
            ),
            ArtifactRegistryRecord(
                artifact_id="canonical_taxonomy_v1",
                artifact_type="JSONL_ENTITY_TABLE",
                schema_version="v1",
                entity_space="TAXONOMY",
                logical_ref="canonical/taxonomy_nodes.jsonl",
                record_count=len(tax_nodes) + len(tax_memberships),
                checksum=tax_space.checksum,
                status="READY",
                built_from="AIC2026_HIERARCHICAL_RETRIEVAL_AUDIT_TAXONOMY_V1.md",
                producer="M1E_TAXONOMY_BUILDER",
            ),
        ]

        for ar in artifact_registry_records:
            cursor.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, artifact_type, schema_version, entity_space,
                    logical_ref, record_count, checksum, status, built_from,
                    producer, notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ar.artifact_id,
                    ar.artifact_type,
                    ar.schema_version,
                    ar.entity_space,
                    ar.logical_ref,
                    ar.record_count,
                    ar.checksum,
                    ar.status,
                    ar.built_from,
                    ar.producer,
                    json.dumps(ar.notes, ensure_ascii=False),
                ),
            )

        # ------------------------------------------------------------------
        # 5. Populate Runtime Metadata & Analyze
        # ------------------------------------------------------------------
        print("5. Populating runtime metadata, running integrity check and ANALYZE...")
        runtime_meta_kv = {
            "build_id": build_id,
            "schema_version": "v1",
            "fts_tokenizer": "unicode61",
            "normalizer_version": "v1_nfc_accentless",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "video_count": str(v_count),
            "custom_keyframe_count": str(ckf_count),
            "qwen_frame_count": str(qwen_count),
            "asr_segment_count": str(asr_seg_count),
            "ocr_item_count": str(ocr_item_count),
            "ocr_bge_row_count": str(ocr_bge_count),
            "btc_keyframe_count": str(btc_kf_count),
            "btc_clip_row_count": str(btc_clip_count),
            "btc_object_coverage_count": str(btc_cov_count),
            "media_info_count": str(media_count),
            "taxonomy_node_count": str(len(tax_nodes)),
            "video_membership_count": str(len(tax_memberships)),
        }
        for k, v in runtime_meta_kv.items():
            cursor.execute("INSERT OR REPLACE INTO runtime_meta(key, value) VALUES (?, ?)", (k, v))
            cursor.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)", (k, v))

        conn.commit()

        # Integrity Check
        cursor.execute("PRAGMA integrity_check;")
        integrity_rows = cursor.fetchall()
        integrity_status = integrity_rows[0][0] if integrity_rows else "UNKNOWN"
        if integrity_status != "ok":
            raise ValueError(f"SQLite PRAGMA integrity_check FAILED: {integrity_rows}")

        # Foreign Key Check
        cursor.execute("PRAGMA foreign_key_check;")
        fk_violations = cursor.fetchall()
        if fk_violations:
            raise ValueError(f"SQLite PRAGMA foreign_key_check FAILED with {len(fk_violations)} violations: {fk_violations[:10]}")

        # Optimize & Close WAL
        cursor.execute("ANALYZE;")
        conn.commit()
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.close()

        sqlite_size = db_path.stat().st_size
        sqlite_sha = self._file_sha256(db_path)
        print(f"   mapping.sqlite: {sqlite_size:,} bytes (SHA-256: {sqlite_sha})")
        print(f"   PRAGMA integrity_check: {integrity_status}")
        print(f"   PRAGMA foreign_key_check: 0 violations")

        # ------------------------------------------------------------------
        # 6. Write Manifests & Index Registry JSONL
        # ------------------------------------------------------------------
        print("6. Writing runtime registries and manifests...")

        # index_registry.jsonl in runtime/
        with open(runtime_dir / "index_registry.jsonl", "w", encoding="utf-8") as f:
            for vi in vector_index_records:
                f.write(json.dumps(vi.to_dict(), ensure_ascii=False) + "\n")

        # canonical_registry.jsonl in manifest/
        with open(manifest_dir / "canonical_registry.jsonl", "w", encoding="utf-8") as f:
            for ar in artifact_registry_records:
                f.write(json.dumps(ar.to_dict(), ensure_ascii=False) + "\n")

        # source_registry.jsonl in manifest/
        with open(manifest_dir / "source_registry.jsonl", "w", encoding="utf-8") as f:
            for ar in artifact_registry_records:
                src_dict = {
                    "source_id": ar.artifact_id,
                    "source_type": ar.artifact_type,
                    "scope": ar.entity_space,
                    "relative_path_or_logical_ref": ar.logical_ref,
                    "schema_version": ar.schema_version,
                    "record_count": ar.record_count,
                    "checksum": ar.checksum,
                    "status": ar.status,
                    "producer": ar.producer,
                }
                f.write(json.dumps(src_dict, ensure_ascii=False) + "\n")

        # build_manifest.json
        build_duration = time.time() - t_start
        build_manifest = {
            "build_id": build_id,
            "git_commit": "aa6ba4121fec4b7d797ef09b4b2c6e3a096235db",
            "schema_version": "v1",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "build_duration_sec": round(build_duration, 2),
            "sqlite_version": sqlite3.sqlite_version,
            "fts5_status": "AVAILABLE",
            "fts_tokenizer": "unicode61",
            "normalizer_version": "v1_nfc_accentless",
            "mapping_sqlite": {
                "byte_size": sqlite_size,
                "sha256": sqlite_sha,
                "integrity_check": integrity_status,
                "foreign_key_violations": 0,
            },
            "relational_counts": {
                "videos": v_count,
                "media_info": media_count,
                "custom_keyframes": ckf_count,
                "qwen_frames": qwen_count,
                "asr_video_coverage": asr_cov_count,
                "asr_segments": asr_seg_count,
                "ocr_keyframe_coverage": ocr_cov_count,
                "ocr_items": ocr_item_count,
                "ocr_bge_rows": ocr_bge_count,
                "btc_keyframes": btc_kf_count,
                "btc_clip_rows": btc_clip_count,
                "btc_object_coverage": btc_cov_count,
                "taxonomy_nodes": len(tax_nodes),
                "video_memberships": len(tax_memberships),
            },
            "fts_counts": {
                "asr_fts": asr_fts_count,
                "ocr_fts": ocr_fts_count,
                "qwen_caption_fts": qwen_fts_count,
                "media_fts": media_fts_count,
            },
            "external_artifacts": {
                "btc_objects_corpus": {
                    "record_count": 17732100,
                    "checksum": "78f087b931d94e2efd0c69c8e6dd4072abdb23ccf55c9b3ea253aea85aeaf24c",
                    "status": "READY_EXTERNAL",
                    "relational_imported": 0,
                }
            },
            "taxonomy_summary": {
                "program_memberships": 873,
                "status_counts": tax_space.status_counts,
                "program_counts": tax_space.program_counts,
                "l25_subjects": 88,
            },
            "vector_indexes": [vi.index_id for vi in vector_index_records],
            "raw_mutations": 0,
            "inference_reruns": 0,
            "status": "PASS",
        }

        with open(manifest_dir / "build_manifest.json", "w", encoding="utf-8") as f:
            json.dump(build_manifest, f, indent=2)

        # checksums.sha256
        checksum_lines = []
        for p in sorted(tmp_dir.rglob("*")):
            if p.is_file():
                rel = p.relative_to(tmp_dir).as_posix()
                h = self._file_sha256(p)
                checksum_lines.append(f"{h}  {rel}")
        with open(manifest_dir / "checksums.sha256", "w", encoding="utf-8") as f:
            f.write("\n".join(checksum_lines) + "\n")

        # ------------------------------------------------------------------
        # 7. Atomic Promotion
        # ------------------------------------------------------------------
        print(f"7. Atomically promoting runtime directory to {output_root}...")
        backup_dir = parent_dir / f"retrieval_data_v1.old-{build_id}"
        if output_root.exists():
            output_root.rename(backup_dir)

        tmp_dir.rename(output_root)

        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        print(f"=== BUILD COMPLETED SUCCESSFULLY IN {build_duration:.2f}s ===")
        return build_manifest
