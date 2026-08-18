from __future__ import annotations

from pathlib import Path
from aic2026.core.data_registry import DATA_REGISTRY, DataRegistry


def test_data_registry_initialization():
    assert DATA_REGISTRY is not None
    assert DATA_REGISTRY.asr.total_videos == 873
    assert DATA_REGISTRY.asr.total_segments == 107540
    assert DATA_REGISTRY.asr.master_segments_file.name == "asr_segments.jsonl"
    assert DATA_REGISTRY.asr.master_videos_file.name == "asr_videos.jsonl"
    assert DATA_REGISTRY.custom.qwen_captions_shard.name == "shard_000.jsonl"


def test_data_registry_local_files_exist():
    # Verify critical master files exist on local disk
    assert DATA_REGISTRY.asr.master_segments_file.exists()
    assert DATA_REGISTRY.asr.master_videos_file.exists()
    assert DATA_REGISTRY.ocr.manifest_v1.exists()
