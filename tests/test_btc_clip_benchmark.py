import json
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np

from aic2026.evaluation.btc_clip_benchmark import run_btc_clip_benchmark
from aic2026.retrieval.providers.base import ProviderHit


def test_btc_clip_benchmark_produces_valid_manifests(tmp_path: Path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    queries = [
        {"query_id": "q1", "query_text": "múa lân", "split": "DEV", "query_type": "KIS"},
        {"query_id": "q2", "query_text": "người đi xe đạp", "split": "DEV", "query_type": "KIS"},
    ]
    manifest_file = dataset_dir / "query_manifest.jsonl"
    manifest_file.write_text("".join(json.dumps(q) + "\n" for q in queries), encoding="utf-8")

    out_dir = tmp_path / "out"

    # Mock provider
    from aic2026.retrieval.providers.btc_clip import BtcClipProvider
    orig_search = BtcClipProvider.search
    orig_ensure = BtcClipProvider._ensure_loaded

    def mock_search(self, query, **kwargs):
        return [
            ProviderHit(
                provider="btc_clip",
                evidence_id="BTC:L21_V001:KF000001",
                video_id="L21_V001",
                rank=1,
                start_sec=1.0,
                end_sec=1.0,
                anchor_sec=1.0,
                raw_score=0.35,
                score_kind="cosine_ip_higher_is_better",
                artifact_version="clip-faiss-btc-v1",
                source_video_relpath=None,
                payload={"keyframe_uid": "BTC:L21_V001:KF000001", "frame_idx": 25, "csv_n": 1, "timestamp_ms": 1000},
                provenance={},
            )
        ]

    # Mock artifact dir
    art_dir = tmp_path / "art"
    art_dir.mkdir()
    (art_dir / "DONE.json").write_text(json.dumps({
        "processed_count": 100,
        "index_sha256": "fake_hash",
        "metadata_sha256": "fake_hash",
    }))

    BtcClipProvider.search = mock_search
    BtcClipProvider._ensure_loaded = lambda self: None

    try:
        summary = run_btc_clip_benchmark(
            index_dir=art_dir,
            dataset_dir=dataset_dir,
            output_dir=out_dir,
            split="DEV",
            top_k=5,
            device="cpu",
        )

        assert summary["query_count"] == 2
        assert summary["lane"] == "btc_clip"
        assert summary["scoring"]["quality_status"] == "BLOCKED_BY_GROUND_TRUTH"
        assert summary["scoring"]["unscored_queries"] == 2
        assert summary["scoring"]["scored_queries"] == 0

        assert (out_dir / "DONE.json").is_file()
        assert (out_dir / "summary.json").is_file()
        assert (out_dir / "summary.md").is_file()
        assert (out_dir / "per_query.jsonl").is_file()
    finally:
        BtcClipProvider.search = orig_search
        BtcClipProvider._ensure_loaded = orig_ensure
