"""Three-Way OCR Retrieval Comparison Runner (BM25 vs Trigram vs BGE-M3) (M4C).

Executes reproducible side-by-side comparison across all three OCR retrieval legs
over identical queries and Top-K values, measuring pairwise Jaccard overlap, shared/exclusive
video candidates, and latency profiles.
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


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def run_ocr_three_way_comparison(
    bm25_db_path: str | Path,
    trigram_dir: str | Path,
    bge_dir: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    canonical_db: str | Path | None = None,
    split: str = "DEV",
    top_k: int = 20,
) -> dict[str, Any]:
    """Run three-way comparison on DEV benchmark queries."""
    bm25_db_path = Path(bm25_db_path)
    trigram_dir = Path(trigram_dir)
    bge_dir = Path(bge_dir)
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = dataset_dir / "query_manifest.jsonl"
    queries = [json.loads(line) for line in open(manifest_path, "r", encoding="utf-8")]
    selected_queries = [q for q in queries if q.get("split", "DEV") == split]

    p_bm25 = OcrBm25Provider(bm25_db_path)
    p_trigram = OcrTrigramProvider(trigram_dir, canonical_db_path=canonical_db or bm25_db_path)
    p_bge = OcrBgeProvider(bge_dir, canonical_db_path=canonical_db or bm25_db_path)

    # Warmup
    p_bm25.search(ProviderQuery("chào mừng", top_k=top_k))
    p_trigram.search(ProviderQuery("chào mừng", top_k=top_k))
    p_bge.search(ProviderQuery("chào mừng", top_k=top_k))

    latencies_bm25: list[float] = []
    latencies_trigram: list[float] = []
    latencies_bge: list[float] = []

    jaccards_bm25_trigram: list[float] = []
    jaccards_bm25_bge: list[float] = []
    jaccards_trigram_bge: list[float] = []

    jaccards_vid_bm25_trigram: list[float] = []
    jaccards_vid_bm25_bge: list[float] = []
    jaccards_vid_trigram_bge: list[float] = []

    query_comparisons: list[dict[str, Any]] = []

    t_start = time.perf_counter()
    for q in selected_queries:
        qid = q["query_id"]
        qtext = q.get("query_text") or q.get("text", "")
        vids = tuple(q.get("target_video_ids") or ())
        pq = ProviderQuery(query_text=qtext, top_k=top_k, video_ids=vids if vids else ())

        t0 = time.perf_counter()
        hits_bm25 = p_bm25.search(pq)
        lat_bm25 = (time.perf_counter() - t0) * 1000.0
        latencies_bm25.append(lat_bm25)

        t0 = time.perf_counter()
        hits_trigram = p_trigram.search(pq)
        lat_trigram = (time.perf_counter() - t0) * 1000.0
        latencies_trigram.append(lat_trigram)

        t0 = time.perf_counter()
        hits_bge = p_bge.search(pq)
        lat_bge = (time.perf_counter() - t0) * 1000.0
        latencies_bge.append(lat_bge)

        uids_bm25 = {h.evidence_id for h in hits_bm25}
        uids_trigram = {h.evidence_id for h in hits_trigram}
        uids_bge = {h.evidence_id for h in hits_bge}

        vids_bm25 = {h.video_id for h in hits_bm25}
        vids_trigram = {h.video_id for h in hits_trigram}
        vids_bge = {h.video_id for h in hits_bge}

        j_bt = _jaccard(uids_bm25, uids_trigram)
        j_bb = _jaccard(uids_bm25, uids_bge)
        j_tb = _jaccard(uids_trigram, uids_bge)

        j_vid_bt = _jaccard(vids_bm25, vids_trigram)
        j_vid_bb = _jaccard(vids_bm25, vids_bge)
        j_vid_tb = _jaccard(vids_trigram, vids_bge)

        jaccards_bm25_trigram.append(j_bt)
        jaccards_bm25_bge.append(j_bb)
        jaccards_trigram_bge.append(j_tb)

        jaccards_vid_bm25_trigram.append(j_vid_bt)
        jaccards_vid_bm25_bge.append(j_vid_bb)
        jaccards_vid_trigram_bge.append(j_vid_tb)

        query_comparisons.append({
            "query_id": qid,
            "query_text": qtext,
            "counts": {
                "bm25": len(hits_bm25),
                "trigram": len(hits_trigram),
                "bge": len(hits_bge),
            },
            "latencies_ms": {
                "bm25": round(lat_bm25, 2),
                "trigram": round(lat_trigram, 2),
                "bge": round(lat_bge, 2),
            },
            "item_jaccard": {
                "bm25_vs_trigram": round(j_bt, 4),
                "bm25_vs_bge": round(j_bb, 4),
                "trigram_vs_bge": round(j_tb, 4),
            },
            "video_jaccard": {
                "bm25_vs_trigram": round(j_vid_bt, 4),
                "bm25_vs_bge": round(j_vid_bb, 4),
                "trigram_vs_bge": round(j_vid_tb, 4),
            },
            "top1_items": {
                "bm25": hits_bm25[0].payload.get("text_raw", "") if hits_bm25 else None,
                "trigram": hits_trigram[0].payload.get("text_raw", "") if hits_trigram else None,
                "bge": hits_bge[0].payload.get("text_raw", "") if hits_bge else None,
            },
        })

    total_eval_duration = time.perf_counter() - t_start

    comparison_summary = {
        "benchmark": "OCR_THREE_WAY_COMPARISON",
        "split": split,
        "queries_count": len(selected_queries),
        "top_k": top_k,
        "pairwise_evidence_jaccard_mean": {
            "bm25_vs_trigram": round(float(np.mean(jaccards_bm25_trigram)), 4),
            "bm25_vs_bge": round(float(np.mean(jaccards_bm25_bge)), 4),
            "trigram_vs_bge": round(float(np.mean(jaccards_trigram_bge)), 4),
        },
        "pairwise_video_jaccard_mean": {
            "bm25_vs_trigram": round(float(np.mean(jaccards_vid_bm25_trigram)), 4),
            "bm25_vs_bge": round(float(np.mean(jaccards_vid_bm25_bge)), 4),
            "trigram_vs_bge": round(float(np.mean(jaccards_vid_trigram_bge)), 4),
        },
        "latency_stats_ms": {
            "bm25": {
                "p50": round(_percentile(latencies_bm25, 50), 2),
                "p95": round(_percentile(latencies_bm25, 95), 2),
                "mean": round(float(np.mean(latencies_bm25)), 2),
            },
            "trigram": {
                "p50": round(_percentile(latencies_trigram, 50), 2),
                "p95": round(_percentile(latencies_trigram, 95), 2),
                "mean": round(float(np.mean(latencies_trigram)), 2),
            },
            "bge": {
                "p50": round(_percentile(latencies_bge, 50), 2),
                "p95": round(_percentile(latencies_bge, 95), 2),
                "mean": round(float(np.mean(latencies_bge)), 2),
            },
        },
        "total_duration_sec": round(total_eval_duration, 2),
        "executed_at": _utc_now(),
    }

    # Write output artifacts
    comp_json_path = output_dir / f"ocr_three_way_comparison_{split.lower()}.json"
    comp_md_path = output_dir / f"ocr_three_way_comparison_{split.lower()}.md"

    with open(comp_json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": comparison_summary, "queries": query_comparisons}, f, indent=2, ensure_ascii=False)

    # Write human-readable markdown
    with open(comp_md_path, "w", encoding="utf-8") as f:
        f.write(f"# Three-Way OCR Retrieval Comparison Report ({split})\n\n")
        f.write(f"- **Queries Evaluated**: {len(selected_queries)}\n")
        f.write(f"- **Top-K**: {top_k}\n")
        f.write(f"- **Executed At**: {comparison_summary['executed_at']}\n\n")
        f.write("## 1. Pairwise Evidence (OCR Item) Overlap (Jaccard Index)\n\n")
        f.write("| Pair | Mean Evidence Jaccard | Mean Video Jaccard |\n")
        f.write("|---|:---:|:---:|\n")
        f.write(f"| **OCR BM25 vs OCR Trigram** | `{comparison_summary['pairwise_evidence_jaccard_mean']['bm25_vs_trigram']:.4f}` | `{comparison_summary['pairwise_video_jaccard_mean']['bm25_vs_trigram']:.4f}` |\n")
        f.write(f"| **OCR BM25 vs OCR BGE** | `{comparison_summary['pairwise_evidence_jaccard_mean']['bm25_vs_bge']:.4f}` | `{comparison_summary['pairwise_video_jaccard_mean']['bm25_vs_bge']:.4f}` |\n")
        f.write(f"| **OCR Trigram vs OCR BGE** | `{comparison_summary['pairwise_evidence_jaccard_mean']['trigram_vs_bge']:.4f}` | `{comparison_summary['pairwise_video_jaccard_mean']['trigram_vs_bge']:.4f}` |\n\n")
        f.write("## 2. Latency Benchmarks\n\n")
        f.write("| Lane | Mean (ms) | P50 (ms) | P95 (ms) |\n")
        f.write("|---|:---:|:---:|:---:|\n")
        f.write(f"| **OCR BM25** | `{comparison_summary['latency_stats_ms']['bm25']['mean']:.2f}` | `{comparison_summary['latency_stats_ms']['bm25']['p50']:.2f}` | `{comparison_summary['latency_stats_ms']['bm25']['p95']:.2f}` |\n")
        f.write(f"| **OCR Trigram** | `{comparison_summary['latency_stats_ms']['trigram']['mean']:.2f}` | `{comparison_summary['latency_stats_ms']['trigram']['p50']:.2f}` | `{comparison_summary['latency_stats_ms']['trigram']['p95']:.2f}` |\n")
        f.write(f"| **OCR BGE-M3** | `{comparison_summary['latency_stats_ms']['bge']['mean']:.2f}` | `{comparison_summary['latency_stats_ms']['bge']['p50']:.2f}` | `{comparison_summary['latency_stats_ms']['bge']['p95']:.2f}` |\n\n")
        f.write("## 3. Query Detailed Outputs\n\n")
        f.write("| Query ID | Query Text | BM25 Hits | Trigram Hits | BGE Hits | BM25 Top-1 | Trigram Top-1 | BGE Top-1 |\n")
        f.write("|---|---|:---:|:---:|:---:|---|---|---|\n")
        for qc in query_comparisons:
            t1_bm25 = (qc["top1_items"]["bm25"] or "-")[:25].replace("|", " ")
            t1_tri = (qc["top1_items"]["trigram"] or "-")[:25].replace("|", " ")
            t1_bge = (qc["top1_items"]["bge"] or "-")[:25].replace("|", " ")
            f.write(f"| `{qc['query_id']}` | {qc['query_text'][:30]} | {qc['counts']['bm25']} | {qc['counts']['trigram']} | {qc['counts']['bge']} | {t1_bm25} | {t1_tri} | {t1_bge} |\n")

    return comparison_summary
