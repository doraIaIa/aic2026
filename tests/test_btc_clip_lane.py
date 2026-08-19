import json
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest

from aic2026.retrieval.providers.base import ProviderQuery, ProviderUnavailableError, ProviderIntegrityError
from aic2026.retrieval.providers.btc_clip import (
    BtcClipProvider,
    BTC_CLIP_MODEL_NAME,
    BTC_CLIP_PRETRAINED,
    BTC_CLIP_DIMENSION,
)


def _make_mock_btc_artifact(tmp_path: Path, count: int = 5) -> Path:
    art_dir = tmp_path / "clip-faiss-btc-v1"
    art_dir.mkdir(parents=True, exist_ok=True)

    metadata_lines = []
    for i in range(1, count + 1):
        vid = f"L21_V{i:03d}"
        keyframe_id = f"{vid}:1"
        from aic2026.retrieval.clip_faiss import stable_embedding_id
        emb_id = stable_embedding_id(keyframe_id)
        row = {
            "embedding_id": emb_id,
            "keyframe_id": keyframe_id,
            "video_id": vid,
            "csv_n": 1,
            "clip_row": 0,
            "frame_idx": 25,
            "pts_time": 1.0,
            "keyframe_relpath": f"data_extracted/keyframes/{vid}/001.jpg",
        }
        metadata_lines.append(json.dumps(row) + "\n")

    metadata_file = art_dir / "metadata.jsonl"
    metadata_file.write_text("".join(metadata_lines), encoding="utf-8")

    index_file = art_dir / "clip.index"
    index_file.write_bytes(b"mock_index_binary_data")

    from aic2026.core.hashing import sha256_file
    done = {
        "schema_version": 1,
        "task": "clip_faiss_index",
        "expected_count": count,
        "processed_count": count,
        "vector_dim": 512,
        "metric": "cosine_via_normalized_inner_product",
        "index_file": "clip.index",
        "index_sha256": sha256_file(index_file),
        "metadata_file": "metadata.jsonl",
        "metadata_sha256": sha256_file(metadata_file),
    }
    (art_dir / "DONE.json").write_text(json.dumps(done), encoding="utf-8")
    return art_dir


class MockFaissIndex:
    def __init__(self, ntotal: int = 5, d: int = 512):
        self.ntotal = ntotal
        self.d = d

    def search(self, query: np.ndarray, k: int):
        from aic2026.retrieval.clip_faiss import stable_embedding_id
        # Return mock IDs corresponding to L21_V001..
        ids = np.asarray([[stable_embedding_id(f"L21_V{i:03d}:1") for i in range(1, min(k, self.ntotal) + 1)]], dtype=np.int64)
        scores = np.asarray([[0.8 - i * 0.05 for i in range(ids.shape[1])]], dtype=np.float32)
        return scores, ids


def _mock_encoder_loader():
    def encode(text: str) -> np.ndarray:
        v = np.ones(512, dtype=np.float32)
        return v / np.linalg.norm(v)
    
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    return mock_model, mock_tokenizer


def test_btc_clip_contract_constants():
    assert BTC_CLIP_MODEL_NAME == "ViT-B-32"
    assert BTC_CLIP_PRETRAINED == "openai"
    assert BTC_CLIP_DIMENSION == 512


def test_btc_clip_provider_initialization_and_health(tmp_path: Path):
    art_dir = _make_mock_btc_artifact(tmp_path, count=3)

    provider = BtcClipProvider(
        art_dir,
        model_loader=_mock_encoder_loader,
        index_loader=lambda p: MockFaissIndex(ntotal=3, d=512),
    )

    # Mock encoder method
    provider.encode_text = lambda t: np.ones(512, dtype=np.float32) / np.sqrt(512)

    health = provider.health()
    assert health["status"] == "OK"
    assert health["lane_id"] == "btc_clip"
    assert health["frame_space"] == "BTC"
    assert health["index_rows"] == 3
    assert health["dimension"] == 512
    assert health["model_name"] == "ViT-B-32"
    assert health["pretrained"] == "openai"


def test_btc_clip_search_returns_canonical_btc_hits(tmp_path: Path):
    art_dir = _make_mock_btc_artifact(tmp_path, count=5)

    provider = BtcClipProvider(
        art_dir,
        model_loader=_mock_encoder_loader,
        index_loader=lambda p: MockFaissIndex(ntotal=5, d=512),
    )
    provider.encode_text = lambda t: np.ones(512, dtype=np.float32) / np.sqrt(512)

    hits = provider.search("múa lân", top_k=3)
    assert len(hits) == 3

    # Validate canonical BTC provenance and structure
    for i, h in enumerate(hits, 1):
        assert h.provider == "btc_clip"
        assert h.rank == i
        assert h.evidence_id.startswith("BTC:L21_V")
        assert ":KF000001" in h.evidence_id
        assert h.payload["frame_space"] == "BTC"
        assert h.payload["lane"] == "btc_clip"
        assert h.payload["csv_n"] == 1
        assert h.score_kind == "cosine_ip_higher_is_better"
        assert isinstance(h.raw_score, float)


def test_btc_clip_candidate_scope_filtering(tmp_path: Path):
    art_dir = _make_mock_btc_artifact(tmp_path, count=5)

    provider = BtcClipProvider(
        art_dir,
        model_loader=_mock_encoder_loader,
        index_loader=lambda p: MockFaissIndex(ntotal=5, d=512),
    )
    provider.encode_text = lambda t: np.ones(512, dtype=np.float32) / np.sqrt(512)

    # Filter to only L21_V002
    hits = provider.search("test", top_k=5, candidate_video_ids=["L21_V002"])
    assert len(hits) == 1
    assert hits[0].video_id == "L21_V002"

    # Filter to empty set
    empty_hits = provider.search("test", top_k=5, candidate_video_ids=[])
    assert len(empty_hits) == 0

    # Filter to non-existent video
    none_hits = provider.search("test", top_k=5, candidate_video_ids=["L99_V999"])
    assert len(none_hits) == 0


def test_btc_clip_rejects_empty_query(tmp_path: Path):
    art_dir = _make_mock_btc_artifact(tmp_path, count=3)
    provider = BtcClipProvider(art_dir)
    with pytest.raises(ValueError, match="Query text cannot be empty"):
        provider.search("   ")


def test_btc_clip_checksum_mismatch_fails_closed(tmp_path: Path):
    art_dir = _make_mock_btc_artifact(tmp_path, count=3)
    # Corrupt index file
    (art_dir / "clip.index").write_bytes(b"corrupted_bytes")

    provider = BtcClipProvider(art_dir)
    health = provider.health()
    assert health["status"] in ("ERROR", "UNAVAILABLE")
