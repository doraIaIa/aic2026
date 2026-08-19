"""Qwen Structured Facet Retrieval Lane Benchmark Runner (M5A).

Executes reproducible evaluation of the Qwen Structured lane on the DEV benchmark
query suite. Evaluates FRAME evidence in CUSTOM space.
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
from aic2026.retrieval.providers.qwen_structured import QwenStructuredProvider


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_qwen_structured_benchmark(
    index_db_path: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 50,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute reproducible evaluation on DEV queries for Qwen Structured lane.
    
    Status is BLOCKED_BY_GROUND_TRUTH unless real calibrated GT is available.
    """
    index_db_path = Path(index_db_path)
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_id or datetime.now(timezone.utc).strftime("m5a_qwen_structured_%Y%m%d_%H%M%S")

    # 1. Load dataset queries
    manifest_path = dataset_dir / "query_manifest.jsonl"
    labels_path = dataset_dir / "labels.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing query manifest: {manifest_path}")

    queries = [json.loads(line) for line in open(manifest_path, "r", encoding="utf-8")]
    selected_queries = [q for q in queries if q.get("split", "DEV") == split]

    dataset_sha256 = sha256_file(manifest_path)

    # 2. Instantiate provider & warmup
    provider = QwenStructuredProvider(index_db_path)
    provider_health = provider.health()
    if provider_health.get("status") != "OK":
        raise RuntimeError(
            f"Qwen structured provider health check failed: {provider_health.get('error')}"
        )

    # Warmup
    provider.search("motorcycle riding", top_k=1)

    # 3. Execute benchmark queries
    t_start = time.perf_counter()
    per_query_records: list[dict[str, Any]] = []
    latencies_total: list[float] = []
    matched_facet_counts: list[int] = []
    unique_video_ids: set[str] = set()
    empty_count = 0
    scored_count = 0
    unscored_count = 0

    for q in selected_queries:
        qid = q["query_id"]
        qtext = q["query_text"]

        t0 = time.perf_counter()
        hits = provider.search(
            query=qtext,
            top_k=top_k,
            query_id=qid,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies_total.append(elapsed_ms)

        if not hits:
            empty_count += 1
            unscored_count += 1
            per_query_records.append({
                "query_id": qid,
                "query_text": qtext,
                "hit_count": 0,
                "elapsed_ms": round(elapsed_ms, 2),
                "matched_facets": [],
                "top_hits": [],
                "status": "NO_MATCHED_FACETS",
            })
            continue

        unscored_count += 1  # No GT ground truth annotated for Qwen facets
        for h in hits:
            unique_video_ids.add(h.video_id)

        all_matched_facets = []
        for h in hits:
            for mf in h.payload.get("matched_facets", []):
                all_matched_facets.append(mf["facet_id"])
        matched_facet_counts.append(len(set(all_matched_facets)))

        top_hit_dicts = [
            {
                "rank": h.rank,
                "score": h.raw_score,
                "video_id": h.video_id,
                "keyframe_uid": h.payload.get("keyframe_uid"),
                "start_sec": h.start_sec,
                "matched_facets": [mf["facet_id"] for mf in h.payload.get("matched_facets", [])],
            }
            for h in hits[:5]
        ]

        per_query_records.append({
            "query_id": qid,
            "query_text": qtext,
            "hit_count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "unique_matched_facets": list(set(all_matched_facets)),
            "top_hits": top_hit_dicts,
            "status": "OK",
        })

    total_wall_sec = time.perf_counter() - t_start

    # 4. Write per_query.jsonl
    with open(output_dir / "per_query.jsonl", "w", encoding="utf-8") as f:
        for r in per_query_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5. Summary metrics
    summary = {
        "run_id": run_id,
        "lane_id": "qwen_structured",
        "entity_type": "FRAME",
        "frame_space": "CUSTOM",
        "score_type": "qwen_facet_support",
        "score_direction": "HIGHER_IS_BETTER",
        "dataset_split": split,
        "dataset_sha256": dataset_sha256,
        "dataset_query_count": len(selected_queries),
        "empty_query_count": empty_count,
        "scored_query_count": scored_count,
        "unscored_query_count": unscored_count,
        "quality_eval_status": "BLOCKED_BY_GROUND_TRUTH",
        "unique_videos_retrieved": len(unique_video_ids),
        "total_wall_sec": round(total_wall_sec, 3),
        "latency_ms": {
            "p50": round(_percentile(latencies_total, 50), 2),
            "p90": round(_percentile(latencies_total, 90), 2),
            "p95": round(_percentile(latencies_total, 95), 2),
            "p99": round(_percentile(latencies_total, 99), 2),
            "mean": round(float(np.mean(latencies_total)), 2) if latencies_total else 0.0,
        },
        "matched_facets_per_query": {
            "mean": round(float(np.mean(matched_facet_counts)), 2) if matched_facet_counts else 0.0,
            "max": int(max(matched_facet_counts)) if matched_facet_counts else 0,
        },
        "created_at": _utc_now(),
    }

    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # 6. Markdown Summary
    with open(output_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("# Qwen Structured Facet Retrieval Lane Benchmark Summary (M5A)\n\n")
        f.write(f"- **Run ID:** `{run_id}`\n")
        f.write(f"- **Lane:** `qwen_structured` (FRAME / CUSTOM)\n")
        f.write(f"- **Quality Status:** `BLOCKED_BY_GROUND_TRUTH`\n")
        f.write(f"- **Queries Evaluated:** {len(selected_queries)}\n")
        f.write(f"- **Empty (No Facets Matched):** {empty_count}\n")
        f.write(f"- **Unique Videos Retrieved:** {len(unique_video_ids)}\n")
        f.write(f"- **Latency p50 / p95:** {summary['latency_ms']['p50']}ms / {summary['latency_ms']['p95']}ms\n")
        f.write(f"- **Total Wall Time:** {total_wall_sec:.2f}s\n")

    # 7. DONE.json
    done_payload = {
        "status": "PASS",
        "run_id": run_id,
        "lane_id": "qwen_structured",
        "quality_eval_status": "BLOCKED_BY_GROUND_TRUTH",
        "query_count": len(selected_queries),
        "total_wall_sec": round(total_wall_sec, 3),
        "summary_sha256": sha256_file(output_dir / "summary.json"),
    }
    with open(output_dir / "DONE.json", "w", encoding="utf-8") as f:
        json.dump(done_payload, f, indent=2, ensure_ascii=False)

    provider.close()
    return summary

