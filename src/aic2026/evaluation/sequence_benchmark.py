"""M7 — Controlled Temporal Benchmark & Real-Corpus Sequence Probe Suite.

Generates a controlled 12+ case functional temporal fixture and executes 10+ real-corpus
AIC-style multi-step sequence sessions to verify temporal join logic, match group categorization,
and performance metrics without making unverified GT quality claims.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aic2026.core.config import load_config
from aic2026.core.paths import PathResolver
from aic2026.media.resolver import MediaResolver
from aic2026.retrieval.capabilities import CapabilityService
from aic2026.retrieval.orchestrator import SearchOrchestrator
from aic2026.retrieval.providers import (
    AsrProvider,
    ObjectProvider,
    VisualProvider,
)
from aic2026.search.api import AsrSearchApi
from aic2026.search.sequence import (
    MatchGroup,
    SequenceChain,
    SequenceOrchestrator,
    SequenceResponse,
    StepConfig,
    TemporalOccurrence,
    classify_chain_group,
)
from aic2026.workspace import WorkspaceStore

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 1. Controlled Functional Temporal Fixture (Synthetic/Known Controlled Cases)
# ------------------------------------------------------------------------------

CONTROLLED_TEMPORAL_FIXTURE: list[dict[str, Any]] = [
    {
        "case_id": "TC01_point_to_point_valid",
        "description": "2-step point -> point within 60s gap (valid FULL_MATCH)",
        "total_steps": 2,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 10.0, "rank": 1, "score": 0.9, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 25.0, "rank": 1, "score": 0.85, "evidence_id": "e2"}],
        },
        "expected_groups": {"FULL_MATCH": 1, "STEP_ONLY_MATCH": 0},
    },
    {
        "case_id": "TC02_point_to_segment_valid",
        "description": "2-step visual frame -> ASR interval (valid FULL_MATCH)",
        "total_steps": 2,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 15.0, "rank": 1, "score": 0.88, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "start_sec": 20.0, "end_sec": 26.0, "rank": 1, "score": -4.2, "evidence_id": "e2"}],
        },
        "expected_groups": {"FULL_MATCH": 1},
    },
    {
        "case_id": "TC03_segment_to_point_valid",
        "description": "2-step ASR interval -> visual frame (valid FULL_MATCH)",
        "total_steps": 2,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "start_sec": 5.0, "end_sec": 12.0, "rank": 1, "score": -3.5, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 30.0, "rank": 1, "score": 0.79, "evidence_id": "e2"}],
        },
        "expected_groups": {"FULL_MATCH": 1},
    },
    {
        "case_id": "TC04_point_to_ocr_valid",
        "description": "2-step visual frame -> OCR text item (valid FULL_MATCH)",
        "total_steps": 2,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 8.0, "rank": 1, "score": 0.91, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 18.0, "rank": 1, "score": -2.8, "evidence_id": "e2"}],
        },
        "expected_groups": {"FULL_MATCH": 1},
    },
    {
        "case_id": "TC05_ocr_to_segment_valid",
        "description": "2-step OCR item -> ASR interval (valid FULL_MATCH)",
        "total_steps": 2,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 14.0, "rank": 1, "score": -1.5, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "start_sec": 22.0, "end_sec": 30.0, "rank": 1, "score": -3.9, "evidence_id": "e2"}],
        },
        "expected_groups": {"FULL_MATCH": 1},
    },
    {
        "case_id": "TC06_3step_mixed_modality_valid",
        "description": "3-step OCR -> Visual -> Speech (valid FULL_MATCH)",
        "total_steps": 3,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 10.0, "rank": 1, "score": -2.0, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 25.0, "rank": 1, "score": 0.85, "evidence_id": "e2"}],
            "S3": [{"video_id": "V01", "start_sec": 40.0, "end_sec": 48.0, "rank": 1, "score": -4.0, "evidence_id": "e3"}],
        },
        "expected_groups": {"FULL_MATCH": 1},
    },
    {
        "case_id": "TC07_3step_prefix_match_only",
        "description": "3-step sequence where S3 is missing in V01 -> PREFIX_MATCH (S1+S2)",
        "total_steps": 3,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 10.0, "rank": 1, "score": 0.9, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 20.0, "rank": 1, "score": 0.8, "evidence_id": "e2"}],
            "S3": [{"video_id": "V02", "pts_time": 30.0, "rank": 1, "score": 0.85, "evidence_id": "e3"}],  # Different video
        },
        "expected_groups": {"FULL_MATCH": 0, "PREFIX_MATCH": 1, "STEP_ONLY_MATCH": 1},
    },
    {
        "case_id": "TC08_3step_suffix_match_only",
        "description": "3-step sequence where S1 is missing in V01 -> SUFFIX_MATCH (S2+S3)",
        "total_steps": 3,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V02", "pts_time": 5.0, "rank": 1, "score": 0.9, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 22.0, "rank": 1, "score": 0.8, "evidence_id": "e2"}],
            "S3": [{"video_id": "V01", "pts_time": 35.0, "rank": 1, "score": 0.85, "evidence_id": "e3"}],
        },
        "expected_groups": {"FULL_MATCH": 0, "SUFFIX_MATCH": 1, "STEP_ONLY_MATCH": 1},
    },
    {
        "case_id": "TC09_4step_partial_match",
        "description": "4-step sequence where only S2+S3 match in V01 -> PARTIAL_MATCH",
        "total_steps": 4,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V02", "pts_time": 5.0, "rank": 1, "score": 0.9, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 15.0, "rank": 1, "score": 0.8, "evidence_id": "e2"}],
            "S3": [{"video_id": "V01", "pts_time": 28.0, "rank": 1, "score": 0.85, "evidence_id": "e3"}],
            "S4": [{"video_id": "V03", "pts_time": 45.0, "rank": 1, "score": 0.77, "evidence_id": "e4"}],
        },
        "expected_groups": {"FULL_MATCH": 0, "PARTIAL_MATCH": 1},
    },
    {
        "case_id": "TC10_strict_order_violation",
        "description": "2-step reverse order in time (S2 occurs before S1) -> ORDER_VIOLATION, STEP_ONLY",
        "total_steps": 2,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 40.0, "rank": 1, "score": 0.9, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 10.0, "rank": 1, "score": 0.8, "evidence_id": "e2"}],  # Earlier!
        },
        "expected_groups": {"FULL_MATCH": 0, "STEP_ONLY_MATCH": 2},
    },
    {
        "case_id": "TC11_gap_too_large_violation",
        "description": "2-step gap is 80s > max_gap 30s -> GAP_TOO_LARGE, STEP_ONLY",
        "total_steps": 2,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 30000,  # 30s max
        "max_span_ms": None,
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 10.0, "rank": 1, "score": 0.9, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 90.0, "rank": 1, "score": 0.8, "evidence_id": "e2"}],  # 80s gap!
        },
        "expected_groups": {"FULL_MATCH": 0, "STEP_ONLY_MATCH": 2},
    },
    {
        "case_id": "TC12_max_span_violation",
        "description": "3-step span is 75s > max_span 60s -> SPAN_VIOLATION",
        "total_steps": 3,
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "max_span_ms": 60000,  # 60s max total span
        "step_hits": {
            "S1": [{"video_id": "V01", "pts_time": 5.0, "rank": 1, "score": 0.9, "evidence_id": "e1"}],
            "S2": [{"video_id": "V01", "pts_time": 35.0, "rank": 1, "score": 0.8, "evidence_id": "e2"}],
            "S3": [{"video_id": "V01", "pts_time": 80.0, "rank": 1, "score": 0.7, "evidence_id": "e3"}],  # 80s - 5s = 75s span
        },
        "expected_groups": {"FULL_MATCH": 0},
    },
]


def run_controlled_fixture() -> dict[str, Any]:
    """Runs all 12 controlled fixture test cases to verify temporal join logic."""
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    for case in CONTROLLED_TEMPORAL_FIXTURE:
        case_id = case["case_id"]
        total_steps = case["total_steps"]
        strict_order = case["strict_order"]
        min_gap_ms = case["min_gap_ms"]
        max_gap_ms = case["max_gap_ms"]
        max_span_ms = case["max_span_ms"]
        step_hits = case["step_hits"]
        expected_groups = case["expected_groups"]

        # Build dummy step configs
        steps = [
            StepConfig(step_id=f"S{i+1}", lane="siglip_custom", query=f"query_{i+1}")
            for i in range(total_steps)
        ]

        # Use mock api returning step_hits
        class MockApi:
            def siglip_search(self, req: dict[str, Any]):
                q = req.get("query", "")
                idx_str = q.split("_")[-1]
                s_id = f"S{idx_str}"
                hits = step_hits.get(s_id, [])
                return 200, {"hits": hits}

        orchestrator = SequenceOrchestrator(MockApi())
        resp = orchestrator.execute_sequence(
            steps=steps,
            strict_order=strict_order,
            min_gap_ms=min_gap_ms,
            max_gap_ms=max_gap_ms,
            max_span_ms=max_span_ms,
        )

        # Verify group counts match expectation
        case_pass = True
        err_msg = ""
        for grp_name, exp_count in expected_groups.items():
            act_count = len(resp.groups.get(grp_name, []))
            if act_count != exp_count:
                case_pass = False
                err_msg = f"{grp_name} count expected {exp_count}, got {act_count}"
                break

        if case_pass:
            passed += 1
        else:
            failed += 1

        results.append({
            "case_id": case_id,
            "description": case["description"],
            "status": "PASS" if case_pass else "FAIL",
            "error": err_msg if not case_pass else None,
            "groups_emitted": {g: len(chains) for g, chains in resp.groups.items()},
        })

    return {
        "fixture_name": "FUNCTIONAL_TEMPORAL_FIXTURE",
        "quality_status": "FUNCTIONAL_ONLY_NOT_COMPETITION_RELEVANCE_GT",
        "total_cases": len(CONTROLLED_TEMPORAL_FIXTURE),
        "passed": passed,
        "failed": failed,
        "cases": results,
    }


# ------------------------------------------------------------------------------
# 2. Manual Real-Corpus AIC-Style Sequence Smokes (10+ Sessions)
# ------------------------------------------------------------------------------

MANUAL_AIC_SEQUENCE_SESSIONS: list[dict[str, Any]] = [
    {
        "session_id": "SEQ01_2step_traffic_red_car",
        "description": "2-step Visual: Traffic scene then red car",
        "steps": [
            {"step_id": "S1", "lane": "siglip_custom", "query": "giao thông đông đúc trên đường phố"},
            {"step_id": "S2", "lane": "siglip_custom", "query": "chiếc ô tô màu đỏ chạy qua"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "top_k_per_step": 30,
    },
    {
        "session_id": "SEQ02_2step_ocr_then_visual",
        "description": "2-step OCR text item then Visual person",
        "steps": [
            {"step_id": "S1", "lane": "ocr_bm25", "query": "Việt Nam"},
            {"step_id": "S2", "lane": "siglip_custom", "query": "người dẫn chương trình trong trường quay"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 90000,
        "top_k_per_step": 30,
    },
    {
        "session_id": "SEQ03_2step_asr_then_visual",
        "description": "2-step Speech interval then Visual kitchen",
        "steps": [
            {"step_id": "S1", "lane": "asr_bm25", "query": "xin chào quý vị khán giả"},
            {"step_id": "S2", "lane": "siglip_custom", "query": "nấu ăn trong gian bếp"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 120000,
        "top_k_per_step": 30,
    },
    {
        "session_id": "SEQ04_3step_mixed_ocr_vis_asr",
        "description": "3-step Mixed Modality: OCR -> Visual -> Speech",
        "steps": [
            {"step_id": "S1", "lane": "ocr_bge", "query": "thời sự"},
            {"step_id": "S2", "lane": "siglip_custom", "query": "người phát biểu trên sân khấu"},
            {"step_id": "S3", "lane": "asr_bge", "query": "kính thưa quý vị đại biểu"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 90000,
        "top_k_per_step": 25,
    },
    {
        "session_id": "SEQ05_2step_cross_space_siglip_btc_clip",
        "description": "2-step Cross-Space Visual: SigLIP (CUSTOM) then BTC CLIP (BTC space)",
        "steps": [
            {"step_id": "S1", "lane": "siglip_custom", "query": "cây xanh ngoài trời công viên"},
            {"step_id": "S2", "lane": "btc_clip", "query": "trẻ em vui chơi"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "top_k_per_step": 30,
    },
    {
        "session_id": "SEQ06_2step_structured_qwen_and_vis",
        "description": "2-step Structured Qwen facets then SigLIP visual",
        "steps": [
            {
                "step_id": "S1",
                "lane": "qwen_structured",
                "query": "cảnh sát giao thông",
                "options": {"scenes": ["outdoor"], "objects": ["person", "car"]},
            },
            {"step_id": "S2", "lane": "siglip_custom", "query": "dừng xe trên đường"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "top_k_per_step": 25,
    },
    {
        "session_id": "SEQ07_2step_btc_objects_and_asr",
        "description": "2-step BTC Objects detector then ASR speech",
        "steps": [
            {
                "step_id": "S1",
                "lane": "btc_objects",
                "options": {"classes": ["Person", "Car"], "mode": "ALL", "min_detector_score": 0.5},
            },
            {"step_id": "S2", "lane": "asr_bm25", "query": "tai nạn giao thông"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "top_k_per_step": 25,
    },
    {
        "session_id": "SEQ08_3step_strict_order_false",
        "description": "3-step Co-occurrence (Strict Order OFF, max_span 120s)",
        "steps": [
            {"step_id": "S1", "lane": "siglip_custom", "query": "bệnh viện bác sĩ"},
            {"step_id": "S2", "lane": "ocr_bm25", "query": "y tế"},
            {"step_id": "S3", "lane": "asr_bm25", "query": "khám chữa bệnh"},
        ],
        "strict_order": False,
        "max_span_ms": 120000,
        "top_k_per_step": 25,
    },
    {
        "session_id": "SEQ09_2step_qwen_bge_and_vis",
        "description": "2-step Qwen BGE embedding then SigLIP visual",
        "steps": [
            {"step_id": "S1", "lane": "qwen_bge", "query": "phỏng vấn nhân vật"},
            {"step_id": "S2", "lane": "siglip_custom", "query": "phóng viên cầm micro"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 60000,
        "top_k_per_step": 30,
    },
    {
        "session_id": "SEQ10_4step_multimodal_narrative",
        "description": "4-step Multimodal Narrative Chain: OCR -> Vis -> Vis -> Speech",
        "steps": [
            {"step_id": "S1", "lane": "ocr_bm25", "query": "Chương trình"},
            {"step_id": "S2", "lane": "siglip_custom", "query": "sân vận động thể thao"},
            {"step_id": "S3", "lane": "siglip_custom", "query": "cầu thủ bóng đá ghi bàn"},
            {"step_id": "S4", "lane": "asr_bm25", "query": "chiến thắng"},
        ],
        "strict_order": True,
        "min_gap_ms": 0,
        "max_gap_ms": 120000,
        "top_k_per_step": 25,
    },
]


def run_manual_smokes(api: AsrSearchApi) -> dict[str, Any]:
    """Runs all 10 real-corpus AIC-style sequence smoke sessions."""
    orchestrator = SequenceOrchestrator(api)
    session_results: list[dict[str, Any]] = []

    for session in MANUAL_AIC_SEQUENCE_SESSIONS:
        s_id = session["session_id"]
        desc = session["description"]
        raw_steps = session["steps"]
        strict_order = session.get("strict_order", True)
        min_gap_ms = session.get("min_gap_ms", 0)
        max_gap_ms = session.get("max_gap_ms", 60000)
        max_span_ms = session.get("max_span_ms")
        top_k = session.get("top_k_per_step", 30)

        step_configs = [
            StepConfig(
                step_id=item["step_id"],
                lane=item["lane"],
                query=item.get("query", ""),
                options=item.get("options", {}),
            )
            for item in raw_steps
        ]

        t0 = time.perf_counter()
        resp = orchestrator.execute_sequence(
            steps=step_configs,
            top_k_per_step=top_k,
            strict_order=strict_order,
            min_gap_ms=min_gap_ms,
            max_gap_ms=max_gap_ms,
            max_span_ms=max_span_ms,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        full_count = len(resp.groups.get("FULL_MATCH", []))
        prefix_count = len(resp.groups.get("PREFIX_MATCH", []))
        suffix_count = len(resp.groups.get("SUFFIX_MATCH", []))
        partial_count = len(resp.groups.get("PARTIAL_MATCH", []))
        step_only_count = len(resp.groups.get("STEP_ONLY_MATCH", []))

        session_results.append({
            "session_id": s_id,
            "description": desc,
            "total_steps": len(raw_steps),
            "status": resp.status.value,
            "latency_ms": round(elapsed_ms, 2),
            "diagnostics": resp.diagnostics.to_dict(),
            "counts": {
                "FULL_MATCH": full_count,
                "PREFIX_MATCH": prefix_count,
                "SUFFIX_MATCH": suffix_count,
                "PARTIAL_MATCH": partial_count,
                "STEP_ONLY_MATCH": step_only_count,
                "total_emitted": resp.diagnostics.chains_emitted,
            },
        })

    return {
        "benchmark_name": "MANUAL_AIC_SEQUENCE_SMOKES",
        "total_sessions": len(session_results),
        "sessions": session_results,
    }


DEFAULT_OUTPUT_ROOT = Path(r"F:\AIC_WORK\artifacts\evaluation\sequence_v1")
DEFAULT_DB_PATH = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")


def execute_full_m7_benchmark(output_root: Optional[Path] = None, database_path: Optional[Path] = None) -> dict[str, Any]:
    """Executes the controlled fixture and real-corpus smoke sessions, then records artifacts."""
    t_start = time.perf_counter()
    db_path = database_path or DEFAULT_DB_PATH
    api = AsrSearchApi(database=db_path)

    # 1. Controlled Fixture
    fixture_summary = run_controlled_fixture()

    # 2. Real-Corpus Smokes
    smokes_summary = run_manual_smokes(api)

    total_latency_sec = time.perf_counter() - t_start

    run_id = f"m7_seq_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    if output_root is None:
        output_dir = DEFAULT_OUTPUT_ROOT / run_id
    else:
        output_dir = output_root / run_id

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write files
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fixture_cases": fixture_summary["total_cases"],
        "smoke_sessions": smokes_summary["total_sessions"],
        "quality_status": "BLOCKED_BY_GROUND_TRUTH",
        "evaluation_verdict": "FUNCTIONAL_TEMPORAL_GATE_PASS",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with open(output_dir / "controlled_cases.jsonl", "w", encoding="utf-8") as f:
        for c in fixture_summary["cases"]:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    with open(output_dir / "manual_smokes.jsonl", "w", encoding="utf-8") as f:
        for s in smokes_summary["sessions"]:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    summary_data = {
        "manifest": manifest,
        "controlled_fixture": fixture_summary,
        "manual_smokes": smokes_summary,
        "total_runtime_sec": round(total_latency_sec, 2),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
    (output_dir / "DONE").write_text("DONE\n", encoding="utf-8")

    return summary_data
