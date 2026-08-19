from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import pytest

from aic2026.data_hub.index_registry_models import (
    ArtifactRegistryRecord,
    VectorIndexRecord,
)
from aic2026.data_hub.runtime_hub import RuntimeDataHub
from aic2026.data_hub.text_normalizer import TextNormalizer


def test_text_normalizer_vietnamese():
    raw = "  Chào Mừng   Bạn Đến Với Cuộc Thi AIC 2026!  "
    norm = TextNormalizer.normalize_text(raw)
    assert norm == "Chào Mừng Bạn Đến Với Cuộc Thi AIC 2026!"

    acc = TextNormalizer.strip_accents(raw)
    assert acc == "Chao Mung Ban Den Voi Cuoc Thi AIC 2026!"

    # Special Vietnamese characters
    assert TextNormalizer.strip_accents("Đà Nẵng, Phở Bò, Ếch Xào Xả Ớt") == "Da Nang, Pho Bo, Ech Xao Xa Ot"


def test_schema_foreign_keys_and_rejections(tmp_path: Path):
    db_path = tmp_path / "test_mapping.sqlite"
    schema_path = Path(__file__).resolve().parent.parent / "src" / "aic2026" / "db" / "schema.sql"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    c = conn.cursor()

    # 1. Insert a video
    c.execute(
        """
        INSERT INTO videos(video_id, ordinal, ordinal_space_id, series, relpath)
        VALUES ('L21_V001', 0, 'v1_natural_series_video', 'L21', 'videos/L21/L21_V001.mp4')
        """
    )
    conn.commit()

    # 2. Duplicate PK fails
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(
            """
            INSERT INTO videos(video_id, ordinal, ordinal_space_id, series, relpath)
            VALUES ('L21_V001', 1, 'v1_natural_series_video', 'L21', 'videos/L21/L21_V001_dup.mp4')
            """
        )

    # 3. Custom keyframe referring to non-existent video fails
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(
            """
            INSERT INTO custom_keyframes(
                keyframe_uid, video_id, video_ordinal, frame_idx, timestamp_ms, raw_pts_time, file_name, image_relpath
            ) VALUES ('CUSTOM:UNKNOWN:F0001', 'UNKNOWN_VIDEO', 99, 1, 1000, 1.0, '0001.jpg', 'img/0001.jpg')
            """
        )

    # 4. Valid custom keyframe succeeds
    c.execute(
        """
        INSERT INTO custom_keyframes(
            keyframe_uid, video_id, video_ordinal, frame_idx, timestamp_ms, raw_pts_time, file_name, image_relpath
        ) VALUES ('CUSTOM:L21_V001:F0001', 'L21_V001', 0, 1, 1000, 1.0, '0001.jpg', 'img/0001.jpg')
        """
    )

    # 5. BTC keyframe with proper namespace succeeds
    c.execute(
        """
        INSERT INTO btc_keyframes(
            keyframe_uid, video_id, video_ordinal, local_keyframe_no, frame_idx, timestamp_ms, raw_pts_time, fps, image_relpath
        ) VALUES ('BTC:L21_V001:KF000001', 'L21_V001', 0, 1, 1, 1000, 1.0, 25.0, 'img/btc0001.jpg')
        """
    )
    conn.commit()

    # Check integrity
    c.execute("PRAGMA integrity_check;")
    assert c.fetchone()[0] == "ok"

    c.execute("PRAGMA foreign_key_check;")
    assert len(c.fetchall()) == 0
    conn.close()


def test_fts5_modality_separation(tmp_path: Path):
    db_path = tmp_path / "test_fts.sqlite"
    schema_path = Path(__file__).resolve().parent.parent / "src" / "aic2026" / "db" / "schema.sql"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    c = conn.cursor()

    # Setup video, custom keyframe, ASR segment
    c.execute("INSERT INTO videos(video_id, ordinal, series, relpath) VALUES ('L21_V001', 0, 'L21', 'v.mp4')")
    c.execute(
        """
        INSERT INTO canonical_asr_segments(
            segment_uid, source_segment_id, video_id, video_ordinal, start_ms, end_ms, start_sec, end_sec, text_raw, text_norm
        ) VALUES ('ASR:L21_V001:0001', '0001', 'L21_V001', 0, 0, 5000, 0.0, 5.0, 'Bản tin 60 giây chiều nay', 'Bản tin 60 giây chiều nay')
        """
    )
    c.execute(
        """
        INSERT INTO asr_fts(segment_uid, video_id, text_raw, text_norm, text_accentless)
        VALUES ('ASR:L21_V001:0001', 'L21_V001', 'Bản tin 60 giây chiều nay', 'Bản tin 60 giây chiều nay', 'Ban tin 60 giay chieu nay')
        """
    )

    # Insert OCR
    c.execute(
        """
        INSERT INTO custom_keyframes(keyframe_uid, video_id, video_ordinal, frame_idx, timestamp_ms, raw_pts_time, file_name, image_relpath)
        VALUES ('CUSTOM:L21_V001:F0001', 'L21_V001', 0, 1, 1000, 1.0, '1.jpg', 'img/1.jpg')
        """
    )
    c.execute(
        """
        INSERT INTO ocr_keyframes(keyframe_uid, video_id, video_ordinal, frame_idx, timestamp_ms, raw_pts_time, file_name, image_relpath)
        VALUES ('CUSTOM:L21_V001:F0001', 'L21_V001', 0, 1, 1000, 1.0, '1.jpg', 'img/1.jpg')
        """
    )
    c.execute(
        """
        INSERT INTO ocr_items(ocr_uid, video_id, video_ordinal, keyframe_uid, frame_idx, timestamp_ms, raw_pts_time, local_text_index, text_raw, text_norm)
        VALUES ('OCR:CUSTOM:L21_V001:F0001:T0000', 'L21_V001', 0, 'CUSTOM:L21_V001:F0001', 1, 1000, 1.0, 0, 'BỆNH VIỆN CHỢ RẪY', 'BỆNH VIỆN CHỢ RẪY')
        """
    )
    c.execute(
        """
        INSERT INTO ocr_fts(ocr_uid, keyframe_uid, video_id, text_raw, text_norm, text_accentless)
        VALUES ('OCR:CUSTOM:L21_V001:F0001:T0000', 'CUSTOM:L21_V001:F0001', 'L21_V001', 'BỆNH VIỆN CHỢ RẪY', 'BỆNH VIỆN CHỢ RẪY', 'BENH VIEN CHO RAY')
        """
    )

    # Insert Qwen
    c.execute(
        """
        INSERT INTO qwen_frames(keyframe_uid, video_id, frame_idx, timestamp_ms, raw_pts_time, caption)
        VALUES ('CUSTOM:L21_V001:F0001', 'L21_V001', 1, 1000, 1.0, 'Bác sĩ đang khám cho bệnh nhân trong bệnh viện')
        """
    )
    c.execute(
        """
        INSERT INTO qwen_caption_fts(keyframe_uid, video_id, caption_raw, caption_norm, caption_accentless)
        VALUES ('CUSTOM:L21_V001:F0001', 'L21_V001', 'Bác sĩ đang khám cho bệnh nhân trong bệnh viện', 'Bác sĩ đang khám cho bệnh nhân trong bệnh viện', 'Bac si dang kham cho benh nhan trong benh vien')
        """
    )

    # Insert Media
    c.execute(
        """
        INSERT INTO media_info(video_id, video_ordinal, title)
        VALUES ('L21_V001', 0, 'Tin tức thời sự HTV 60 Giây')
        """
    )
    c.execute(
        """
        INSERT INTO media_fts(video_id, title_raw, title_norm, title_accentless, keywords, description)
        VALUES ('L21_V001', 'Tin tức thời sự HTV 60 Giây', 'Tin tức thời sự HTV 60 Giây', 'Tin tuc thoi su HTV 60 Giay', '', '')
        """
    )
    conn.commit()
    conn.close()

    # Query with RuntimeDataHub
    hub = RuntimeDataHub(db_path)

    # ASR FTS query
    asr_hits = hub.search_asr_fts("60 giây")
    assert len(asr_hits) == 1
    assert asr_hits[0]["segment_uid"] == "ASR:L21_V001:0001"

    # Accentless query works
    asr_hits_acc = hub.search_asr_fts("chieu nay")
    assert len(asr_hits_acc) == 1

    # OCR FTS query
    ocr_hits = hub.search_ocr_fts("Chợ Rẫy")
    assert len(ocr_hits) == 1
    assert ocr_hits[0]["ocr_uid"] == "OCR:CUSTOM:L21_V001:F0001:T0000"

    # Qwen FTS query
    qwen_hits = hub.search_qwen_fts("bác sĩ khám")
    assert len(qwen_hits) == 1
    assert qwen_hits[0]["keyframe_uid"] == "CUSTOM:L21_V001:F0001"

    # Media FTS query
    media_hits = hub.search_media_fts("HTV")
    assert len(media_hits) == 1
    assert media_hits[0]["video_id"] == "L21_V001"

    # Core repository lookups
    v = hub.get_video("L21_V001")
    assert v is not None
    assert v["video_id"] == "L21_V001"

    kf_c = hub.get_keyframe("CUSTOM:L21_V001:F0001")
    assert kf_c is not None
    assert kf_c["frame_idx"] == 1

    qwen = hub.get_qwen("CUSTOM:L21_V001:F0001")
    assert qwen is not None
    assert "bệnh viện" in qwen["caption"]

    ocr_items = hub.get_ocr_for_keyframe("CUSTOM:L21_V001:F0001")
    assert len(ocr_items) == 1
    assert ocr_items[0]["text_raw"] == "BỆNH VIỆN CHỢ RẪY"

    ocr_near = hub.get_ocr_near("L21_V001", timestamp_ms=1000, window_ms=5000)
    assert len(ocr_near) == 1

    asr_near = hub.get_asr_near("L21_V001", timestamp_ms=2500, window_ms=5000)
    assert len(asr_near) == 1

    media = hub.get_media_info("L21_V001")
    assert media is not None
    assert media["title"] == "Tin tức thời sự HTV 60 Giây"

    hub.close()


def test_vector_index_models_and_validation():
    # Valid BTC CLIP Raw
    v_raw = VectorIndexRecord(
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
    )
    assert v_raw.dimension == 512
    assert v_raw.row_count == 177321

    # Valid BGE Sharded without FAISS
    v_bge = VectorIndexRecord(
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
    )
    assert v_bge.status == "EMBEDDINGS_READY_INDEX_NOT_BUILT"
    assert v_bge.dimension == 1024

    # Valid SigLIP2 Raw
    v_siglip = VectorIndexRecord(
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
    )
    assert v_siglip.dimension == 768
    assert v_siglip.row_count == 116767
    assert v_siglip.frame_space == "CUSTOM"


def test_empty_qwen_caption_no_fake_tokens(tmp_path: Path):
    db_path = tmp_path / "test_empty_qwen.sqlite"
    schema_path = Path(__file__).resolve().parent.parent / "src" / "aic2026" / "db" / "schema.sql"

    conn = sqlite3.connect(str(db_path))
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    c = conn.cursor()
    c.execute("INSERT INTO videos(video_id, ordinal, series, relpath) VALUES ('L21_V001', 0, 'L21', 'v.mp4')")
    c.execute(
        """
        INSERT INTO custom_keyframes(keyframe_uid, video_id, video_ordinal, frame_idx, timestamp_ms, raw_pts_time, file_name, image_relpath)
        VALUES ('CUSTOM:L21_V001:F0001', 'L21_V001', 0, 1, 1000, 1.0, '1.jpg', 'img/1.jpg')
        """
    )
    # Empty caption inserted
    c.execute(
        """
        INSERT INTO qwen_frames(keyframe_uid, video_id, frame_idx, timestamp_ms, raw_pts_time, caption)
        VALUES ('CUSTOM:L21_V001:F0001', 'L21_V001', 1, 1000, 1.0, '')
        """
    )
    c.execute(
        """
        INSERT INTO qwen_caption_fts(keyframe_uid, video_id, caption_raw, caption_norm, caption_accentless)
        VALUES ('CUSTOM:L21_V001:F0001', 'L21_V001', '', '', '')
        """
    )
    conn.commit()
    conn.close()

    hub = RuntimeDataHub(db_path)
    res = hub.search_qwen_fts("anything")
    assert len(res) == 0
    hub.close()

