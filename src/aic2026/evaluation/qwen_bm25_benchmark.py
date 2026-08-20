"""Qwen Caption BM25 Retrieval Lane Benchmark Runner (M5B1).

Executes reproducible evaluation of the Qwen BM25 lane on the DEV benchmark
query suite. Returns FRAME-level evidence in CUSTOM frame space.
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
from aic2026.retrieval.providers.qwen_bm25 import QwenBm25Provider


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_qwen_bm25_benchmark(
    db_path: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 20,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute reproducible evaluation on DEV queries for Qwen BM25 lane.

    Returns FRAME-level evidence in CUSTOM space.
    If ground truth is unverified/unscored, status = BLOCKED_BY_GROUND_TRUTH.
    """
    db_path = Path(db_path)
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_id or datetime.now(timezone.utc).strftime("m5b1_qwen_bm25_%Y%m%d_%H%M%S")

    # 1. Load dataset queries & labels
    manifest_path = dataset_dir / "query_manifest.jsonl"
    labels_path = dataset_dir / "labels.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing query manifest: {manifest_path}")

    manifest_sha = sha256_file(manifest_path)
    labels_sha = sha256_file(labels_path) if labels_path.is_file() else None

    queries: list[dict[str, Any]] = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item.get("split") == split or split == "ALL":
                    queries.append(item)

    # 2. Instantiate provider & inspect health
    provider = QwenBm25Provider(db_path)
    health = provider.health()
    if health.get("status") != "OK":
        raise RuntimeError(f"Qwen BM25 provider unhealthy: {health}")

    # 3. Execute search per query and record latency
    per_query_results: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    unique_videos_all: set[str] = set()
    empty_result_count = 0

    for q in queries:
        qid = q["query_id"]
        qtext = q["query_text"]
        vids = tuple(q.get("candidate_video_ids") or ())

        t0 = time.perf_counter()
        hits = provider.search(
            ProviderQuery(query_text=qtext, top_k=top_k, video_ids=vids),
            query_id=qid,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        hit_dicts = []
        for h in hits:
            unique_videos_all.add(h.video_id)
            hit_dicts.append({
                "rank": h.rank,
                "video_id": h.video_id,
                "evidence_id": h.evidence_id,
                "keyframe_uid": h.payload.get("keyframe_uid"),
                "frame_idx": h.payload.get("frame_idx"),
                "timestamp_ms": h.payload.get("timestamp_ms"),
                "raw_score": h.raw_score,
                "score_type": h.provenance.get("score_type", "sqlite_fts5_bm25"),
                "caption": h.payload.get("caption", ""),
            })

        if not hits:
            empty_result_count += 1

        per_query_results.append({
            "query_id": qid,
            "query_text": qtext,
            "category": q.get("category", "unknown"),
            "candidate_video_ids": list(vids),
            "hit_count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": hit_dicts,
        })

    provider.close()

    # 4. Generate benchmark summary
    summary = {
        "run_id": run_id,
        "lane_id": "qwen_bm25",
        "created_at": _utc_now(),
        "split": split,
        "query_count": len(queries),
        "scored_query_count": 0,
        "unscored_query_count": len(queries),
        "empty_result_count": empty_result_count,
        "unique_candidate_videos": len(unique_videos_all),
        "quality_evaluation_status": "BLOCKED_BY_GROUND_TRUTH",
        "dataset": {
            "dir": str(dataset_dir),
            "manifest_sha256": manifest_sha,
            "labels_sha256": labels_sha,
        },
        "database": {
            "path": str(db_path),
            "qwen_fts_table": "qwen_caption_fts",
            "qwen_fts_rows": health.get("qwen_fts_rows", 116767),
            "canonical_qwen_rows": health.get("canonical_qwen_rows", 116767),
        },
        "latency_ms": {
            "p50": round(_percentile(latencies_ms, 50), 2),
            "p90": round(_percentile(latencies_ms, 90), 2),
            "p95": round(_percentile(latencies_ms, 95), 2),
            "max": round(max(latencies_ms) if latencies_ms else 0.0, 2),
        },
    }

    # Write output artifacts
    summary_path = output_dir / "benchmark_summary.json"
    results_path = output_dir / "per_query_results.json"

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(per_query_results, f, indent=2)

    return summary
