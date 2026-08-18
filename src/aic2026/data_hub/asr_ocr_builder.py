from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aic2026.data_hub.asr_ocr_models import (
    AsrOcrValidationResult,
    AsrSegmentRecord,
    AsrVideoCoverageRecord,
    OcrBgeRowmapRecord,
    OcrItemRecord,
    OcrKeyframeCoverageRecord,
)
from aic2026.data_hub.asr_ocr_validator import AsrOcrValidator
from aic2026.data_hub.custom_registry import CustomKeyframeRegistry
from aic2026.data_hub.video_registry import VideoRegistry


def normalize_canonical_text(text: str) -> str:
    """Safe deterministic text normalization (NFC unicode + collapsed whitespace)."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", norm).strip()


class AsrOcrCatalogBuilder:
    """Materializes canonical ASR speech intervals, OCR keyframe evidence, and BGE-M3 row mappings."""

    def __init__(
        self,
        video_registry: VideoRegistry,
        custom_registry: CustomKeyframeRegistry,
        validator: Optional[AsrOcrValidator] = None,
    ) -> None:
        self.video_registry = video_registry
        self.custom_registry = custom_registry
        self.validator = validator or AsrOcrValidator(
            video_registry=video_registry,
            custom_registry=custom_registry,
        )

    def build_asr_catalog(
        self,
        asr_videos_path: Path,
        asr_segments_path: Path,
    ) -> Tuple[List[AsrVideoCoverageRecord], List[AsrSegmentRecord]]:
        """Parse raw merged ASR files and build normalized canonical ASR records."""
        asr_videos_path = Path(asr_videos_path)
        asr_segments_path = Path(asr_segments_path)

        if not asr_videos_path.exists():
            raise FileNotFoundError(f"ASR master videos file not found: {asr_videos_path}")
        if not asr_segments_path.exists():
            raise FileNotFoundError(f"ASR master segments file not found: {asr_segments_path}")

        # 1. Parse ASR videos manifest
        video_manifest_map: Dict[str, Dict[str, Any]] = {}
        with open(asr_videos_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                v_data = json.loads(line)
                vid = v_data["video_id"]
                video_manifest_map[vid] = v_data

        # Build AsrVideoCoverageRecord for all 873 corpus videos
        coverage_records: List[AsrVideoCoverageRecord] = []
        for v_meta in self.video_registry.iter_videos():
            vid = v_meta.video_id
            v_raw = video_manifest_map.get(vid)
            if v_raw is None:
                # Video not present in ASR manifest -> Zero segments
                seg_count = 0
                dur_sec = float(v_meta.duration_ms) / 1000.0 if v_meta.duration_ms else 0.0
                dur_ms = v_meta.duration_ms if v_meta.duration_ms else 0
            else:
                seg_count = int(v_raw.get("segment_count", 0))
                dur_sec = float(v_raw.get("duration_sec", 0.0))
                dur_ms = int(round(dur_sec * 1000))

            status = "HAS_SEGMENTS" if seg_count > 0 else "ZERO_ASR_SEGMENTS"

            coverage_records.append(
                AsrVideoCoverageRecord(
                    video_id=vid,
                    video_ordinal=v_meta.ordinal,
                    ordinal_space_id=v_meta.ordinal_space_id,
                    segment_count=seg_count,
                    duration_sec=dur_sec,
                    duration_ms=dur_ms,
                    asr_status=status,
                    source_id="asr_whisper_medium_vi_full_v1",
                )
            )

        # 2. Parse ASR segments
        segment_records: List[AsrSegmentRecord] = []
        with open(asr_segments_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                if line_no == 1 and not line.startswith("{"):
                    idx = line.find("{")
                    if idx != -1:
                        line = line[idx:]

                s_data = json.loads(line)
                vid = s_data["video_id"]
                v_meta = self.video_registry.get_video(vid)
                if v_meta is None:
                    v_ordinal = -1
                    v_space = "unknown"
                else:
                    v_ordinal = v_meta.ordinal
                    v_space = v_meta.ordinal_space_id

                src_seg_id = s_data.get("segment_id", f"{vid}:{line_no:06d}")
                # Canonical UID: Namespaced ASR:{video_id}:{source_segment_id}
                canonical_uid = f"ASR:{vid}:{src_seg_id}" if not src_seg_id.startswith("ASR:") else src_seg_id

                start_sec = float(s_data.get("start_sec", s_data.get("start", 0.0)))
                end_sec = float(s_data.get("end_sec", s_data.get("end", 0.0)))
                start_ms = int(round(start_sec * 1000))
                end_ms = int(round(end_sec * 1000))

                text_raw = str(s_data.get("text", ""))
                text_norm = normalize_canonical_text(text_raw)

                segment_records.append(
                    AsrSegmentRecord(
                        segment_uid=canonical_uid,
                        source_segment_id=src_seg_id,
                        video_id=vid,
                        video_ordinal=v_ordinal,
                        ordinal_space_id=v_space,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        start_sec=start_sec,
                        end_sec=end_sec,
                        text_raw=text_raw,
                        text_norm=text_norm,
                        language=s_data.get("language", "vi"),
                        model=s_data.get("model", "whisper-medium"),
                        avg_logprob=float(s_data["avg_logprob"]) if s_data.get("avg_logprob") is not None else None,
                        no_speech_prob=float(s_data["no_speech_prob"]) if s_data.get("no_speech_prob") is not None else None,
                        compression_ratio=float(s_data["compression_ratio"]) if s_data.get("compression_ratio") is not None else None,
                        batch_id=s_data.get("batch_id"),
                        source_file=s_data.get("source_file"),
                        source_id="asr_whisper_medium_vi_full_v1",
                        schema_version="v1",
                    )
                )

        return coverage_records, segment_records

    def build_ocr_coverage_catalog(
        self,
        ocr_manifest_path: Path,
    ) -> List[OcrKeyframeCoverageRecord]:
        """Parse OCR manifest and build canonical keyframe coverage records matching M1B CUSTOM keyframes."""
        ocr_manifest_path = Path(ocr_manifest_path)
        if not ocr_manifest_path.exists():
            raise FileNotFoundError(f"OCR manifest file not found: {ocr_manifest_path}")

        coverage_records: List[OcrKeyframeCoverageRecord] = []
        with open(ocr_manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                src = item.get("ocr_image_source", "CUSTOM")
                if src != "CUSTOM":
                    continue

                vid = item["video_id"]
                frame_idx = int(item["frame_idx"])
                pts_time = float(item["pts_time"])
                timestamp_ms = int(round(pts_time * 1000))
                file_name = item["file_name"]
                image_path = item.get("image_path", f"output/keyframes/{vid}/{file_name}")

                canonical_uid = f"CUSTOM:{vid}:F{frame_idx}"
                v_meta = self.video_registry.get_video(vid)
                v_ordinal = v_meta.ordinal if v_meta else -1

                coverage_records.append(
                    OcrKeyframeCoverageRecord(
                        keyframe_uid=canonical_uid,
                        video_id=vid,
                        video_ordinal=v_ordinal,
                        frame_idx=frame_idx,
                        timestamp_ms=timestamp_ms,
                        raw_pts_time=pts_time,
                        file_name=file_name,
                        image_relpath=image_path,
                        item_count=0,
                        source_id="ocr_custom_manifest_v1",
                    )
                )

        return coverage_records

    def materialize(
        self,
        output_dir: Path,
        asr_videos_path: Path,
        asr_segments_path: Path,
        ocr_manifest_path: Path,
        ocr_items: Optional[List[OcrItemRecord]] = None,
        bge_rowmaps: Optional[List[OcrBgeRowmapRecord]] = None,
    ) -> AsrOcrValidationResult:
        """Materialize canonical ASR and OCR datasets into output_dir with fail-closed validation."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        asr_coverage, asr_segments = self.build_asr_catalog(asr_videos_path, asr_segments_path)
        ocr_keyframes = self.build_ocr_coverage_catalog(ocr_manifest_path)

        validation = self.validator.validate(
            asr_coverage=asr_coverage,
            asr_segments=asr_segments,
            ocr_keyframes=ocr_keyframes,
            ocr_items=ocr_items,
            bge_rowmaps=bge_rowmaps,
        )

        if not validation.is_valid:
            raise ValueError(f"AsrOcr validation failed with {len(validation.errors)} errors: {validation.errors[:5]}")

        # 1. Write asr_video_coverage.jsonl
        with open(output_dir / "asr_video_coverage.jsonl", "w", encoding="utf-8") as f:
            for rec in asr_coverage:
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

        # 2. Write asr_segments_canonical.jsonl
        with open(output_dir / "asr_segments_canonical.jsonl", "w", encoding="utf-8") as f:
            for rec in asr_segments:
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

        # 3. Write asr_space.json
        asr_space = {
            "asr_space_id": "asr_whisper_medium_vi_v1",
            "video_space_id": self.video_registry.video_space_id,
            "total_videos": len(asr_coverage),
            "videos_with_segments": validation.asr_videos_with_segments,
            "zero_segment_videos": validation.asr_zero_segment_videos,
            "total_segments": len(asr_segments),
            "canonical_checksum": validation.asr_canonical_checksum,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(output_dir / "asr_space.json", "w", encoding="utf-8") as f:
            json.dump(asr_space, f, indent=2, ensure_ascii=False)

        # 4. Write ocr_keyframe_coverage.jsonl
        with open(output_dir / "ocr_keyframe_coverage.jsonl", "w", encoding="utf-8") as f:
            for rec in ocr_keyframes:
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

        # 5. Write ocr_items_canonical.jsonl
        with open(output_dir / "ocr_items_canonical.jsonl", "w", encoding="utf-8") as f:
            if ocr_items:
                for rec in ocr_items:
                    f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

        # 6. Write ocr_bge_rowmap.jsonl
        with open(output_dir / "ocr_bge_rowmap.jsonl", "w", encoding="utf-8") as f:
            if bge_rowmaps:
                for rec in bge_rowmaps:
                    f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

        # 7. Write ocr_space.json
        ocr_space = {
            "ocr_space_id": "ocr_custom_keyframes_v1",
            "frame_space": "CUSTOM",
            "custom_space_id": self.custom_registry.custom_space_id,
            "covered_keyframes": len(ocr_keyframes),
            "covered_videos": validation.ocr_covered_videos,
            "total_items": validation.ocr_item_count,
            "canonical_checksum": validation.ocr_canonical_checksum,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(output_dir / "ocr_space.json", "w", encoding="utf-8") as f:
            json.dump(ocr_space, f, indent=2, ensure_ascii=False)

        # 8. Write source_registry.jsonl
        source_records = [
            {
                "source_id": "asr_whisper_medium_vi_full_v1",
                "source_type": "ASR_SPEECH",
                "scope": "873_VIDEOS",
                "relative_path": "asr_segments_canonical.jsonl",
                "record_count": len(asr_segments),
                "checksum": validation.asr_canonical_checksum,
                "status": "CANONICAL",
            },
            {
                "source_id": "ocr_custom_manifest_v1",
                "source_type": "OCR_VISIBLE_TEXT",
                "scope": "116767_CUSTOM_KEYFRAMES",
                "relative_path": "ocr_keyframe_coverage.jsonl",
                "record_count": len(ocr_keyframes),
                "checksum": validation.ocr_canonical_checksum,
                "status": "CANONICAL",
            },
        ]
        with open(output_dir / "source_registry.jsonl", "w", encoding="utf-8") as f:
            for s in source_records:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

        # 9. Write build_manifest_m1c.json
        build_manifest = {
            "task": "M1C_ASR_OCR_MAPPING",
            "video_space_id": self.video_registry.video_space_id,
            "custom_space_id": self.custom_registry.custom_space_id,
            "asr_video_rows": validation.asr_video_count,
            "asr_segments": validation.asr_segment_count,
            "asr_videos_with_segments": validation.asr_videos_with_segments,
            "asr_zero_segment_videos": validation.asr_zero_segment_videos,
            "asr_canonical_checksum": validation.asr_canonical_checksum,
            "ocr_keyframe_coverage": validation.ocr_keyframe_count,
            "ocr_covered_videos": validation.ocr_covered_videos,
            "ocr_item_count": validation.ocr_item_count,
            "ocr_canonical_checksum": validation.ocr_canonical_checksum,
            "bge_model": "BAAI/bge-m3",
            "bge_dimension": 1024,
            "bge_normalized": True,
            "bge_vector_row_count": validation.bge_vector_row_count,
            "bge_mapped_row_count": validation.bge_mapped_row_count,
            "bge_rowmap_checksum": validation.bge_rowmap_checksum,
            "is_valid": validation.is_valid,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(output_dir / "build_manifest_m1c.json", "w", encoding="utf-8") as f:
            json.dump(build_manifest, f, indent=2, ensure_ascii=False)

        return validation
