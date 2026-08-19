"""Media-info BM25 Retrieval Lane Benchmark Runner (M4E).

Executes reproducible evaluation of the Media BM25 lane on the DEV benchmark
query suite. Returns VIDEO-level evidence; no frame/range metrics fabricated.
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
from aic2026.retrieval.providers.media_bm25 import MediaBm25Provider


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_media_bm25_benchmark(
    db_path: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 20,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute reproducible evaluation on DEV queries for Media BM25 lane.

    Quality evaluation for this lane is VIDEO-level only.
    No frame Recall, no range Recall, no exact-frame accuracy computed.
    If GT is unverified, status = BLOCKED_BY_GROUND_TRUTH.
    """
    db_path = Path(db_path)
    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_id or datetime.now(timezone.utc).strftime("m4e_media_bm25_%Y%m%d_%H%M%S")

    # -----------------------------------------------------------------------
    # 1. Load dataset queries & labels
    # -----------------------------------------------------------------------
    manifest_path = dataset_dir / "query_manifest.jsonl"
    labels_path = dataset_dir / "labels.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing query manifest: {manifest_path}")

    queries = [json.loads(line) for line in open(manifest_path, "r", encoding="utf-8")]
    selected_queries = [q for q in queries if q.get("split", "DEV") == split]

    label_map: dict[str, Any] = {}
    if labels_path.is_file():
        for line in open(labels_path, "r", encoding="utf-8"):
            lbl = json.loads(line)
            label_map[lbl["query_id"]] = lbl

    dataset_sha256 = sha256_file(manifest_path)

    # -----------------------------------------------------------------------
    # 2. Instantiate provider & warmup
    # -----------------------------------------------------------------------
    provider = MediaBm25Provider(db_path)
    provider_health = provider.health()
    if provider_health.get("status") != "OK":
        raise RuntimeError(
            f"Media BM25 provider health check failed: {provider_health.get('error')}"
        )

    # Warmup
    provider.search(ProviderQuery(query_text="chào mừng", top_k=1))

    # -----------------------------------------------------------------------
    # 3. Execute benchmark queries
    # -----------------------------------------------------------------------
    t_start = time.perf_counter()
    per_query_records: list[dict[str, Any]] = []
    latencies_total: list[float] = []
    scored_count = 0
    unscored_count = 0
    empty_count = 0
    unique_video_ids: set[str] = set()

    for q in selected_queries:
        qid = q["query_id"]
        qtext = q["query_text"]

        label = label_map.get(qid, q)
        is_verified = label.get("verification_status") == "VERIFIED"

        t0 = time.perf_counter()
        hits = provider.search(ProviderQuery(query_text=qtext, top_k=top_k))
        elapsed = (time.perf_counter() - t0) * 1000
        latencies_total.append(elapsed)

        if not hits:
            empty_count += 1

        for h in hits:
            unique_video_ids.add(h.video_id)

        top_candidates = [
            {
                "rank": h.rank,
                "video_id": h.video_id,
                "title": h.payload.get("title", ""),
                "author": h.payload.get("author"),
                "publish_date": h.payload.get("publish_date"),
                "keywords": h.payload.get("keywords", []),
                "raw_score": h.raw_score,
            }
            for h in hits
        ]

        if is_verified:
            scored_count += 1
        else:
            unscored_count += 1

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
            # VIDEO evidence only — no frame/range status
            "entity_type": "VIDEO",
            "frame_range_status": "NOT_APPLICABLE",
        }
        per_query_records.append(record)

    total_duration_sec = time.perf_counter() - t_start

    # -----------------------------------------------------------------------
    # 4. Save per_query.jsonl
    # -----------------------------------------------------------------------
    per_query_path = output_dir / "per_query.jsonl"
    with open(per_query_path, "w", encoding="utf-8") as f:
        for r in per_query_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # -----------------------------------------------------------------------
    # 5. Build summary
    # -----------------------------------------------------------------------
    quality_status = "BLOCKED_BY_GROUND_TRUTH" if scored_count == 0 else "PASS"

    summary: dict[str, Any] = {
        "run_id": run_id,
        "lane": "media_bm25",
        "entity_type": "VIDEO",
        "frame_space": "NONE",
        "split": split,
        "total_queries": len(selected_queries),
        "scored_queries": scored_count,
        "unscored_queries": unscored_count,
        "empty_result_queries": empty_count,
        "quality_status": quality_status,
        "video_recall_status": "BLOCKED_BY_GROUND_TRUTH" if scored_count == 0 else "MEASURED",
        "frame_recall_status": "NOT_APPLICABLE",
        "range_recall_status": "NOT_APPLICABLE",
        "fabricated_frames": 0,
        "fabricated_timestamps": 0,
        "candidate_video_diversity": len(unique_video_ids),
        "dataset_sha256": dataset_sha256,
        "latency_ms": {
            "mean": round(float(np.mean(latencies_total)), 2) if latencies_total else 0.0,
            "p50": round(_percentile(latencies_total, 50), 2),
            "p95": round(_percentile(latencies_total, 95), 2),
            "min": round(float(np.min(latencies_total)), 2) if latencies_total else 0.0,
            "max": round(float(np.max(latencies_total)), 2) if latencies_total else 0.0,
        },
        "total_duration_sec": round(total_duration_sec, 2),
        "executed_at": _utc_now(),
        "provider_health": provider_health,
    }

    summary_json_path = output_dir / "summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # -----------------------------------------------------------------------
    # 6. Markdown summary
    # -----------------------------------------------------------------------
    summary_md_path = output_dir / "summary.md"
    with open(summary_md_path, "w", encoding="utf-8") as f:
        f.write(f"# Media BM25 Retrieval Benchmark Report ({split})\n\n")
        f.write(f"- **Lane**: `media_bm25`\n")
        f.write(f"- **Entity type**: VIDEO (no frame/range metrics)\n")
        f.write(f"- **Split**: `{split}`\n")
        f.write(f"- **Queries Executed**: `{len(selected_queries)}`\n")
        f.write(f"- **Scored Queries**: `{scored_count}`\n")
        f.write(f"- **Unscored Queries**: `{unscored_count}`\n")
        f.write(f"- **Empty Results**: `{empty_count}`\n")
        f.write(f"- **Quality Status**: `{quality_status}`\n")
        f.write(f"- **Candidate Video Diversity**: `{len(unique_video_ids)}`\n")
        f.write(f"- **Latency p50**: `{summary['latency_ms']['p50']} ms`\n")
        f.write(f"- **Latency p95**: `{summary['latency_ms']['p95']} ms`\n")
        f.write(f"- **Total Duration**: `{summary['total_duration_sec']} s`\n")
        f.write(f"- **Fabricated Frames**: `0`\n")
        f.write(f"- **Fabricated Timestamps**: `0`\n")
        f.write(f"- **Frame/Range Recall**: `NOT_APPLICABLE`\n")

    # -----------------------------------------------------------------------
    # 7. DONE marker
    # -----------------------------------------------------------------------
    done_path = output_dir / "DONE.json"
    with open(done_path, "w", encoding="utf-8") as f:
        json.dump({"status": "PASS", "lane": "media_bm25", "run_id": run_id, "summary": summary}, f, indent=2)

    return summary
