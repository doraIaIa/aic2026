from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class BtcDataPaths:
    keyframes_dir: Path
    map_keyframes_dir: Path
    clip_features_dir: Path
    objects_dir: Path
    video_dir: Path
    media_info_zip: Path


@dataclass(frozen=True)
class CustomDataPaths:
    keyframes_dir: Path
    map_keyframes_dir: Path
    qwen_captions_shard: Path
    video_metadata_csv: Path


@dataclass(frozen=True)
class AsrDataPaths:
    master_segments_file: Path
    master_videos_file: Path
    final_backup_dir: Path
    total_videos: int
    total_segments: int


@dataclass(frozen=True)
class OcrDataPaths:
    manifest_v1: Path
    selected_frames_count: int
    shards_folder_name: str


@dataclass(frozen=True)
class EvaluationPaths:
    internal_verified_dev15_dir: Path
    group_a_review_dir: Path


class DataRegistry:
    """Single-Source-of-Truth Data Paths Registry for AIC 2026."""

    _instance: DataRegistry | None = None

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "data_paths.json"
        
        self.config_path = config_path
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._raw: Dict[str, Any] = json.load(f)
        else:
            self._raw = {}

        roots = self._raw.get("roots", {})
        self.btc_drive_root = Path(roots.get("btc_drive_root", r"G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026"))
        self.local_artifacts_root = Path(roots.get("local_artifacts_root", r"F:\AIC_WORK\artifacts"))
        self.local_dev_root = Path(roots.get("local_dev_root", r"F:\AIC_DEV\aic2026"))

        # 1. BTC Data
        btc = self._raw.get("btc_provided_data", {})
        self.btc = BtcDataPaths(
            keyframes_dir=Path(btc.get("keyframes_dir", self.btc_drive_root / "data_extracted" / "keyframes")),
            map_keyframes_dir=Path(btc.get("map_keyframes_dir", self.btc_drive_root / "data_extracted" / "map-keyframes")),
            clip_features_dir=Path(btc.get("clip_features_dir", self.btc_drive_root / "data_extracted" / "clip-features-32")),
            objects_dir=Path(btc.get("objects_dir", self.btc_drive_root / "data_extracted" / "objects")),
            video_dir=Path(btc.get("video_dir", self.btc_drive_root / "data_extracted" / "video")),
            media_info_zip=Path(btc.get("media_info_zip", self.btc_drive_root / "data" / "media-info-aic25-b1.zip")),
        )

        # 2. Custom Data
        custom = self._raw.get("custom_enriched_data", {})
        self.custom = CustomDataPaths(
            keyframes_dir=Path(custom.get("keyframes_dir", self.btc_drive_root / "output" / "keyframes")),
            map_keyframes_dir=Path(custom.get("map_keyframes_dir", self.btc_drive_root / "output" / "map_keyframes")),
            qwen_captions_shard=Path(custom.get("qwen_captions_shard", self.btc_drive_root / "output_llm" / "shard_000.jsonl")),
            video_metadata_csv=Path(custom.get("video_metadata_csv", self.btc_drive_root / "output" / "video_metadata.csv")),
        )

        # 3. ASR Data
        asr = self._raw.get("asr_voice_data", {})
        self.asr = AsrDataPaths(
            master_segments_file=Path(asr.get("master_segments_file", self.local_artifacts_root / "asr" / "whisper-medium-vi-full-v1-colab-merged" / "asr_segments.jsonl")),
            master_videos_file=Path(asr.get("master_videos_file", self.local_artifacts_root / "asr" / "whisper-medium-vi-full-v1-colab-merged" / "asr_videos.jsonl")),
            final_backup_dir=Path(asr.get("final_backup_dir", self.local_artifacts_root / "asr" / "whisper-medium-vi-full-873-final")),
            total_videos=asr.get("total_videos", 873),
            total_segments=asr.get("total_segments", 107540),
        )

        # 4. OCR Data
        ocr = self._raw.get("ocr_text_data", {})
        self.ocr = OcrDataPaths(
            manifest_v1=Path(ocr.get("manifest_v1", self.local_artifacts_root / "ocr" / "ocr-corpus-v1" / "manifest.jsonl")),
            selected_frames_count=ocr.get("selected_frames_count", 138791),
            shards_folder_name=ocr.get("shards_folder_name", "ocr_single_text_retrieval"),
        )

        # 5. Evaluation Data
        ev = self._raw.get("evaluation_benchmarks", {})
        self.evaluation = EvaluationPaths(
            internal_verified_dev15_dir=Path(ev.get("internal_verified_dev15_dir", self.local_artifacts_root / "evaluation" / "internal-verified-v1")),
            group_a_review_dir=Path(ev.get("group_a_review_dir", self.local_artifacts_root / "evaluation" / "group-a-review-v1")),
        )

    @classmethod
    def get_instance(cls) -> DataRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Global convenience singleton
DATA_REGISTRY = DataRegistry.get_instance()
