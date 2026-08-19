"""BTC CLIP standalone retrieval benchmark runner (M3A).

Runs reproducible evaluations against the DEV dataset using BtcClipProvider,
preserving canonical scoring contracts and recording per-query diagnostics.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aic2026.core.hashing import sha256_file
from aic2026.evaluation.scoring import score_video_retrieval
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.btc_clip import BtcClipProvider


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_btc_clip_benchmark(
    index_dir: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 100,
    device: str = "cpu",
) -> dict[str, Any]:
    """Execute BTC CLIP benchmark on DEV evaluation queries."""
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

    # 2. Load provider & marker
    provider = BtcClipProvider(index_dir, device=device)
    done_data = json.loads((index_dir / "DONE.json").read_text(encoding="utf-8"))

    # 3. Warm up model
    print(f"Running BTC CLIP benchmark for {len(selected_queries)} queries (split={split})...")
    provider.search(ProviderQuery(query_text="warmup query", top_k=1))

    # 4. Evaluate each query
    run_id = f"btc_clip_dev_{int(time.time())}"
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
                "csv_n": h.payload.get("csv_n", 0),
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
                failure_tag = "BTC_CLIP_VISUAL_MISS"
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
            "predictions": predictions,
        })

    # 5. Write per_query.jsonl
    per_query_file = output_dir / "per_query.jsonl"
    with open(per_query_file, "w", encoding="utf-8") as f:
        for rec in per_query_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 6. Build summary
    lat_p50 = round(_percentile(latencies, 50), 2)
    lat_p95 = round(_percentile(latencies, 95), 2)
    lat_mean = round(float(np.mean(latencies)), 2) if latencies else 0.0

    avg_unique_vids = round(float(np.mean([r["unique_videos"] for r in per_query_records])), 1)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "lane": "btc_clip",
        "timestamp": _utc_now(),
        "dataset_split": split,
        "query_count": len(selected_queries),
        "dataset_sha256": dataset_sha256,
        "index_id": "clip-faiss-btc-v1",
        "index_rows": done_data.get("processed_count", 177321),
        "index_sha256": done_data.get("index_sha256"),
        "metadata_sha256": done_data.get("metadata_sha256"),
        "model": "ViT-B-32",
        "pretrained": "openai",
        "device": device,
        "top_k": top_k,
        "latency_ms": {
            "p50": lat_p50,
            "p95": lat_p95,
            "mean": lat_mean,
            "min": round(min(latencies), 2) if latencies else 0.0,
            "max": round(max(latencies), 2) if latencies else 0.0,
        },
        "candidate_diversity": {
            "avg_unique_videos_per_query": avg_unique_vids,
        },
        "scoring": {
            "scored_queries": scored_count,
            "unscored_queries": unscored_count,
            "quality_status": "BLOCKED_BY_GROUND_TRUTH" if scored_count == 0 else "SCORED",
            "video_recall": {f"R@{k}": round(video_recalls[k] / scored_count, 4) if scored_count > 0 else "UNSCORED" for k in video_recalls},
            "mean_first_correct_rank": round(float(np.mean(first_correct_ranks)), 2) if first_correct_ranks else "UNSCORED",
            "failure_tag_counts": failure_tag_counts,
        },
    }

    summary_json_file = output_dir / "summary.json"
    summary_json_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # 7. Write summary.md
    md_content = f"""# BTC CLIP Retrieval Benchmark Summary

- **Run ID:** `{run_id}`
- **Lane:** `btc_clip` (BTC keyframe space, 177,321 vectors)
- **Model:** `OpenCLIP ViT-B-32/openai`
- **FAISS Index:** `IndexIDMap2(IndexFlatIP)`
- **Device:** `{device}`
- **Split:** `{split}` ({len(selected_queries)} queries)
- **Quality Status:** `{summary['scoring']['quality_status']}`

## Latency
- **p50:** {lat_p50} ms
- **p95:** {lat_p95} ms
- **Mean:** {lat_mean} ms

## Candidate Diversity
- **Average Unique Candidate Videos / Query (Top-{top_k}):** {avg_unique_vids}

## Per-Query Top-1 Matches
| Query ID | Latency (ms) | Top-1 Video | Keyframe UID | Raw Score | Unique Vids |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in per_query_records:
        md_content += f"| `{r['query_id']}` | {r['latency_ms']} | `{r['top_1_video']}` | `{r['top_1_uid']}` | {r['top_1_score']} | {r['unique_videos']} |\n"

    (output_dir / "summary.md").write_text(md_content, encoding="utf-8")

    # 8. Write DONE.json marker
    done_marker = {
        "task": "btc_clip_benchmark",
        "schema_version": 1,
        "run_id": run_id,
        "created_at": _utc_now(),
        "query_count": len(selected_queries),
        "scored_count": scored_count,
        "unscored_count": unscored_count,
        "summary_sha256": sha256_file(summary_json_file),
        "per_query_sha256": sha256_file(per_query_file),
    }
    (output_dir / "DONE.json").write_text(json.dumps(done_marker, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"BTC CLIP benchmark complete: {len(selected_queries)} queries evaluated in {sum(latencies)/1000:.2f}s (p50: {lat_p50}ms)")
    return summary
