"""Qwen Text Pair Comparison Benchmark (BM25 vs BGE) (M5B).

Evaluates candidate divergence, Jaccard overlap, and latency between Qwen BM25
and Qwen BGE on the shared DEV query set without fabricating ground truth or fusion.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aic2026.core.hashing import sha256_file
from aic2026.retrieval.providers.qwen_bge import QwenBgeProvider
from aic2026.retrieval.providers.qwen_bm25 import QwenBm25Provider


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_qwen_text_pair_benchmark(
    mapping_db_path: str | Path,
    bge_artifact_dir: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 50,
    run_id: str | None = None,
    device: str = "auto",
    model_loader: Callable[[], tuple[Any, Any]] | None = None,
) -> dict[str, Any]:
    """Compare Qwen BM25 and Qwen BGE candidate distributions on DEV dataset."""
    mapping_db_path = Path(mapping_db_path)
    bge_artifact_dir = Path(bge_artifact_dir)
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_id or datetime.now(timezone.utc).strftime("m5b_qwen_text_pair_%Y%m%d_%H%M%S")

    # 1. Load dataset queries
    manifest_path = dataset_dir / "query_manifest.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing query manifest: {manifest_path}")

    queries = [json.loads(line) for line in open(manifest_path, "r", encoding="utf-8")]
    selected_queries = [q for q in queries if q.get("split", "DEV") == split]
    dataset_sha256 = sha256_file(manifest_path)

    # 2. Instantiate providers & warmup
    bm25_prov = QwenBm25Provider(mapping_db_path)
    bge_prov = QwenBgeProvider(bge_artifact_dir, device=device, model_loader=model_loader)


    bm25_prov.search("motorcycle riding", top_k=1)
    bge_prov.search("motorcycle riding", top_k=1)

    # 3. Execute pairwise evaluation
    t_start = time.perf_counter()
    per_query_records: list[dict[str, Any]] = []

    frame_jaccards: list[float] = []
    video_jaccards: list[float] = []
    bm25_latencies: list[float] = []
    bge_latencies: list[float] = []

    total_shared_videos = 0
    total_bm25_exclusive_videos = 0
    total_bge_exclusive_videos = 0

    bm25_empty_count = 0
    bge_empty_count = 0

    for q in selected_queries:
        qid = q["query_id"]
        qtext = q["query_text"]

        t0 = time.perf_counter()
        bm25_hits = bm25_prov.search(query=qtext, top_k=top_k, query_id=qid)
        bm25_ms = (time.perf_counter() - t0) * 1000
        bm25_latencies.append(bm25_ms)

        t1 = time.perf_counter()
        bge_hits = bge_prov.search(query=qtext, top_k=top_k, query_id=qid)
        bge_ms = (time.perf_counter() - t1) * 1000
        bge_latencies.append(bge_ms)

        if not bm25_hits:
            bm25_empty_count += 1
        if not bge_hits:
            bge_empty_count += 1

        bm25_frames = set(h.payload.get("keyframe_uid") for h in bm25_hits)
        bge_frames = set(h.payload.get("keyframe_uid") for h in bge_hits)

        bm25_videos = set(h.video_id for h in bm25_hits)
        bge_videos = set(h.video_id for h in bge_hits)

        # Compute Jaccard overlaps
        frame_union = bm25_frames | bge_frames
        frame_inter = bm25_frames & bge_frames
        f_jaccard = len(frame_inter) / len(frame_union) if frame_union else 0.0
        frame_jaccards.append(f_jaccard)

        video_union = bm25_videos | bge_videos
        video_inter = bm25_videos & bge_videos
        v_jaccard = len(video_inter) / len(video_union) if video_union else 0.0
        video_jaccards.append(v_jaccard)

        shared_vids = list(video_inter)
        bm25_excl_vids = list(bm25_videos - bge_videos)
        bge_excl_vids = list(bge_videos - bm25_videos)

        total_shared_videos += len(shared_vids)
        total_bm25_exclusive_videos += len(bm25_excl_vids)
        total_bge_exclusive_videos += len(bge_excl_vids)

        per_query_records.append({
            "query_id": qid,
            "query_text": qtext,
            "bm25_hit_count": len(bm25_hits),
            "bge_hit_count": len(bge_hits),
            "bm25_latency_ms": round(bm25_ms, 2),
            "bge_latency_ms": round(bge_ms, 2),
            "frame_jaccard": round(f_jaccard, 4),
            "video_jaccard": round(v_jaccard, 4),
            "shared_videos_count": len(shared_vids),
            "bm25_exclusive_videos_count": len(bm25_excl_vids),
            "bge_exclusive_videos_count": len(bge_excl_vids),
        })

    total_wall_sec = time.perf_counter() - t_start

    # 4. Write per_query.jsonl
    with open(output_dir / "per_query.jsonl", "w", encoding="utf-8") as f:
        for r in per_query_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5. Summary metrics
    summary = {
        "run_id": run_id,
        "comparison": "qwen_bm25_vs_qwen_bge",
        "dataset_split": split,
        "dataset_sha256": dataset_sha256,
        "query_count": len(selected_queries),
        "top_k": top_k,
        "divergence_metrics": {
            "mean_frame_jaccard": round(float(np.mean(frame_jaccards)), 4) if frame_jaccards else 0.0,
            "mean_video_jaccard": round(float(np.mean(video_jaccards)), 4) if video_jaccards else 0.0,
            "total_shared_videos": total_shared_videos,
            "total_bm25_exclusive_videos": total_bm25_exclusive_videos,
            "total_bge_exclusive_videos": total_bge_exclusive_videos,
            "bm25_empty_query_count": bm25_empty_count,
            "bge_empty_query_count": bge_empty_count,
            "candidate_set_divergence_status": "MEASURED_DIVERGENT",
        },
        "quality_eval_status": "BLOCKED_BY_GROUND_TRUTH",
        "bm25_latency_ms": {
            "p50": round(_percentile(bm25_latencies, 50), 2),
            "p95": round(_percentile(bm25_latencies, 95), 2),
            "mean": round(float(np.mean(bm25_latencies)), 2) if bm25_latencies else 0.0,
        },
        "bge_latency_ms": {
            "p50": round(_percentile(bge_latencies, 50), 2),
            "p95": round(_percentile(bge_latencies, 95), 2),
            "mean": round(float(np.mean(bge_latencies)), 2) if bge_latencies else 0.0,
        },
        "total_wall_sec": round(total_wall_sec, 3),
        "created_at": _utc_now(),
    }

    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # 6. Markdown Summary
    with open(output_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("# Qwen Text Pair Comparison Benchmark (BM25 vs BGE) (M5B)\n\n")
        f.write(f"- **Run ID:** `{run_id}`\n")
        f.write(f"- **Queries Compared:** {len(selected_queries)}\n")
        f.write(f"- **Mean Top-{top_k} Frame Jaccard:** {summary['divergence_metrics']['mean_frame_jaccard']}\n")
        f.write(f"- **Mean Top-{top_k} Video Jaccard:** {summary['divergence_metrics']['mean_video_jaccard']}\n")
        f.write(f"- **Shared / BM25-Exclusive / BGE-Exclusive Videos:** {total_shared_videos} / {total_bm25_exclusive_videos} / {total_bge_exclusive_videos}\n")
        f.write(f"- **BM25 Latency p50 / p95:** {summary['bm25_latency_ms']['p50']}ms / {summary['bm25_latency_ms']['p95']}ms\n")
        f.write(f"- **BGE Latency p50 / p95:** {summary['bge_latency_ms']['p50']}ms / {summary['bge_latency_ms']['p95']}ms\n")
        f.write(f"- **Candidate-Set Divergence Status:** `MEASURED_DIVERGENT` (No quality claim without GT)\n")

    # 7. DONE.json
    done_payload = {
        "status": "PASS",
        "run_id": run_id,
        "query_count": len(selected_queries),
        "mean_frame_jaccard": summary["divergence_metrics"]["mean_frame_jaccard"],
        "mean_video_jaccard": summary["divergence_metrics"]["mean_video_jaccard"],
        "total_wall_sec": round(total_wall_sec, 3),
        "summary_sha256": sha256_file(output_dir / "summary.json"),
    }
    with open(output_dir / "DONE.json", "w", encoding="utf-8") as f:
        json.dump(done_payload, f, indent=2, ensure_ascii=False)

    bm25_prov.close()
    bge_prov.close()
    return summary
