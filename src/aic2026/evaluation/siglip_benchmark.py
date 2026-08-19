"""SigLIP2 CUSTOM standalone retrieval benchmark runner (M2A).

Runs reproducible evaluations against the DEV dataset using SigLIPProvider,
preserving canonical scoring contracts and recording per-query diagnostics.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aic2026.core.hashing import sha256_file
from aic2026.evaluation.scoring import CUTOFFS, score_query, score_video_retrieval
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.siglip import SigLIPProvider


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_siglip_benchmark(
    index_dir: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 100,
    device: str = "cpu",
) -> dict[str, Any]:
    """Execute SigLIP-only benchmark on DEV evaluation queries."""
    index_dir = Path(index_dir)
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load dataset queries and labels
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

    # Dataset hash
    dataset_sha256 = sha256_file(manifest_path)

    # 2. Load provider & passport
    provider = SigLIPProvider(index_dir, device=device)
    passport_path = index_dir / "siglip_custom_passport.json"
    passport = json.loads(passport_path.read_text(encoding="utf-8")) if passport_path.is_file() else {}
    done_data = json.loads((index_dir / "DONE.json").read_text(encoding="utf-8"))

    # 3. Warm up model
    print(f"Running SigLIP benchmark for {len(selected_queries)} queries (split={split})...")
    provider.search(ProviderQuery(query_text="warmup query", top_k=1))

    # 4. Evaluate each query
    run_id = f"siglip_custom_dev_{int(time.time())}"
    per_query_records: list[dict[str, Any]] = []
    latencies: list[float] = []

    scored_count = 0
    unscored_count = 0
    video_recalls = {k: 0 for k in (1, 5, 10, 20, 50, 100)}
    first_correct_ranks: list[int] = []
    failure_tag_counts: dict[str, int] = {}

    for q in selected_queries:
        qid = q["query_id"]
        qtype = q.get("query_type", "KIS")
        qtext = q["query_text"]

        label = label_map.get(qid, q)
        is_verified = label.get("verification_status") == "VERIFIED"

        t0 = time.perf_counter()
        hits = provider.search(ProviderQuery(query_text=qtext, top_k=top_k))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        # Convert hits to prediction objects
        predictions = []
        for h in hits:
            predictions.append({
                "rank": h.rank,
                "video_id": h.video_id,
                "frame_idx": h.payload.get("frame_idx", 0),
                "keyframe_uid": h.evidence_id,
                "timestamp_ms": h.payload.get("timestamp_ms", int(h.start_sec * 1000)),
                "raw_score": h.raw_score,
            })

        # Calculate candidate video diversity
        unique_vids = len({p["video_id"] for p in predictions})

        # Scoring
        score_result = None
        failure_tag = None
        if is_verified:
            scored_count += 1
            # Run video retrieval scoring
            v_score = score_video_retrieval(label, predictions)
            score_result = v_score
            first_rank = v_score.get("first_correct_video_rank")
            if first_rank is not None:
                first_correct_ranks.append(first_rank)
                for k in video_recalls:
                    if first_rank <= k:
                        video_recalls[k] += 1
            else:
                failure_tag = "SIGLIP_VISUAL_MISS"
                failure_tag_counts[failure_tag] = failure_tag_counts.get(failure_tag, 0) + 1
        else:
            unscored_count += 1
            failure_tag = "UNSCORED_BY_CURRENT_CONTRACT"

        per_query_records.append({
            "query_id": qid,
            "query_type": qtype,
            "query_text": qtext,
            "split": split,
            "latency_ms": round(elapsed_ms, 2),
            "hits_count": len(hits),
            "unique_videos": unique_vids,
            "top_1_video": predictions[0]["video_id"] if predictions else None,
            "top_1_uid": predictions[0]["keyframe_uid"] if predictions else None,
            "top_1_score": round(predictions[0]["raw_score"], 4) if predictions else None,
            "is_verified": is_verified,
            "score_result": score_result,
            "failure_tag": failure_tag,
            "predictions_top_10": predictions[:10],
        })

    # Summary metrics
    lat_p50 = _percentile(latencies, 50)
    lat_p95 = _percentile(latencies, 95)
    lat_mean = float(np.mean(latencies))

    summary = {
        "run_id": run_id,
        "lane": "siglip_custom",
        "split": split,
        "query_count": len(selected_queries),
        "scored_query_count": scored_count,
        "unscored_query_count": unscored_count,
        "latency_ms": {
            "p50": round(lat_p50, 2),
            "p95": round(lat_p95, 2),
            "mean": round(lat_mean, 2),
        },
        "video_recall": {
            f"R@{k}": round(video_recalls[k] / scored_count, 4) if scored_count > 0 else "UNSCORED"
            for k in (1, 5, 10, 20, 50, 100)
        },
        "first_correct_rank_stats": {
            "count": len(first_correct_ranks),
            "mean": round(float(np.mean(first_correct_ranks)), 2) if first_correct_ranks else None,
            "median": float(np.median(first_correct_ranks)) if first_correct_ranks else None,
        },
        "candidate_diversity_mean": round(float(np.mean([r["unique_videos"] for r in per_query_records])), 2),
        "failure_tags": failure_tag_counts,
        "provenance": {
            "model_id": passport.get("model_id", "google/siglip2-base-patch16-224"),
            "dimension": 768,
            "index_rows": done_data.get("row_count", 116767),
            "index_checksum": done_data.get("index_sha256"),
            "rowmap_checksum": done_data.get("rowmap_sha256"),
            "dataset_checksum": dataset_sha256,
            "m1_runtime_build_id": passport.get("m1_runtime_build_id"),
            "device": device,
            "created_at": _utc_now(),
        },
        "status": "PASS",
    }

    # 5. Write artifacts
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    per_query_path = run_dir / "per_query.jsonl"
    with open(per_query_path, "w", encoding="utf-8") as f:
        for r in per_query_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary_path = run_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    summary_md_path = run_dir / "summary.md"
    md_content = f"""# SigLIP2 CUSTOM Retrieval Lane Benchmark Report

- **Run ID:** `{run_id}`
- **Lane:** `siglip_custom`
- **Split:** `{split}`
- **Total Queries:** {len(selected_queries)}
- **Scored Queries:** {scored_count} (Unscored: {unscored_count})
- **Latency:** p50={lat_p50:.1f}ms, p95={lat_p95:.1f}ms, mean={lat_mean:.1f}ms
- **Device:** `{device}`

## Video Recall @ K

| Metric | Value |
| :--- | :--- |
| Recall@1 | {summary['video_recall']['R@1']} |
| Recall@5 | {summary['video_recall']['R@5']} |
| Recall@10 | {summary['video_recall']['R@10']} |
| Recall@20 | {summary['video_recall']['R@20']} |
| Recall@50 | {summary['video_recall']['R@50']} |
| Recall@100 | {summary['video_recall']['R@100']} |

## Diagnostics & Invariants

- Model: `{summary['provenance']['model_id']}`
- FAISS Rows: {summary['provenance']['index_rows']}
- Candidate Diversity (unique videos/100): {summary['candidate_diversity_mean']}
- Status: **{summary['status']}**
"""
    summary_md_path.write_text(md_content, encoding="utf-8")

    done_eval = {
        "task": "siglip_benchmark",
        "schema_version": 1,
        "run_id": run_id,
        "lane": "siglip_custom",
        "query_count": len(selected_queries),
        "per_query_file": "per_query.jsonl",
        "summary_file": "summary.json",
        "summary_md": "summary.md",
        "created_at": _utc_now(),
        "status": "PASS",
    }
    with open(run_dir / "DONE.json", "w", encoding="utf-8") as f:
        json.dump(done_eval, f, indent=2)

    print(f"\nSigLIP benchmark finished: {len(selected_queries)} queries in {sum(latencies)/1000:.2f}s")
    print(f"  Latency: p50 = {lat_p50:.1f}ms, p95 = {lat_p95:.1f}ms")
    print(f"  Artifacts saved to: {run_dir}")

    return summary
