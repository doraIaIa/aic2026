"""Paired Visual Retrieval Comparison Runner (SigLIP CUSTOM vs BTC CLIP) (M3A).

Performs operational candidate comparison between the Custom SigLIP2 lane and the
BTC CLIP lane across identical queries and Top-K values.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aic2026.core.hashing import sha256_file
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.btc_clip import BtcClipProvider
from aic2026.retrieval.providers.siglip import SigLIPProvider


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_visual_pair_benchmark(
    siglip_index_dir: str | Path,
    btc_index_dir: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 20,
    device: str = "cpu",
) -> dict[str, Any]:
    """Execute paired visual search evaluation on DEV queries."""
    siglip_dir = Path(siglip_index_dir)
    btc_dir = Path(btc_index_dir)
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load dataset queries
    manifest_path = dataset_dir / "query_manifest.jsonl"
    labels_path = dataset_dir / "labels.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing query manifest: {manifest_path}")

    queries = [json.loads(line) for line in open(manifest_path, "r", encoding="utf-8")]
    selected_queries = [q for q in queries if q.get("split", "DEV") == split]

    label_map = {}
    if labels_path.is_file():
        for line in open(labels_path, "r", encoding="utf-8"):
            l = json.loads(line)
            label_map[l["query_id"]] = l

    dataset_sha256 = sha256_file(manifest_path)

    # 2. Load both providers
    siglip_provider = SigLIPProvider(siglip_dir, device=device)
    btc_provider = BtcClipProvider(btc_dir, device=device)

    # Warmup both
    siglip_provider.search(ProviderQuery(query_text="warmup", top_k=1))
    btc_provider.search(ProviderQuery(query_text="warmup", top_k=1))

    # 3. Run comparison
    run_id = f"visual_pair_dev_{int(time.time())}"
    per_query_records: list[dict[str, Any]] = []
    siglip_latencies: list[float] = []
    btc_latencies: list[float] = []
    jaccards: list[float] = []
    siglip_only_counts: list[int] = []
    btc_only_counts: list[int] = []
    shared_counts: list[int] = []

    for q in selected_queries:
        qid = q["query_id"]
        qtext = q["query_text"]

        label = label_map.get(qid, q)
        is_verified = label.get("verification_status") == "VERIFIED"

        # SigLIP search
        t0 = time.perf_counter()
        siglip_hits = siglip_provider.search(ProviderQuery(query_text=qtext, top_k=top_k))
        siglip_elapsed = (time.perf_counter() - t0) * 1000
        siglip_latencies.append(siglip_elapsed)

        # BTC CLIP search
        t0 = time.perf_counter()
        btc_hits = btc_provider.search(ProviderQuery(query_text=qtext, top_k=top_k))
        btc_elapsed = (time.perf_counter() - t0) * 1000
        btc_latencies.append(btc_elapsed)

        siglip_vids = [h.video_id for h in siglip_hits]
        btc_vids = [h.video_id for h in btc_hits]

        siglip_set = set(siglip_vids)
        btc_set = set(btc_vids)

        shared = sorted(siglip_set & btc_set)
        siglip_only = sorted(siglip_set - btc_set)
        btc_only = sorted(btc_set - siglip_set)

        union = siglip_set | btc_set
        jaccard = len(shared) / len(union) if union else 0.0

        jaccards.append(jaccard)
        siglip_only_counts.append(len(siglip_only))
        btc_only_counts.append(len(btc_only))
        shared_counts.append(len(shared))

        per_query_records.append({
            "query_id": qid,
            "query_text": qtext,
            "top_k": top_k,
            "siglip_latency_ms": round(siglip_elapsed, 2),
            "btc_latency_ms": round(btc_elapsed, 2),
            "siglip_top1": siglip_hits[0].video_id if siglip_hits else None,
            "btc_top1": btc_hits[0].video_id if btc_hits else None,
            "siglip_top1_score": round(siglip_hits[0].raw_score, 4) if siglip_hits else None,
            "btc_top1_score": round(btc_hits[0].raw_score, 4) if btc_hits else None,
            "shared_candidate_count": len(shared),
            "siglip_only_candidate_count": len(siglip_only),
            "btc_only_candidate_count": len(btc_only),
            "jaccard_video_set": round(jaccard, 4),
            "shared_videos": shared,
            "siglip_only_videos": siglip_only,
            "btc_only_videos": btc_only,
            "quality_status": "VERIFIED" if is_verified else "BLOCKED_BY_GROUND_TRUTH",
        })

    # 4. Write per_query.jsonl
    per_query_file = output_dir / "per_query.jsonl"
    with open(per_query_file, "w", encoding="utf-8") as f:
        for rec in per_query_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 5. Build summary
    summary: dict[str, Any] = {
        "run_id": run_id,
        "comparison_type": "CANDIDATE_OVERLAP_DIVERSITY",
        "timestamp": _utc_now(),
        "dataset_split": split,
        "query_count": len(selected_queries),
        "dataset_sha256": dataset_sha256,
        "top_k": top_k,
        "siglip_lane": {
            "lane_id": "siglip_custom",
            "model": "google/siglip2-base-patch16-224",
            "frame_space": "CUSTOM",
            "vectors": 116767,
            "latency_ms": {
                "p50": round(_percentile(siglip_latencies, 50), 2),
                "p95": round(_percentile(siglip_latencies, 95), 2),
                "mean": round(float(np.mean(siglip_latencies)), 2),
            },
        },
        "btc_clip_lane": {
            "lane_id": "btc_clip",
            "model": "OpenCLIP ViT-B-32/openai",
            "frame_space": "BTC",
            "vectors": 177321,
            "latency_ms": {
                "p50": round(_percentile(btc_latencies, 50), 2),
                "p95": round(_percentile(btc_latencies, 95), 2),
                "mean": round(float(np.mean(btc_latencies)), 2),
            },
        },
        "candidate_overlap_diversity": {
            "mean_video_set_jaccard": round(float(np.mean(jaccards)), 4),
            "median_video_set_jaccard": round(float(np.median(jaccards)), 4),
            "mean_shared_candidate_videos": round(float(np.mean(shared_counts)), 1),
            "mean_siglip_only_candidate_videos": round(float(np.mean(siglip_only_counts)), 1),
            "mean_btc_only_candidate_videos": round(float(np.mean(btc_only_counts)), 1),
        },
        "quality_evaluation_status": {
            "gt_scored_pairs": 0,
            "gt_unscored_pairs": len(selected_queries),
            "status": "BLOCKED_BY_GROUND_TRUTH",
        },
    }

    summary_json_file = output_dir / "summary.json"
    summary_json_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # 6. Write summary.md
    md_content = f"""# Paired Visual Retrieval Benchmark (SigLIP CUSTOM vs BTC CLIP)

- **Run ID:** `{run_id}`
- **Evaluation Type:** `CANDIDATE_OVERLAP_DIVERSITY`
- **Queries Evaluated:** {len(selected_queries)} DEV queries
- **Top-K:** {top_k}

## Candidate Overlap & Diversity
- **Mean Top-{top_k} Video Jaccard Similarity:** {summary['candidate_overlap_diversity']['mean_video_set_jaccard']}
- **Median Top-{top_k} Video Jaccard Similarity:** {summary['candidate_overlap_diversity']['median_video_set_jaccard']}
- **Mean Shared Candidate Videos / Query:** {summary['candidate_overlap_diversity']['mean_shared_candidate_videos']}
- **Mean SigLIP-Only Candidate Videos / Query:** {summary['candidate_overlap_diversity']['mean_siglip_only_candidate_videos']}
- **Mean BTC-Only Candidate Videos / Query:** {summary['candidate_overlap_diversity']['mean_btc_only_candidate_videos']}

## Latency Comparison
| Metric | SigLIP (CUSTOM 116k) | BTC CLIP (BTC 177k) |
| :--- | :--- | :--- |
| **p50 (ms)** | {summary['siglip_lane']['latency_ms']['p50']} | {summary['btc_clip_lane']['latency_ms']['p50']} |
| **p95 (ms)** | {summary['siglip_lane']['latency_ms']['p95']} | {summary['btc_clip_lane']['latency_ms']['p95']} |
| **Mean (ms)** | {summary['siglip_lane']['latency_ms']['mean']} | {summary['btc_clip_lane']['latency_ms']['mean']} |

## Per-Query Comparison
| Query ID | SigLIP Top-1 | BTC Top-1 | Shared Vids | SigLIP-Only | BTC-Only | Jaccard |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in per_query_records:
        md_content += f"| `{r['query_id']}` | `{r['siglip_top1']}` | `{r['btc_top1']}` | {r['shared_candidate_count']} | {r['siglip_only_candidate_count']} | {r['btc_only_candidate_count']} | {r['jaccard_video_set']:.4f} |\n"

    (output_dir / "summary.md").write_text(md_content, encoding="utf-8")

    # 7. Write DONE.json marker
    done_marker = {
        "task": "visual_pair_benchmark",
        "schema_version": 1,
        "run_id": run_id,
        "created_at": _utc_now(),
        "query_count": len(selected_queries),
        "summary_sha256": sha256_file(summary_json_file),
        "per_query_sha256": sha256_file(per_query_file),
    }
    (output_dir / "DONE.json").write_text(json.dumps(done_marker, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Visual pair benchmark complete: {len(selected_queries)} queries compared (mean Jaccard: {summary['candidate_overlap_diversity']['mean_video_set_jaccard']})")
    return summary
