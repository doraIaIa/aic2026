import json
from pathlib import Path
import numpy as np

from aic2026.evaluation.visual_pair_benchmark import run_visual_pair_benchmark
from aic2026.retrieval.providers.base import ProviderHit
from aic2026.retrieval.providers.btc_clip import BtcClipProvider
from aic2026.retrieval.providers.siglip import SigLIPProvider


def test_visual_pair_benchmark_computes_diversity_correctly(tmp_path: Path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    queries = [
        {"query_id": "q1", "query_text": "múa lân", "split": "DEV", "query_type": "KIS"},
    ]
    manifest_file = dataset_dir / "query_manifest.jsonl"
    manifest_file.write_text("".join(json.dumps(q) + "\n" for q in queries), encoding="utf-8")

    out_dir = tmp_path / "out"

    # Mock SigLIP provider returning L21_V001, L21_V002
    def mock_siglip_search(self, query, **kwargs):
        return [
            ProviderHit("siglip_custom", "CUSTOM:L21_V001:F100", "L21_V001", 1, 1.0, 1.0, 1.0, 0.2, "cosine", "v1", None, {}, {}),
            ProviderHit("siglip_custom", "CUSTOM:L21_V002:F200", "L21_V002", 2, 2.0, 2.0, 2.0, 0.18, "cosine", "v1", None, {}, {}),
        ]

    # Mock BTC CLIP provider returning L21_V002, L21_V003
    def mock_btc_search(self, query, **kwargs):
        return [
            ProviderHit("btc_clip", "BTC:L21_V002:KF000001", "L21_V002", 1, 2.0, 2.0, 2.0, 0.35, "cosine", "v1", None, {}, {}),
            ProviderHit("btc_clip", "BTC:L21_V003:KF000001", "L21_V003", 2, 3.0, 3.0, 3.0, 0.30, "cosine", "v1", None, {}, {}),
        ]

    orig_siglip_search = SigLIPProvider.search
    orig_siglip_ensure = SigLIPProvider._ensure_loaded
    orig_btc_search = BtcClipProvider.search
    orig_btc_ensure = BtcClipProvider._ensure_loaded

    SigLIPProvider.search = mock_siglip_search
    SigLIPProvider._ensure_loaded = lambda self: None
    BtcClipProvider.search = mock_btc_search
    BtcClipProvider._ensure_loaded = lambda self: None

    siglip_dir = tmp_path / "siglip"
    siglip_dir.mkdir()
    btc_dir = tmp_path / "btc"
    btc_dir.mkdir()

    try:
        summary = run_visual_pair_benchmark(
            siglip_index_dir=siglip_dir,
            btc_index_dir=btc_dir,
            dataset_dir=dataset_dir,
            output_dir=out_dir,
            split="DEV",
            top_k=2,
            device="cpu",
        )

        assert summary["query_count"] == 1
        assert summary["comparison_type"] == "CANDIDATE_OVERLAP_DIVERSITY"

        div = summary["candidate_overlap_diversity"]
        # siglip: {L21_V001, L21_V002}, btc: {L21_V002, L21_V003}
        # shared: {L21_V002} -> 1, siglip_only: {L21_V001} -> 1, btc_only: {L21_V003} -> 1
        # union: 3 -> Jaccard = 1/3 = 0.3333
        assert div["mean_shared_candidate_videos"] == 1.0
        assert div["mean_siglip_only_candidate_videos"] == 1.0
        assert div["mean_btc_only_candidate_videos"] == 1.0
        assert abs(div["mean_video_set_jaccard"] - 0.3333) < 1e-3

        assert (out_dir / "DONE.json").is_file()
        assert (out_dir / "summary.json").is_file()
        assert (out_dir / "summary.md").is_file()
        assert (out_dir / "per_query.jsonl").is_file()
    finally:
        SigLIPProvider.search = orig_siglip_search
        SigLIPProvider._ensure_loaded = orig_siglip_ensure
        BtcClipProvider.search = orig_btc_search
        BtcClipProvider._ensure_loaded = orig_btc_ensure
