import json
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest

from aic2026.retrieval.providers.base import ProviderQuery, ProviderUnavailableError
from aic2026.retrieval.providers.asr_bge import (
    AsrBgeProvider,
    BGE_MODEL_ID,
    BGE_DENSE_DIMENSION,
    CANONICAL_ASR_TOTAL,
    CANONICAL_ZERO_ASR_VIDEOS,
)


def _make_mock_asr_bge_artifact(tmp_path: Path, count: int = 5) -> Path:
    art_dir = tmp_path / "asr_bge_v1"
    art_dir.mkdir(parents=True, exist_ok=True)

    rowmap_lines = []
    for i in range(count):
        vid = f"L21_V{i+1:03d}"
        row = {
            "global_row": i,
            "segment_uid": f"ASR:{vid}:{i+1}",
            "source_segment_id": f"{i+1}",
            "video_id": vid,
            "video_ordinal": i,
            "start_ms": i * 1000,
            "end_ms": (i + 2) * 1000,
            "start_sec": float(i),
            "end_sec": float(i + 2),
            "text": f"Mẫu văn bản thử nghiệm {i+1}",
            "language": "vi",
            "model": "whisper-medium",
        }
        rowmap_lines.append(json.dumps(row) + "\n")

    rowmap_file = art_dir / "asr_bge_rowmap.jsonl"
    rowmap_file.write_text("".join(rowmap_lines), encoding="utf-8")

    faiss_file = art_dir / "asr_bge.faiss"
    faiss_file.write_bytes(b"mock_faiss_data")

    from aic2026.core.hashing import sha256_file
    passport = {
        "index_id": "asr_bge_v1",
        "lane_id": "asr_bge",
        "model_id": BGE_MODEL_ID,
        "dimension": BGE_DENSE_DIMENSION,
        "canonical_segment_count": count,
        "index_rows": count,
        "index_sha256": sha256_file(faiss_file),
        "rowmap_sha256": sha256_file(rowmap_file),
    }
    (art_dir / "asr_bge_passport.json").write_text(json.dumps(passport), encoding="utf-8")
    (art_dir / "DONE.json").write_text(json.dumps({"status": "PASS", "total_rows": count}), encoding="utf-8")
    return art_dir


def _mock_bge_model_loader():
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    return mock_model, mock_tokenizer


def test_asr_bge_contract_constants():
    assert BGE_MODEL_ID == "BAAI/bge-m3"
    assert BGE_DENSE_DIMENSION == 1024
    assert CANONICAL_ASR_TOTAL == 107540
    assert CANONICAL_ZERO_ASR_VIDEOS == 14


def test_asr_bge_provider_missing_artifact(tmp_path: Path):
    missing_dir = tmp_path / "non_existent_bge"
    provider = AsrBgeProvider(missing_dir)
    h = provider.health()
    assert h["status"] == "UNAVAILABLE"


def test_asr_bge_empty_query():
    with pytest.raises(ValueError):
        ProviderQuery(query_text="", top_k=10)
    with pytest.raises(ValueError):
        ProviderQuery(query_text="   ", top_k=10)
