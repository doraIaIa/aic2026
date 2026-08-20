"""Qwen Field-Aware BGE-Large Benchmark Runner (M5B2).

Evaluates the dense Qwen BGE retrieval provider against evaluation query manifests
(e.g., internal-verified-v1 DEV split) with standalone primary full_text benchmark
and independent per-field diagnostics (caption, objects_attributes, spatial_relations,
counts, scene, visible_actions, full_text).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Sequence

from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.retrieval.providers.qwen_bge import (
    ACCEPTED_FIELDS,
    BGE_DENSE_DIMENSION,
    BGE_LARGE_MODEL_ID,
    EXPECTED_FIELD_COUNTS,
    QwenBgeProvider,
)

logger = logging.getLogger(__name__)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_qwen_bge_benchmark(
    artifact_dir: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    field: str = "full_text",
    split: str = "DEV",
    top_k: int = 20,
    device: str = "auto",
    canonical_db_path: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute standalone Qwen BGE benchmark over a dataset manifest for a single explicit field."""
    if field not in ACCEPTED_FIELDS:
        raise ValueError(f"Invalid field '{field}'. Allowed fields: {ACCEPTED_FIELDS}")

    artifact_path = Path(artifact_dir)
    dataset_path = Path(dataset_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    manifest_path = dataset_path / "query_manifest.jsonl"
    labels_path = dataset_path / "query_labels.jsonl"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing query manifest: {manifest_path}")

    # Compute dataset checksums
    manifest_sha = _file_sha256(manifest_path)
    labels_sha = _file_sha256(labels_path) if labels_path.exists() else None

    # Load queries for target split
    queries: list[dict[str, Any]] = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item.get("split") == split or split == "ALL":
                    queries.append(item)

    if not queries:
        raise ValueError(f"No queries found for split '{split}' in {manifest_path}")

    provider = QwenBgeProvider(artifact_path, device=device, canonical_db_path=canonical_db_path)
    health = provider.health()

    actual_run_id = run_id or f"qwen_bge_{field}_{split.lower()}_{int(time.time())}"
    per_query_results: list[dict[str, Any]] = []
    encode_latencies_ms: list[float] = []
    total_latencies_ms: list[float] = []
    empty_result_count = 0
    all_hit_vids: set[str] = set()

    for q_item in queries:
        qid = q_item.get("query_id") or str(q_item.get("id"))
        qtext = q_item.get("query_text") or q_item.get("query") or ""
        vids = tuple(q_item.get("candidate_video_ids") or ())

        t0 = time.perf_counter()
        hits = provider.search(
            ProviderQuery(query_text=qtext, top_k=top_k, video_ids=vids),
            field=field,
            query_id=qid,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        total_latencies_ms.append(elapsed_ms)

        if not hits:
            empty_result_count += 1

        hit_vids = [h.video_id for h in hits]
        all_hit_vids.update(hit_vids)

        per_query_results.append({
            "query_id": qid,
            "query_text": qtext,
            "field": field,
            "top_k": top_k,
            "hit_count": len(hits),
            "latency_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        })

    def _p(vals: list[float], pct: float) -> float:
        if not vals:
            return 0.0
        sorted_vals = sorted(vals)
        k = (len(sorted_vals) - 1) * (pct / 100.0)
        f = int(k)
        c = min(f + 1, len(sorted_vals) - 1)
        d = k - f
        return round(sorted_vals[f] + d * (sorted_vals[c] - sorted_vals[f]), 2)

    summary: dict[str, Any] = {
        "run_id": actual_run_id,
        "lane_id": "qwen_bge",
        "field": field,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "split": split,
        "query_count": len(queries),
        "scored_query_count": 0,
        "unscored_query_count": len(queries),
        "empty_result_count": empty_result_count,
        "unique_candidate_videos": len(all_hit_vids),
        "quality_evaluation_status": "BLOCKED_BY_GROUND_TRUTH",
        "dataset": {
            "dir": str(dataset_path),
            "manifest_sha256": manifest_sha,
            "labels_sha256": labels_sha,
        },
        "model": {
            "model_id": BGE_LARGE_MODEL_ID,
            "dimension": BGE_DENSE_DIMENSION,
            "pooling": "CLS",
            "normalization": "L2",
            "max_length": 512,
            "configured_device": device,
            "resolved_device": health.get("resolved_device", "cpu"),
        },
        "latency_ms": {
            "p50": _p(total_latencies_ms, 50),
            "p90": _p(total_latencies_ms, 90),
            "p95": _p(total_latencies_ms, 95),
            "max": round(max(total_latencies_ms), 2) if total_latencies_ms else 0.0,
        },
    }

    # Write artifact files
    with open(out_path / "benchmark_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    with open(out_path / "per_query_results.json", "w", encoding="utf-8") as f:
        json.dump(per_query_results, f, indent=2, ensure_ascii=False)

    provider.close()
    return summary


def run_all_fields_diagnostic_benchmark(
    artifact_dir: str | Path,
    dataset_dir: str | Path,
    output_root: str | Path,
    *,
    split: str = "DEV",
    top_k: int = 20,
    device: str = "auto",
    canonical_db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run independent standalone benchmark across all 7 fields and summarize divergence/coverage."""
    out_root = Path(output_root)
    out_root.mkdir(parents=True, exist_ok=True)

    field_summaries: dict[str, Any] = {}
    for fld in ACCEPTED_FIELDS:
        fld_out = out_root / fld
        summary = run_qwen_bge_benchmark(
            artifact_dir,
            dataset_dir,
            fld_out,
            field=fld,
            split=split,
            top_k=top_k,
            device=device,
            canonical_db_path=canonical_db_path,
        )
        field_summaries[fld] = summary

    # Overall diagnostic summary
    diag_summary = {
        "benchmark_type": "independent_7_field_diagnostic",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "split": split,
        "fields": {
            fld: {
                "expected_rows": EXPECTED_FIELD_COUNTS.get(fld),
                "empty_result_count": field_summaries[fld]["empty_result_count"],
                "unique_candidate_videos": field_summaries[fld]["unique_candidate_videos"],
                "latency_p50_ms": field_summaries[fld]["latency_ms"]["p50"],
                "latency_p95_ms": field_summaries[fld]["latency_ms"]["p95"],
            }
            for fld in ACCEPTED_FIELDS
        },
    }

    with open(out_root / "seven_fields_diagnostic_summary.json", "w", encoding="utf-8") as f:
        json.dump(diag_summary, f, indent=2, ensure_ascii=False)

    return diag_summary
