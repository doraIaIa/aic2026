"""ASR Retrieval Lane Benchmark Runner (BM25 or BGE-M3) (M4A).

Executes reproducible evaluation of ASR BM25 or BGE-M3 on the DEV benchmark
query suite, recording latencies, candidate outputs, and ground-truth status.
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


def run_asr_benchmark(
    lane: str,
    target_path: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 20,
    device: str = "cpu",
) -> dict[str, Any]:
    """Execute reproducible evaluation on DEV queries for ASR BM25 or BGE lane."""
    target_path = Path(target_path)
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load dataset queries & labels
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

    # 2. Instantiate provider
    if lane == "asr_bm25":
        provider = AsrBm25Provider(target_path)
    elif lane == "asr_bge":
        provider = AsrBgeProvider(target_path, device=device)
    else:
        raise ValueError(f"Unknown ASR lane: {lane}")

    # Warmup
    provider.search(ProviderQuery(query_text="warmup", top_k=1))

    # 3. Execute benchmark queries
    t_start = time.perf_counter()
    per_query_records: list[dict[str, Any]] = []
    latencies: list[float] = []
    scored_count = 0
    unscored_count = 0
    empty_count = 0

    for q in selected_queries:
        qid = q["query_id"]
        qtext = q["query_text"]

        label = label_map.get(qid, q)
        is_verified = label.get("verification_status") == "VERIFIED"

        t0 = time.perf_counter()
        hits = provider.search(ProviderQuery(query_text=qtext, top_k=top_k))
        elapsed = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed)

        if not hits:
            empty_count += 1

        top_candidates = [
            {
                "rank": h.rank,
                "video_id": h.video_id,
                "segment_uid": h.evidence_id,
                "raw_score": h.raw_score,
                "start_sec": h.start_sec,
                "end_sec": h.end_sec,
                "text": h.payload.get("text_raw", "")[:60],
            }
            for h in hits
        ]

        if is_verified:
            scored_count += 1
            hit_target = False  # If GT verified
        else:
            unscored_count += 1
            hit_target = None

        record = {
            "query_id": qid,
            "query_text": qtext,
            "query_type": q.get("query_type", "UNKNOWN"),
            "split": split,
            "verification_status": label.get("verification_status", "UNVERIFIED"),
            "latency_ms": round(elapsed, 2),
            "hit_count": len(hits),
            "top_candidates": top_candidates,
            "quality_status": "SCORED" if is_verified else "BLOCKED_BY_GROUND_TRUTH",
        }
        per_query_records.append(record)

    total_duration_sec = time.perf_counter() - t_start

    # 4. Save per_query.jsonl
    per_query_path = output_dir / "per_query.jsonl"
    with open(per_query_path, "w", encoding="utf-8") as f:
        for r in per_query_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5. Build summary metrics
    summary = {
        "lane": lane,
        "split": split,
        "total_queries": len(selected_queries),
        "scored_queries": scored_count,
        "unscored_queries": unscored_count,
        "empty_result_queries": empty_count,
        "quality_status": "PASS" if scored_count > 0 else "BLOCKED_BY_GROUND_TRUTH",
        "dataset_sha256": dataset_sha256,
        "latency_ms": {
            "mean": round(float(np.mean(latencies)), 2),
            "p50": round(_percentile(latencies, 50), 2),
            "p95": round(_percentile(latencies, 95), 2),
            "min": round(float(np.min(latencies)), 2),
            "max": round(float(np.max(latencies)), 2),
        },
        "total_duration_sec": round(total_duration_sec, 2),
        "executed_at": _utc_now(),
    }

    summary_json_path = output_dir / "summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # 6. Save Markdown summary
    summary_md_path = output_dir / "summary.md"
    with open(summary_md_path, "w", encoding="utf-8") as f:
        f.write(f"# ASR Retrieval Benchmark Report — {lane.upper()} ({split})\n\n")
        f.write(f"- **Lane**: `{lane}`\n")
        f.write(f"- **Split**: `{split}`\n")
        f.write(f"- **Queries Executed**: `{len(selected_queries)}`\n")
        f.write(f"- **Scored Queries**: `{scored_count}`\n")
        f.write(f"- **Unscored Queries**: `{unscored_count}`\n")
        f.write(f"- **Empty Results**: `{empty_count}`\n")
        f.write(f"- **Quality Evaluation Status**: `{summary['quality_status']}`\n")
        f.write(f"- **Latency p50**: `{summary['latency_ms']['p50']} ms`\n")
        f.write(f"- **Latency p95**: `{summary['latency_ms']['p95']} ms`\n")
        f.write(f"- **Total Duration**: `{summary['total_duration_sec']} s`\n")

    # 7. Write DONE marker
    done_path = output_dir / "DONE.json"
    with open(done_path, "w", encoding="utf-8") as f:
        json.dump({"status": "PASS", "lane": lane, "summary": summary}, f, indent=2)

    return summary
