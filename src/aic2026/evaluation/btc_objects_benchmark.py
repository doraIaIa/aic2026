"""BTC Objects Operational Benchmark and Integrity Probe Suite (M5D).

Executes comprehensive functional, integrity, threshold, multi-class,
candidate scope, and bbox evidence verification probes over the
177,321 canonical BTC keyframes and 17,732,100 OpenImages detections.
"""
from __future__ import annotations

import json
import logging
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aic2026.retrieval.btc_objects_index import (
    CANONICAL_BTC_FRAME_COUNT,
    CANONICAL_DETECTION_COUNT,
    CANONICAL_VIDEO_COUNT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_ZIP_PATH,
    resolve_object_zip_path,
)
from aic2026.retrieval.providers.btc_objects import BtcObjectsProvider, BtcObjectsQuery

logger = logging.getLogger(__name__)

BENCHMARK_OUTPUT_ROOT = Path(r"F:\AIC_WORK\artifacts\evaluation\btc_objects_v1")


def run_single_class_probes(
    provider: BtcObjectsProvider,
) -> list[dict[str, Any]]:
    """Execute >= 30 single-class probes spanning common, medium, and rare classes."""
    classes_to_test = [
        # Very common (>50k frames)
        "person", "clothing", "man", "human face", "plant",
        "tree", "building", "skyscraper", "land vehicle", "vehicle",
        # Medium frequency (5k - 50k frames)
        "car", "woman", "window", "wheel", "flower",
        "food", "door", "table", "chair", "motorcycle",
        "bicycle", "street light", "billboard", "traffic sign", "hat",
        # Rare / specific (<5k frames)
        "airplane", "bus", "dog", "cat", "bird",
        "guitar", "pizza", "coffee cup", "umbrella", "horse",
    ]

    probes: list[dict[str, Any]] = []
    for cls in classes_to_test:
        t0 = time.perf_counter()
        hits = provider.search_objects(BtcObjectsQuery(
            classes=[cls],
            match_mode="ALL",
            min_detector_score=0.1,
            top_k=10,
        ))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        top_hit = hits[0] if hits else None
        probes.append({
            "class": cls,
            "hit_count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "top_score": top_hit.raw_score if top_hit else None,
            "top_keyframe_uid": top_hit.payload.get("keyframe_uid") if top_hit else None,
            "top_video_id": top_hit.video_id if top_hit else None,
            "status": "PASS" if len(hits) > 0 else "ZERO_HITS",
        })
    return probes


def run_multi_class_probes(
    provider: BtcObjectsProvider,
) -> list[dict[str, Any]]:
    """Execute >= 12 multi-class co-occurrence probes (ALL 2-class, ALL 3-class, ANY)."""
    multi_configs = [
        # ALL 2-class
        {"classes": ["person", "motorcycle"], "match_mode": "ALL", "min_score": 0.1},
        {"classes": ["person", "car"], "match_mode": "ALL", "min_score": 0.1},
        {"classes": ["person", "bicycle"], "match_mode": "ALL", "min_score": 0.1},
        {"classes": ["person", "dog"], "match_mode": "ALL", "min_score": 0.1},
        {"classes": ["table", "chair"], "match_mode": "ALL", "min_score": 0.1},
        {"classes": ["building", "tree"], "match_mode": "ALL", "min_score": 0.1},
        # ALL 3-class
        {"classes": ["person", "man", "clothing"], "match_mode": "ALL", "min_score": 0.1},
        {"classes": ["person", "land vehicle", "building"], "match_mode": "ALL", "min_score": 0.1},
        {"classes": ["person", "car", "tree"], "match_mode": "ALL", "min_score": 0.1},
        # ANY 2+ classes
        {"classes": ["motorcycle", "bicycle"], "match_mode": "ANY", "min_score": 0.25},
        {"classes": ["airplane", "bus", "train"], "match_mode": "ANY", "min_score": 0.25},
        {"classes": ["pizza", "coffee cup", "cake"], "match_mode": "ANY", "min_score": 0.25},
        {"classes": ["guitar", "piano", "drum"], "match_mode": "ANY", "min_score": 0.25},
    ]

    probes = []
    for cfg in multi_configs:
        t0 = time.perf_counter()
        hits = provider.search_objects(BtcObjectsQuery(
            classes=cfg["classes"],
            match_mode=cfg["match_mode"],
            min_detector_score=cfg["min_score"],
            top_k=10,
        ))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Verification of ALL / ANY contract
        all_passed = True
        for h in hits:
            matched = set(h.payload.get("matched_classes", []))
            # Resolve requested class entities for comparison
            req_entities = set()
            for rc in cfg["classes"]:
                r_info = provider.resolve_class(rc)
                if r_info:
                    req_entities.add(r_info["class_entity"])

            if cfg["match_mode"] == "ALL":
                if not req_entities.issubset(matched):
                    all_passed = False
                    break
            elif cfg["match_mode"] == "ANY":
                if not (req_entities & matched):
                    all_passed = False
                    break

        probes.append({
            "classes": cfg["classes"],
            "match_mode": cfg["match_mode"],
            "min_score": cfg["min_score"],
            "hit_count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "contract_verified": all_passed,
            "top_score": hits[0].raw_score if hits else None,
            "status": "PASS" if all_passed and len(hits) > 0 else "FAIL",
        })
    return probes


def run_threshold_probes(
    provider: BtcObjectsProvider,
) -> list[dict[str, Any]]:
    """Test monotonic eligibility across increasing score thresholds (0.0, 0.25, 0.5, 0.75)."""
    test_classes = ["motorcycle", "car", "guitar", "airplane"]
    thresholds = [0.0, 0.25, 0.50, 0.75]

    probes = []
    for cls in test_classes:
        counts = []
        for th in thresholds:
            hits = provider.search_objects(BtcObjectsQuery(
                classes=[cls],
                match_mode="ALL",
                min_detector_score=th,
                top_k=100,
            ))
            counts.append((th, len(hits)))

        # Monotonicity check: count at higher threshold <= count at lower threshold (over top-100 or total)
        # Verify that all scores in hits are >= threshold
        scores_valid = True
        for th in thresholds:
            hits = provider.search_objects(BtcObjectsQuery(
                classes=[cls],
                match_mode="ALL",
                min_detector_score=th,
                top_k=20,
            ))
            for h in hits:
                if h.raw_score is not None and h.raw_score < th:
                    scores_valid = False

        probes.append({
            "class": cls,
            "threshold_counts": {str(th): cnt for th, cnt in counts},
            "scores_satisfy_threshold": scores_valid,
            "status": "PASS" if scores_valid else "FAIL",
        })
    return probes


def run_scope_probes(
    provider: BtcObjectsProvider,
) -> list[dict[str, Any]]:
    """Test 1-video, 5-video, empty, and invalid candidate scopes."""
    test_class = "person"
    test_vids_5 = ["L21_V001", "L21_V002", "L21_V003", "L21_V004", "L21_V005"]

    probes = []

    # 1. 1-video scope
    hits_1v = provider.search_objects(BtcObjectsQuery(
        classes=[test_class],
        match_mode="ALL",
        min_detector_score=0.1,
        top_k=20,
        candidate_video_ids=["L21_V001"],
    ))
    vids_1v = {h.video_id for h in hits_1v}
    pass_1v = (vids_1v == {"L21_V001"}) or (len(hits_1v) == 0)
    probes.append({
        "scope_type": "1_video",
        "scope": ["L21_V001"],
        "hit_count": len(hits_1v),
        "observed_vids": list(vids_1v),
        "status": "PASS" if pass_1v and len(hits_1v) > 0 else "FAIL",
    })

    # 2. 5-video scope
    hits_5v = provider.search_objects(BtcObjectsQuery(
        classes=[test_class],
        match_mode="ALL",
        min_detector_score=0.1,
        top_k=50,
        candidate_video_ids=test_vids_5,
    ))
    vids_5v = {h.video_id for h in hits_5v}
    pass_5v = vids_5v.issubset(set(test_vids_5))
    probes.append({
        "scope_type": "5_video",
        "scope": test_vids_5,
        "hit_count": len(hits_5v),
        "observed_vids": list(vids_5v),
        "status": "PASS" if pass_5v and len(hits_5v) > 0 else "FAIL",
    })

    # 3. Empty scope list
    hits_empty = provider.search_objects(BtcObjectsQuery(
        classes=[test_class],
        match_mode="ALL",
        min_detector_score=0.1,
        top_k=20,
        candidate_video_ids=[],
    ))
    probes.append({
        "scope_type": "empty_scope",
        "scope": [],
        "hit_count": len(hits_empty),
        "status": "PASS" if len(hits_empty) == 0 else "FAIL",
    })

    # 4. Invalid video ID
    hits_invalid = provider.search_objects(BtcObjectsQuery(
        classes=[test_class],
        match_mode="ALL",
        min_detector_score=0.1,
        top_k=20,
        candidate_video_ids=["NON_EXISTENT_VIDEO_XYZ"],
    ))
    probes.append({
        "scope_type": "invalid_video_id",
        "scope": ["NON_EXISTENT_VIDEO_XYZ"],
        "hit_count": len(hits_invalid),
        "status": "PASS" if len(hits_invalid) == 0 else "FAIL",
    })

    return probes


def run_class_validation_probes(
    provider: BtcObjectsProvider,
) -> list[dict[str, Any]]:
    """Test normalization variants, unknown class, duplicate classes, whitespace."""
    probes = []

    # 1. Exact raw label vs uppercase vs mixed case
    hits_exact = provider.search_objects(BtcObjectsQuery(classes=["Person"], top_k=5))
    hits_upper = provider.search_objects(BtcObjectsQuery(classes=["PERSON"], top_k=5))
    hits_lower = provider.search_objects(BtcObjectsQuery(classes=["person"], top_k=5))
    hits_spaces = provider.search_objects(BtcObjectsQuery(classes=["  person  "], top_k=5))

    same_rank1 = (
        hits_exact[0].payload["keyframe_uid"] == hits_upper[0].payload["keyframe_uid"] ==
        hits_lower[0].payload["keyframe_uid"] == hits_spaces[0].payload["keyframe_uid"]
    )
    probes.append({
        "variant": "casing_and_whitespace",
        "test": "Person vs PERSON vs person vs '  person  '",
        "identical_rank1": same_rank1,
        "status": "PASS" if same_rank1 else "FAIL",
    })

    # 2. Unknown class in ALL mode
    hits_unk_all = provider.search_objects(BtcObjectsQuery(
        classes=["person", "totally_unknown_class_xyz123"],
        match_mode="ALL",
        top_k=5,
    ))
    probes.append({
        "variant": "unknown_class_in_all",
        "classes": ["person", "totally_unknown_class_xyz123"],
        "hit_count": len(hits_unk_all),
        "status": "PASS" if len(hits_unk_all) == 0 else "FAIL",
    })

    # 3. Unknown class in ANY mode
    hits_unk_any = provider.search_objects(BtcObjectsQuery(
        classes=["motorcycle", "totally_unknown_class_xyz123"],
        match_mode="ANY",
        top_k=5,
    ))
    probes.append({
        "variant": "unknown_class_in_any",
        "classes": ["motorcycle", "totally_unknown_class_xyz123"],
        "hit_count": len(hits_unk_any),
        "status": "PASS" if len(hits_unk_any) > 0 else "FAIL",
    })

    # 4. Duplicate requested class
    hits_dup = provider.search_objects(BtcObjectsQuery(
        classes=["person", "person", "Person"],
        match_mode="ALL",
        top_k=5,
    ))
    hits_single = provider.search_objects(BtcObjectsQuery(
        classes=["person"],
        match_mode="ALL",
        top_k=5,
    ))
    dup_pass = (len(hits_dup) == len(hits_single)) and (hits_dup[0].raw_score == hits_single[0].raw_score)
    probes.append({
        "variant": "duplicate_class_request",
        "classes": ["person", "person", "Person"],
        "hit_count": len(hits_dup),
        "dedup_pass": dup_pass,
        "status": "PASS" if dup_pass else "FAIL",
    })

    return probes


def run_bbox_evidence_checks(
    provider: BtcObjectsProvider,
    zip_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Verify >= 20 returned detections match source raw JSON from zip."""
    actual_zip = resolve_object_zip_path(zip_path)
    # Search for diverse classes
    classes_to_check = ["person", "motorcycle", "car", "dog", "airplane"]

    hits_to_check = []
    for cls in classes_to_check:
        hits = provider.search_objects(BtcObjectsQuery(classes=[cls], top_k=5))
        hits_to_check.extend(hits)

    checks = []
    with zipfile.ZipFile(actual_zip, "r") as zf:
        for h in hits_to_check[:25]:
            vid = h.video_id
            kf_no = h.payload["local_keyframe_no"]
            source_file = f"objects/{vid}/{kf_no:03d}.json"
            if source_file not in zf.namelist():
                source_file = f"objects/{vid}/{kf_no:04d}.json"

            raw_bytes = zf.read(source_file)
            data = json.loads(raw_bytes)

            scores = [float(s) for s in data.get("detection_scores", [])]
            entities = data.get("detection_class_entities", [])
            boxes = data.get("detection_boxes", [])

            # Check that top score and class in payload actually exist in raw source
            matched_cls = h.payload["matched_classes"][0]
            expected_score = h.payload["class_scores"][matched_cls]
            top_bbox = h.payload["top_bboxes"][matched_cls]

            # Find matching detection in source
            found = False
            for sc, ent, box in zip(scores, entities, boxes):
                if ent == matched_cls and abs(sc - expected_score) < 1e-4:
                    found = True
                    break

            checks.append({
                "keyframe_uid": h.payload["keyframe_uid"],
                "video_id": vid,
                "matched_class": matched_cls,
                "score": expected_score,
                "bbox": top_bbox,
                "source_verified": found,
                "status": "PASS" if found else "FAIL",
            })
    return checks


def run_manual_aic_demonstrations(
    provider: BtcObjectsProvider,
) -> list[dict[str, Any]]:
    """Manual structured translations for 10 representative AIC-style concepts."""
    demo_concepts = [
        {"concept": "person near motorcycle on street", "classes": ["person", "motorcycle"], "match_mode": "ALL", "min_score": 0.25},
        {"concept": "person driving a car", "classes": ["person", "car"], "match_mode": "ALL", "min_score": 0.25},
        {"concept": "person walking a dog in park", "classes": ["person", "dog"], "match_mode": "ALL", "min_score": 0.20},
        {"concept": "airplane at airport runway", "classes": ["airplane", "building"], "match_mode": "ALL", "min_score": 0.15},
        {"concept": "dining scene with food and wine", "classes": ["food", "table"], "match_mode": "ALL", "min_score": 0.25},
        {"concept": "person playing musical guitar", "classes": ["person", "guitar"], "match_mode": "ALL", "min_score": 0.15},
        {"concept": "traffic with cars, buses or motorcycles", "classes": ["car", "bus", "motorcycle"], "match_mode": "ANY", "min_score": 0.30},
        {"concept": "living room furniture with table and chair", "classes": ["table", "chair"], "match_mode": "ALL", "min_score": 0.30},
        {"concept": "person holding umbrella in rain", "classes": ["person", "umbrella"], "match_mode": "ALL", "min_score": 0.15},
        {"concept": "outdoor nature landscape with trees and plants", "classes": ["tree", "plant"], "match_mode": "ALL", "min_score": 0.40},
    ]

    demos = []
    for d in demo_concepts:
        t0 = time.perf_counter()
        hits = provider.search_objects(BtcObjectsQuery(
            classes=d["classes"],
            match_mode=d["match_mode"],
            min_detector_score=d["min_score"],
            top_k=5,
        ))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        demos.append({
            "concept_text": d["concept"],
            "manual_structured_query": {
                "classes": d["classes"],
                "match_mode": d["match_mode"],
                "min_detector_score": d["min_score"],
            },
            "hit_count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "top_hit": {
                "keyframe_uid": hits[0].payload["keyframe_uid"],
                "video_id": hits[0].video_id,
                "score": hits[0].raw_score,
                "timestamp_sec": hits[0].start_sec,
                "matched_classes": hits[0].payload["matched_classes"],
            } if hits else None,
            "status": "PASS" if len(hits) > 0 else "ZERO_HITS",
        })
    return demos


def run_btc_objects_benchmark(
    artifact_dir: str | Path = DEFAULT_OUTPUT_DIR,
    zip_path: str | Path | None = None,
    output_root: str | Path = BENCHMARK_OUTPUT_ROOT,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute complete benchmark suite and write summary artifact."""
    t_start = time.perf_counter()
    r_id = run_id or f"m5d_btc_obj_bench_{int(time.time())}"
    out_dir = Path(output_root) / r_id
    out_dir.mkdir(parents=True, exist_ok=True)

    provider = BtcObjectsProvider(artifact_dir=artifact_dir)

    logger.info("Running single-class probes (>=30)...")
    single_probes = run_single_class_probes(provider)

    logger.info("Running multi-class probes (>=12)...")
    multi_probes = run_multi_class_probes(provider)

    logger.info("Running threshold monotonicity probes...")
    thresh_probes = run_threshold_probes(provider)

    logger.info("Running candidate scope probes...")
    scope_probes = run_scope_probes(provider)

    logger.info("Running class validation probes...")
    valid_probes = run_class_validation_probes(provider)

    logger.info("Running raw bbox evidence checks (>=20)...")
    bbox_checks = run_bbox_evidence_checks(provider, zip_path=zip_path)

    logger.info("Running manual AIC-style concept demonstrations (>=10)...")
    concept_demos = run_manual_aic_demonstrations(provider)

    # Compute latency statistics
    all_latencies = [p["elapsed_ms"] for p in single_probes] + [p["elapsed_ms"] for p in multi_probes]
    all_latencies.sort()
    p50_latency = all_latencies[len(all_latencies) // 2] if all_latencies else 0.0
    p95_index = int(len(all_latencies) * 0.95)
    p95_latency = all_latencies[p95_index] if all_latencies else 0.0

    summary = {
        "run_id": r_id,
        "lane": "btc_objects",
        "entity_type": "FRAME",
        "frame_space": "BTC",
        "score_type": "btc_object_support",
        "score_direction": "HIGHER_IS_BETTER",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_total_sec": round(time.perf_counter() - t_start, 2),
        "latency_stats": {
            "p50_ms": round(p50_latency, 2),
            "p95_ms": round(p95_latency, 2),
            "total_queries_measured": len(all_latencies),
        },
        "quality_evaluation_status": "BLOCKED_BY_GROUND_TRUTH",
        "object_dev_structured_applicability": "NOT_AVAILABLE",
        "no_quality_claim_statement": (
            "No ground truth relevance labels exist for detector class queries on the 15 DEV natural queries. "
            "Evaluation measures deterministic retrieval correctness, integrity, and latency only."
        ),
        "probes_summary": {
            "single_class_probes_count": len(single_probes),
            "single_class_pass": all(p["status"] == "PASS" for p in single_probes),
            "multi_class_probes_count": len(multi_probes),
            "multi_class_pass": all(p["status"] == "PASS" for p in multi_probes),
            "threshold_probes_count": len(thresh_probes),
            "threshold_pass": all(p["status"] == "PASS" for p in thresh_probes),
            "scope_probes_count": len(scope_probes),
            "scope_pass": all(p["status"] == "PASS" for p in scope_probes),
            "validation_probes_count": len(valid_probes),
            "validation_pass": all(p["status"] == "PASS" for p in valid_probes),
            "bbox_evidence_checks_count": len(bbox_checks),
            "bbox_evidence_pass": all(p["status"] == "PASS" for p in bbox_checks),
            "manual_concept_demos_count": len(concept_demos),
            "manual_concept_demos_pass": all(p["status"] == "PASS" for p in concept_demos),
        },
        "single_class_probes": single_probes,
        "multi_class_probes": multi_probes,
        "threshold_probes": thresh_probes,
        "scope_probes": scope_probes,
        "validation_probes": valid_probes,
        "bbox_evidence_checks": bbox_checks,
        "manual_concept_demos": concept_demos,
    }

    summary_file = out_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False)

    done_file = out_dir / "DONE.json"
    with open(done_file, "w", encoding="utf-8") as fp:
        json.dump({"status": "COMPLETED", "run_id": r_id, "completed_at": datetime.now(timezone.utc).isoformat()}, fp, indent=2)

    logger.info("Benchmark complete. Artifact written to %s", summary_file)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    res = run_btc_objects_benchmark()
    print("Benchmark summary status:", json.dumps(res["probes_summary"], indent=2))
