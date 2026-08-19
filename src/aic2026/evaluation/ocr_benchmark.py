"""OCR Retrieval Lane Benchmark Runner (BM25, Trigram, or BGE-M3) (M4C).

Executes reproducible evaluation of OCR BM25, OCR Trigram, or OCR BGE on the DEV benchmark
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
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.ocr_bge import OcrBgeProvider
from aic2026.retrieval.providers.ocr_bm25 import OcrBm25Provider
from aic2026.retrieval.providers.ocr_trigram import OcrTrigramProvider


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_ocr_benchmark(
    lane: str,
    target_path: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    canonical_db: str | Path | None = None,
    split: str = "DEV",
    top_k: int = 20,
) -> dict[str, Any]:
    """Execute reproducible evaluation on DEV queries for an OCR lane."""
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

    # 2. Instantiate provider
    if lane == "ocr_bm25":
        provider = OcrBm25Provider(target_path)
    elif lane == "ocr_trigram":
        provider = OcrTrigramProvider(target_path, canonical_db_path=canonical_db)
    elif lane == "ocr_bge":
        provider = OcrBgeProvider(target_path, canonical_db_path=canonical_db)
    else:
        raise ValueError(f"Unknown OCR lane: {lane}")

    # 3. Warmup provider
    provider.search(ProviderQuery(query_text="chào mừng", top_k=top_k))

    latencies_ms: list[float] = []
    run_records: list[dict[str, Any]] = []
    total_hits_count = 0
    zero_hits_queries = 0

    # 4. Execute benchmark queries
    t_start = time.perf_counter()
    for q in selected_queries:
        qid = q["query_id"]
        qtext = q.get("query_text") or q.get("text", "")
        vids = tuple(q.get("target_video_ids") or ())

        pq = ProviderQuery(query_text=qtext, top_k=top_k, video_ids=vids if vids else ())

        t0 = time.perf_counter()
        hits = provider.search(pq)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        if len(hits) == 0:
            zero_hits_queries += 1
        total_hits_count += len(hits)

        hit_records = []
        for h in hits:
            hit_records.append({
                "rank": h.rank,
                "evidence_id": h.evidence_id,
                "video_id": h.video_id,
                "start_sec": h.start_sec,
                "end_sec": h.end_sec,
                "raw_score": h.raw_score,
                "score_kind": h.score_kind,
                "text_snippet": h.payload.get("text_raw", "")[:60] if h.payload else "",
                "ocr_confidence": h.payload.get("ocr_confidence", 1.0) if h.payload else 1.0,
            })

        run_records.append({
            "query_id": qid,
            "query_text": qtext,
            "latency_ms": round(elapsed_ms, 3),
            "hits_count": len(hits),
            "hits": hit_records,
        })

    total_eval_duration_sec = time.perf_counter() - t_start

    # 5. Build summary
    summary = {
        "lane": lane,
        "split": split,
        "queries_evaluated": len(selected_queries),
        "top_k": top_k,
        "ground_truth_status": "BLOCKED_BY_GROUND_TRUTH",
        "gt_summary": {
            "total_queries": len(selected_queries),
            "scored_queries": 0,
            "unscored_queries": len(selected_queries),
            "reason": "OCR benchmark queries lack segment/keyframe ground truth annotations in internal-verified-v1",
        },
        "latency_stats_ms": {
            "p50": round(_percentile(latencies_ms, 50), 3),
            "p95": round(_percentile(latencies_ms, 95), 3),
            "p99": round(_percentile(latencies_ms, 99), 3),
            "mean": round(float(np.mean(latencies_ms)), 3) if latencies_ms else 0.0,
            "min": round(float(np.min(latencies_ms)), 3) if latencies_ms else 0.0,
            "max": round(float(np.max(latencies_ms)), 3) if latencies_ms else 0.0,
        },
        "retrieval_stats": {
            "total_hits_returned": total_hits_count,
            "avg_hits_per_query": round(total_hits_count / max(1, len(selected_queries)), 2),
            "zero_hits_queries": zero_hits_queries,
        },
        "benchmark_duration_sec": round(total_eval_duration_sec, 3),
        "executed_at": _utc_now(),
    }

    # 6. Materialize run artifacts
    results_path = output_dir / f"ocr_{lane}_{split.lower()}_run.jsonl"
    summary_path = output_dir / f"ocr_{lane}_{split.lower()}_summary.json"

    with open(results_path, "w", encoding="utf-8") as f:
        for r in run_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary["run_file"] = str(results_path.name)
    summary["run_file_sha256"] = sha256_file(results_path)

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary
