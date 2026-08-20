"""M6 — Compare Mode & Lane Diagnostics Benchmark Suite.

Executes deterministic multi-lane retrieval evaluations over the DEV query set,
computes video-level overlap and set-algebra diagnostics, and runs functional
structured and partial-failure probes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aic2026.core.hashing import sha256_file
from aic2026.search.api import AsrSearchApi
from aic2026.search.compare import (
    CompareLaneConfig,
    CompareOrchestrator,
    LaneStatus,
)

logger = logging.getLogger(__name__)

DEFAULT_DATASET_DIR = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1")
DEFAULT_OUTPUT_ROOT = Path(r"F:\AIC_WORK\artifacts\evaluation\compare_v1")
DEFAULT_DB_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")

DETERMINISTIC_FREE_TEXT_PROFILE: list[dict[str, Any]] = [
    {"lane": "siglip_custom", "enabled": True, "options": {}},
    {"lane": "btc_clip", "enabled": True, "options": {}},
    {"lane": "asr_bm25", "enabled": True, "options": {}},
    {"lane": "asr_bge", "enabled": True, "options": {}},
    {"lane": "ocr_bm25", "enabled": True, "options": {}},
    {"lane": "ocr_trigram", "enabled": True, "options": {}},
    {"lane": "ocr_bge", "enabled": True, "options": {}},
    {"lane": "media_bm25", "enabled": True, "options": {}},
    {"lane": "qwen_bm25", "enabled": True, "options": {}},
    {"lane": "qwen_bge", "enabled": True, "options": {"field": "full_text"}},
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, pct))


def run_compare_dev_benchmark(
    database_path: str | Path = DEFAULT_DB_PATH,
    dataset_dir: str | Path = DEFAULT_DATASET_DIR,
    output_dir: str | Path | None = None,
    *,
    split: str = "DEV",
    top_k: int = 20,
    lane_profile: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute multi-lane Compare evaluation across all DEV queries."""
    database_path = Path(database_path)
    dataset_dir = Path(dataset_dir)

    if output_dir is None:
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        out_dir = DEFAULT_OUTPUT_ROOT / run_id
    else:
        out_dir = Path(output_dir)

    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = dataset_dir / "query_manifest.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing query manifest: {manifest_path}")

    dataset_checksum = sha256_file(manifest_path)
    queries = [json.loads(line) for line in open(manifest_path, "r", encoding="utf-8")]
    selected_queries = [q for q in queries if q.get("split", "DEV") == split]

    # Initialize AsrSearchApi adapter for execution
    api = AsrSearchApi(database_path)
    orchestrator = CompareOrchestrator(api)

    profile_configs = [
        CompareLaneConfig(lane=item["lane"], enabled=item.get("enabled", True), options=item.get("options", {}))
        for item in (lane_profile or DETERMINISTIC_FREE_TEXT_PROFILE)
    ]

    per_query_records: list[dict[str, Any]] = []
    lane_latencies: dict[str, list[float]] = {cfg.lane: [] for cfg in profile_configs}
    lane_status_counts: dict[str, dict[str, int]] = {
        cfg.lane: {"OK": 0, "EMPTY": 0, "ERROR": 0, "UNAVAILABLE": 0, "SKIPPED": 0}
        for cfg in profile_configs
    }
    lane_result_counts: dict[str, list[int]] = {cfg.lane: [] for cfg in profile_configs}
    lane_unique_video_counts: dict[str, list[int]] = {cfg.lane: [] for cfg in profile_configs}
    union_counts: list[int] = []

    for q in selected_queries:
        qid = q.get("query_id") or q.get("id") or "UNKNOWN"
        qtext = q.get("query_text") or q.get("query") or q.get("text") or ""

        t0 = time.perf_counter()
        resp = orchestrator.execute_compare(
            query=qtext,
            lanes=profile_configs,
            top_k=top_k,
            query_id=qid,
        )
        total_q_latency = (time.perf_counter() - t0) * 1000

        per_lane_summary = {}
        for l_res in resp.get("lanes", []):
            lname = l_res["lane"]
            lstatus = l_res["status"]
            llatency = l_res["latency_ms"]
            lcount = l_res["result_count"]
            vids = {h.get("video_id") for h in l_res.get("results", []) if h.get("video_id")}
            unique_vids = len(vids)

            if lname in lane_latencies:
                lane_latencies[lname].append(llatency)
                lane_result_counts[lname].append(lcount)
                lane_unique_video_counts[lname].append(unique_vids)
                if lstatus in lane_status_counts[lname]:
                    lane_status_counts[lname][lstatus] += 1
                elif lstatus == "SKIPPED_INVALID_CONFIG":
                    lane_status_counts[lname]["SKIPPED"] += 1

            per_lane_summary[lname] = {
                "status": lstatus,
                "latency_ms": llatency,
                "result_count": lcount,
                "unique_videos": unique_vids,
                "error": l_res.get("error"),
            }

        diag = resp.get("diagnostics", {})
        union_counts.append(diag.get("video_union_count", 0))

        record = {
            "query_id": qid,
            "query_text": qtext,
            "overall_status": resp.get("status"),
            "total_latency_ms": round(total_q_latency, 2),
            "lanes": per_lane_summary,
            "diagnostics": diag,
        }
        per_query_records.append(record)

    # Write per_query.jsonl
    with open(out_dir / "per_query.jsonl", "w", encoding="utf-8") as f:
        for r in per_query_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Aggregate lane stats
    per_lane_stats: dict[str, Any] = {}
    for cfg in profile_configs:
        lname = cfg.lane
        lats = lane_latencies.get(lname, [])
        rcounts = lane_result_counts.get(lname, [])
        uvids = lane_unique_video_counts.get(lname, [])
        per_lane_stats[lname] = {
            "executed_queries": len(lats),
            "status_counts": lane_status_counts.get(lname, {}),
            "latency_p50_ms": round(_percentile(lats, 50), 2),
            "latency_p95_ms": round(_percentile(lats, 95), 2),
            "mean_result_count": round(float(np.mean(rcounts)), 2) if rcounts else 0.0,
            "mean_unique_videos": round(float(np.mean(uvids)), 2) if uvids else 0.0,
        }

    summary = {
        "benchmark": "compare_dev_v1",
        "timestamp": _utc_now(),
        "dataset_checksum": dataset_checksum,
        "split": split,
        "total_queries": len(selected_queries),
        "scored_queries": 0,
        "unscored_queries": len(selected_queries),
        "quality_status": "BLOCKED_BY_GROUND_TRUTH",
        "top_k": top_k,
        "selected_lanes": [cfg.lane for cfg in profile_configs],
        "mean_video_union_count": round(float(np.mean(union_counts)), 2) if union_counts else 0.0,
        "per_lane_stats": per_lane_stats,
    }

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    manifest = {
        "benchmark": "M6_COMPARE_MODE",
        "created_at": _utc_now(),
        "dataset_dir": str(dataset_dir),
        "output_dir": str(out_dir),
        "files": ["per_query.jsonl", "summary.json", "manifest.json", "DONE"],
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    with open(out_dir / "DONE", "w", encoding="utf-8") as f:
        f.write("DONE\n")

    return summary


def run_structured_functional_probes(
    database_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Execute >= 5 qwen_structured, >= 5 btc_objects, and >= 3 combined sessions."""
    api = AsrSearchApi(Path(database_path))
    orchestrator = CompareOrchestrator(api)

    qwen_probes = [
        {"query": "người lái xe trên đường", "options": {"objects": "person, car", "scenes": "street"}},
        {"query": "hai con chó chơi đùa", "options": {"objects": "dog", "counts": "two", "actions": "playing"}},
        {"query": "tòa nhà cao tầng ban ngày", "options": {"objects": "building, skyscraper", "scenes": "outdoor"}},
        {"query": "cô gái mặc áo đỏ", "options": {"objects": "woman", "attributes": "red shirt"}},
        {"query": "xe máy chạy trên phố", "options": {"objects": "motorcycle", "relations": "on the street"}},
    ]

    btc_probes = [
        {"query": "person motorcycle", "options": {"classes": ["Person", "Motorcycle"], "match_mode": "ALL", "min_detector_score": 0.1}},
        {"query": "car tree", "options": {"classes": ["Car", "Tree"], "match_mode": "ALL", "min_detector_score": 0.1}},
        {"query": "table chair", "options": {"classes": ["Table", "Chair"], "match_mode": "ALL", "min_detector_score": 0.1}},
        {"query": "bus or train", "options": {"classes": ["Bus", "Train"], "match_mode": "ANY", "min_detector_score": 0.2}},
        {"query": "person dog", "options": {"classes": ["Person", "Dog"], "match_mode": "ALL", "min_detector_score": 0.1}},
    ]

    combined_probes = [
        {
            "query": "người và xe máy trên đường",
            "qwen_options": {"objects": "person, motorcycle", "scenes": "outdoor"},
            "btc_options": {"classes": ["Person", "Motorcycle"], "match_mode": "ALL", "min_detector_score": 0.1},
        },
        {
            "query": "xe hơi gần tòa nhà",
            "qwen_options": {"objects": "car, building", "relations": "near building"},
            "btc_options": {"classes": ["Car", "Building"], "match_mode": "ALL", "min_detector_score": 0.1},
        },
        {
            "query": "hai con chó trên bãi cỏ",
            "qwen_options": {"objects": "dog", "counts": "two", "scenes": "grass"},
            "btc_options": {"classes": ["Dog", "Plant"], "match_mode": "ANY", "min_detector_score": 0.15},
        },
    ]

    qwen_results = []
    for p in qwen_probes:
        res = orchestrator.execute_compare(
            query=p["query"],
            lanes=[
                CompareLaneConfig(lane="siglip_custom", enabled=True),
                CompareLaneConfig(lane="qwen_structured", enabled=True, options=p["options"]),
            ],
            top_k=10,
        )
        qwen_results.append(res)

    btc_results = []
    for p in btc_probes:
        res = orchestrator.execute_compare(
            query=p["query"],
            lanes=[
                CompareLaneConfig(lane="btc_clip", enabled=True),
                CompareLaneConfig(lane="btc_objects", enabled=True, options=p["options"]),
            ],
            top_k=10,
        )
        btc_results.append(res)

    combined_results = []
    for p in combined_probes:
        res = orchestrator.execute_compare(
            query=p["query"],
            lanes=[
                CompareLaneConfig(lane="siglip_custom", enabled=True),
                CompareLaneConfig(lane="qwen_structured", enabled=True, options=p["qwen_options"]),
                CompareLaneConfig(lane="btc_objects", enabled=True, options=p["btc_options"]),
            ],
            top_k=10,
        )
        combined_results.append(res)

    return {
        "qwen_probes_count": len(qwen_results),
        "btc_probes_count": len(btc_results),
        "combined_probes_count": len(combined_results),
        "all_qwen_ok": all(r.get("status") == "OK" for r in qwen_results),
        "all_btc_ok": all(r.get("status") == "OK" for r in btc_results),
        "all_combined_ok": all(r.get("status") == "OK" for r in combined_results),
    }
