"""Paired ASR Retrieval Comparison Runner (ASR BM25 vs ASR BGE-M3) (M4A).

Performs operational candidate comparison between the ASR BM25 lexical lane
and the ASR BGE-M3 dense semantic lane across identical queries and Top-K values.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aic2026.core.hashing import sha256_file
from aic2026.retrieval.providers.asr_bge import AsrBgeProvider
from aic2026.retrieval.providers.asr_bm25 import AsrBm25Provider
from aic2026.retrieval.providers.base import ProviderQuery


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_asr_pair_benchmark(
    bm25_db_path: str | Path,
    bge_artifact_dir: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 20,
    device: str = "cpu",
) -> dict[str, Any]:
    """Execute paired ASR search evaluation (BM25 vs BGE-M3) on DEV queries."""
    bm25_db = Path(bm25_db_path)
    bge_dir = Path(bge_artifact_dir)
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
    bm25_provider = AsrBm25Provider(bm25_db)
    bge_provider = AsrBgeProvider(bge_dir, device=device)

    # Warmup both
    bm25_provider.search(ProviderQuery(query_text="warmup", top_k=1))
    bge_provider.search(ProviderQuery(query_text="warmup", top_k=1))

    # 3. Run comparison
    per_query_records: list[dict[str, Any]] = []
    bm25_latencies: list[float] = []
    bge_latencies: list[float] = []
    jaccards: list[float] = []
    bm25_only_counts: list[int] = []
    bge_only_counts: list[int] = []
    shared_counts: list[int] = []

    for q in selected_queries:
        qid = q["query_id"]
        qtext = q["query_text"]

        label = label_map.get(qid, q)
        is_verified = label.get("verification_status") == "VERIFIED"

        # BM25 search
        t0 = time.perf_counter()
        bm25_hits = bm25_provider.search(ProviderQuery(query_text=qtext, top_k=top_k))
        bm25_elapsed = (time.perf_counter() - t0) * 1000
        bm25_latencies.append(bm25_elapsed)

        # BGE search
        t0 = time.perf_counter()
        bge_hits = bge_provider.search(ProviderQuery(query_text=qtext, top_k=top_k))
        bge_elapsed = (time.perf_counter() - t0) * 1000
        bge_latencies.append(bge_elapsed)

        # Candidate video analysis
        bm25_videos = [h.video_id for h in bm25_hits]
        bge_videos = [h.video_id for h in bge_hits]

        bm25_vset = set(bm25_videos)
        bge_vset = set(bge_videos)

        intersection = bm25_vset & bge_vset
        union = bm25_vset | bge_vset
        jaccard = len(intersection) / len(union) if union else 0.0

        bm25_only = bm25_vset - bge_vset
        bge_only = bge_vset - bm25_vset

        jaccards.append(jaccard)
        shared_counts.append(len(intersection))
        bm25_only_counts.append(len(bm25_only))
        bge_only_counts.append(len(bge_only))

        record = {
            "query_id": qid,
            "query_text": qtext,
            "split": split,
            "verification_status": label.get("verification_status", "UNVERIFIED"),
            "bm25_hit_count": len(bm25_hits),
            "bge_hit_count": len(bge_hits),
            "bm25_latency_ms": round(bm25_elapsed, 2),
            "bge_latency_ms": round(bge_elapsed, 2),
            "candidate_video_jaccard": round(jaccard, 4),
            "shared_videos_count": len(intersection),
            "bm25_only_videos_count": len(bm25_only),
            "bge_only_videos_count": len(bge_only),
            "shared_videos": sorted(intersection),
            "bm25_only_videos": sorted(bm25_only),
            "bge_only_videos": sorted(bge_only),
            "bm25_top_candidates": [
                {"rank": h.rank, "video_id": h.video_id, "segment_uid": h.evidence_id, "score": h.raw_score}
                for h in bm25_hits[:5]
            ],
            "bge_top_candidates": [
                {"rank": h.rank, "video_id": h.video_id, "segment_uid": h.evidence_id, "score": h.raw_score}
                for h in bge_hits[:5]
            ],
        }
        per_query_records.append(record)

    # 4. Save per_query.jsonl
    per_query_path = output_dir / "per_query.jsonl"
    with open(per_query_path, "w", encoding="utf-8") as f:
        for r in per_query_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5. Build summary metrics
    summary = {
        "comparison": "asr_bm25_vs_asr_bge",
        "split": split,
        "total_queries": len(selected_queries),
        "dataset_sha256": dataset_sha256,
        "video_set_jaccard": {
            "mean": round(float(np.mean(jaccards)), 4),
            "median": round(float(np.median(jaccards)), 4),
            "min": round(float(np.min(jaccards)), 4),
            "max": round(float(np.max(jaccards)), 4),
        },
        "candidate_distribution": {
            "mean_shared_videos": round(float(np.mean(shared_counts)), 2),
            "mean_bm25_only_videos": round(float(np.mean(bm25_only_counts)), 2),
            "mean_bge_only_videos": round(float(np.mean(bge_only_counts)), 2),
        },
        "latency_ms": {
            "bm25_mean": round(float(np.mean(bm25_latencies)), 2),
            "bm25_p50": round(_percentile(bm25_latencies, 50), 2),
            "bm25_p95": round(_percentile(bm25_latencies, 95), 2),
            "bge_mean": round(float(np.mean(bge_latencies)), 2),
            "bge_p50": round(_percentile(bge_latencies, 50), 2),
            "bge_p95": round(_percentile(bge_latencies, 95), 2),
        },
        "executed_at": _utc_now(),
    }

    summary_json_path = output_dir / "summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # 6. Save Markdown summary
    summary_md_path = output_dir / "summary.md"
    with open(summary_md_path, "w", encoding="utf-8") as f:
        f.write(f"# Paired ASR Retrieval Comparison Report — BM25 vs BGE-M3 ({split})\n\n")
        f.write(f"- **Queries Compared**: `{len(selected_queries)}`\n")
        f.write(f"- **Video-set Jaccard (Mean)**: `{summary['video_set_jaccard']['mean']}`\n")
        f.write(f"- **Video-set Jaccard (Median)**: `{summary['video_set_jaccard']['median']}`\n")
        f.write(f"- **Mean Shared Candidate Videos**: `{summary['candidate_distribution']['mean_shared_videos']}`\n")
        f.write(f"- **Mean BM25-only Candidate Videos**: `{summary['candidate_distribution']['mean_bm25_only_videos']}`\n")
        f.write(f"- **Mean BGE-only Candidate Videos**: `{summary['candidate_distribution']['mean_bge_only_videos']}`\n")
        f.write(f"- **BM25 Latency p50 / p95**: `{summary['latency_ms']['bm25_p50']} ms / {summary['latency_ms']['bm25_p95']} ms`\n")
        f.write(f"- **BGE Latency p50 / p95**: `{summary['latency_ms']['bge_p50']} ms / {summary['latency_ms']['bge_p95']} ms`\n")

    # 7. Write DONE marker
    done_path = output_dir / "DONE.json"
    with open(done_path, "w", encoding="utf-8") as f:
        json.dump({"status": "PASS", "comparison": "asr_bm25_vs_asr_bge", "summary": summary}, f, indent=2)

    return summary
