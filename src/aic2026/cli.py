from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from aic2026.core.config import load_config
from aic2026.core.paths import PathContractError, PathResolver
from aic2026.jobs.artifact import validate_artifact
from aic2026.jobs.handlers import get_handler
from aic2026.jobs.manifest import build_shards, write_jsonl_manifest
from aic2026.jobs.models import ManifestItem
from aic2026.jobs.runner import run_shard
from aic2026.audit.discovery import run_discovery
from aic2026.audit.modalities import run_modalities
from aic2026.audit.mapping import run_frame_mapping
from aic2026.audit.clip import run_clip
from aic2026.audit.report import generate_reports
from aic2026.retrieval.clip_faiss import (
    build_clip_index,
    encode_clip_text,
    search_clip_index,
    write_clip_manifest,
)
from aic2026.evaluation.contract import EvalContractError, load_eval_dataset
from aic2026.evaluation.importers import import_combined_queries
from aic2026.evaluation.review import export_candidate_review
from aic2026.evaluation.runner import (
    EvalIntegrityError,
    run_baseline_evaluation,
    validate_eval_run_artifact,
)
from aic2026.asr.fts import build_asr_fts, search_asr
from aic2026.asr.manifest import AsrContractError, build_asr_pilot_manifest
from aic2026.asr.merge import merge_asr_shards
from aic2026.asr.review import export_asr_candidate_review
from aic2026.asr.shard import split_asr_shards
from aic2026.asr.whisper_runner import (
    AsrDependencyError,
    run_asr_shard,
    validate_asr_shard_artifact,
)
from aic2026.data_hub import (
    CustomKeyframeRegistry,
    CustomKeyframeValidator,
    VideoRegistry,
    VideoRegistryValidator,
    build_canonical_video_records,
    build_custom_and_qwen_records,
    materialize_custom_qwen_catalog,
    materialize_video_catalog,
)



def _json_print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    resolver = PathResolver.from_config(config)
    checks = []
    for name, path, must_exist in (
        ("data_root", resolver.data_root, True),
        ("work_root", resolver.work_root, False),
        ("artifact_root", resolver.artifact_root, False),
    ):
        exists = path.exists()
        writable = os.access(path, os.W_OK) if exists else os.access(path.parent if path.parent.exists() else Path.cwd(), os.W_OK)
        checks.append({"name": name, "path": str(path), "exists": exists, "writable_or_parent_writable": writable})
        if not exists and not must_exist:
            path.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    git = shutil.which("git")
    payload = {
        "python": sys.version.split()[0],
        "environment": config.get("environment", {}).get("name", "unknown"),
        "paths": checks,
        "ffmpeg": ffmpeg or "NOT_FOUND",
        "git": git or "NOT_FOUND",
    }
    _json_print(payload)
    data_ok = resolver.data_root.exists()
    return 0 if data_ok else 2


def cmd_demo_manifest(args: argparse.Namespace) -> int:
    items = [
        ManifestItem(
            item_id=f"demo-{i:06d}",
            source_relpath=f"demo/{i:06d}.txt",
            metadata={"ordinal": i},
        )
        for i in range(args.count)
    ]
    write_jsonl_manifest(args.out, items)
    print(f"wrote {len(items)} items -> {args.out}")
    return 0


def cmd_shard(args: argparse.Namespace) -> int:
    outputs = build_shards(args.manifest, args.out, task=args.task, shard_size=args.size)
    print(f"created {len(outputs)} shard(s) in {args.out}")
    for p in outputs:
        print(p)
    return 0


def cmd_run_shard(args: argparse.Namespace) -> int:
    handler = get_handler(args.handler)
    config = {"handler": args.handler, "checkpoint_every": args.checkpoint_every}
    marker = run_shard(
        args.shard,
        args.artifact_dir,
        handler,
        checkpoint_every=args.checkpoint_every,
        max_item_retries=args.max_item_retries,
        config=config,
    )
    _json_print(marker)
    return 0


def cmd_validate_artifact(args: argparse.Namespace) -> int:
    valid, errors, marker = validate_artifact(args.artifact_dir)
    _json_print({"valid": valid, "errors": errors, "marker": marker})
    return 0 if valid else 3


def cmd_status(args: argparse.Namespace) -> int:
    shard_dir = Path(args.shards)
    artifact_root = Path(args.artifacts)
    rows = []
    for shard_file in sorted(shard_dir.glob("shard-*.json")):
        raw = json.loads(shard_file.read_text(encoding="utf-8"))
        shard_id = raw["shard_id"]
        artifact_dir = artifact_root / shard_id
        valid, errors, marker = validate_artifact(artifact_dir)
        if valid:
            status = marker.get("status", "DONE") if marker else "DONE"
        elif (artifact_dir / "checkpoint.json").exists() or (artifact_dir / "results.partial.jsonl").exists():
            status = "PARTIAL"
        else:
            status = "PENDING"
        rows.append({
            "shard_id": shard_id,
            "status": status,
            "artifact_dir": str(artifact_dir),
            "validation_errors": errors if status not in {"PENDING", "PARTIAL"} else [],
        })
    _json_print(rows)
    return 0


def cmd_init_db(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).parent / "db" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema)
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    _json_print({"db": str(db_path), "foreign_keys": bool(fk), "integrity_check": integrity})
    return 0 if integrity == "ok" else 4


def cmd_audit_dataset(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    resolver = PathResolver.from_config(config)
    audit_dir = resolver.work_root / "audit"
    run_discovery(resolver.data_root, audit_dir)
    run_modalities(resolver.data_root, audit_dir)
    return 0

def cmd_audit_frame_mapping(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    resolver = PathResolver.from_config(config)
    audit_dir = resolver.work_root / "audit"
    run_frame_mapping(resolver.data_root, audit_dir)
    return 0

def cmd_audit_clip(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    resolver = PathResolver.from_config(config)
    audit_dir = resolver.work_root / "audit"
    run_clip(resolver.data_root, audit_dir)
    return 0

def cmd_audit_report(args: argparse.Namespace) -> int:
    audit_dir = Path(args.audit_dir)
    generate_reports(audit_dir)
    return 0


def cmd_build_clip_index(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    resolver = PathResolver.from_config(config)
    marker = build_clip_index(
        resolver.data_root,
        args.manifest,
        args.out,
        model_name=args.model_name,
        model_revision=args.model_revision,
        config_hash=args.config_hash,
        git_commit=args.git_commit,
    )
    _json_print(marker)
    return 0


def cmd_build_clip_manifest(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    resolver = PathResolver.from_config(config)
    count = write_clip_manifest(resolver.data_root, args.out)
    _json_print({"manifest": args.out, "videos": count})
    return 0


def cmd_search_clip_index(args: argparse.Namespace) -> int:
    import numpy as np

    query = np.load(args.query_vector)
    results = search_clip_index(args.index, query, args.top_k)
    _json_print([{"embedding_id": item_id, "score": score} for item_id, score in results])
    return 0


def cmd_search_clip_text(args: argparse.Namespace) -> int:
    query = encode_clip_text(
        args.query,
        model_name=args.model_name,
        pretrained=args.pretrained,
        device=args.device,
    )
    results = search_clip_index(args.index, query, args.top_k)
    _json_print([{"embedding_id": item_id, "score": score} for item_id, score in results])
    return 0


def cmd_validate_eval_dataset(args: argparse.Namespace) -> int:
    try:
        _, summary = load_eval_dataset(args.dataset)
    except EvalContractError as exc:
        _json_print({"valid": False, "error": str(exc)})
        return 2
    summary["valid"] = True
    summary["metric_note"] = (
        "BLOCKED_BY_GROUND_TRUTH" if summary["labeled"] == 0 else "Có query labeled để chấm"
    )
    _json_print(summary)
    return 0


def cmd_import_combined_queries(args: argparse.Namespace) -> int:
    try:
        dataset, summary = import_combined_queries(
            args.input,
            args.out,
            dataset_id=args.dataset_id,
            dataset_version=args.dataset_version,
            source_relpath=args.source_relpath,
            expected_sha256=args.expected_sha256,
        )
    except EvalContractError as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print({
        "status": "IMPORTED",
        "output": args.out,
        "source_provenance": dataset.get("source_provenance"),
        **summary,
    })
    return 0


def cmd_run_baseline_eval(args: argparse.Namespace) -> int:
    try:
        marker = run_baseline_evaluation(
            args.dataset,
            args.index_dir,
            args.out,
            split=args.split,
            experiment_name=args.experiment_name,
            pipeline_description=args.pipeline_description,
            model_name=args.model_name,
            pretrained=args.pretrained,
            device=args.device,
        )
    except (EvalContractError, EvalIntegrityError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print(marker)
    return 0


def cmd_eval_summary(args: argparse.Namespace) -> int:
    valid, errors, marker = validate_eval_run_artifact(args.run_dir)
    if not valid:
        _json_print({"valid": False, "errors": errors, "marker": marker})
        return 3
    summary_path = Path(args.run_dir) / str(marker["summary_file"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    _json_print({"valid": True, "summary": summary})
    return 0


def cmd_export_eval_candidates(args: argparse.Namespace) -> int:
    try:
        marker = export_candidate_review(args.dataset, args.run_dir, args.out)
    except (EvalContractError, EvalIntegrityError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print(marker)
    return 0


def cmd_build_asr_pilot_manifest(args: argparse.Namespace) -> int:
    try:
        resolver = PathResolver.from_config(load_config(args.config))
        inventory = args.video_inventory or resolver.work("audit/videos.jsonl")
        summary = build_asr_pilot_manifest(
            args.candidate_review,
            inventory,
            args.out,
            data_root=resolver.data_root,
            min_videos=args.min_videos,
            max_videos=args.max_videos,
            primary_rank=args.primary_rank,
            expanded_rank=args.expanded_rank,
        )
    except (AsrContractError, OSError, PathContractError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print(summary)
    return 0


def cmd_split_asr_shards(args: argparse.Namespace) -> int:
    try:
        outputs = split_asr_shards(args.manifest, args.out_dir, num_shards=args.num_shards)
    except (AsrContractError, OSError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print({"shard_count": len(outputs), "shards": [str(path) for path in outputs]})
    return 0


def cmd_run_asr_shard(args: argparse.Namespace) -> int:
    try:
        resolver = PathResolver.from_config(load_config(args.config))
        marker = run_asr_shard(
            args.shard,
            resolver.data_root,
            args.out_dir,
            model_size=args.model,
            model_revision=args.model_revision,
            language=args.language,
            task=args.task,
            beam_size=args.beam_size,
            vad_filter=args.vad_filter,
            word_timestamps=args.word_timestamps,
            device=args.device,
            compute_type=args.compute_type,
            limit_videos=args.limit_videos,
            force=args.force,
        )
    except (AsrContractError, AsrDependencyError, OSError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print(marker)
    return 0


def cmd_validate_asr_shard(args: argparse.Namespace) -> int:
    try:
        valid, errors, marker = validate_asr_shard_artifact(
            args.artifact_dir,
            duration_tolerance_sec=args.duration_tolerance_sec,
        )
    except (AsrContractError, OSError) as exc:
        _json_print({"valid": False, "errors": [str(exc)], "marker": None})
        return 3
    _json_print({"valid": valid, "errors": errors, "marker": marker})
    return 0 if valid else 3


def cmd_merge_asr_shards(args: argparse.Namespace) -> int:
    try:
        marker = merge_asr_shards(args.shards_dir, args.out_dir)
    except (AsrContractError, OSError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print(marker)
    return 0


def cmd_build_asr_fts(args: argparse.Namespace) -> int:
    try:
        summary = build_asr_fts(args.segments, args.out)
    except (AsrContractError, OSError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print(summary)
    return 0


def cmd_search_asr(args: argparse.Namespace) -> int:
    try:
        results = search_asr(args.index, args.query, top_k=args.top_k)
    except (AsrContractError, OSError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print(results)
    return 0


def cmd_export_asr_candidates(args: argparse.Namespace) -> int:
    try:
        marker = export_asr_candidate_review(
            args.dataset,
            args.index,
            args.out,
            top_k=args.top_k,
            metadata_path=args.metadata,
        )
    except (AsrContractError, EvalContractError, OSError) as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2
    _json_print(marker)
    return 0


def cmd_build_video_catalog(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        _json_print({"status": "REJECTED", "error": f"Input file not found: {input_path}"})
        return 2

    raw_items = []
    if input_path.suffix == ".jsonl":
        with open(input_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    raw_items.append(json.loads(line))
    elif input_path.suffix == ".json":
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_items = data if isinstance(data, list) else data.get("videos", [])
    else:
        _json_print({"status": "REJECTED", "error": f"Unsupported input format: {input_path.suffix}"})
        return 2

    try:
        records = build_canonical_video_records(
            raw_items,
            ordinal_space_id=args.ordinal_space_id,
            source_id=args.source_id,
        )
        v_file, s_file, p_file = materialize_video_catalog(
            records,
            output_dir=args.out,
            video_space_id=args.ordinal_space_id,
            validate=True,
        )
        registry = VideoRegistry.load_from_directory(args.out, validate=True)
        _json_print({
            "status": "BUILT",
            "video_count": registry.video_count(),
            "video_space_id": registry.video_space_id,
            "catalog_checksum": registry.catalog_checksum,
            "series_counts": registry.series_counts(),
            "output_directory": str(args.out),
            "files": {
                "videos": str(v_file),
                "source_registry": str(s_file),
                "video_space": str(p_file),
            },
        })
        return 0
    except Exception as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2


def cmd_validate_video_catalog(args: argparse.Namespace) -> int:
    try:
        registry = VideoRegistry.load_from_directory(args.catalog_dir, validate=False)
        validator = VideoRegistryValidator(
            expected_count=args.expected_count,
            expected_ordinal_space_id=args.ordinal_space_id,
        )
        result = validator.validate(registry.to_records(), registry.video_space)
        _json_print(result.to_dict())
        return 0 if result.is_valid else 3
    except Exception as exc:
        _json_print({"is_valid": False, "errors": [str(exc)]})
        return 3


def cmd_build_custom_qwen_catalog(args: argparse.Namespace) -> int:
    import pandas as pd

    # 1. Load VideoRegistry
    video_cat_dir = Path(args.video_catalog)
    if not video_cat_dir.exists():
        _json_print({"status": "REJECTED", "error": f"Video catalog directory not found: {video_cat_dir}"})
        return 2
    video_registry = VideoRegistry.load_from_directory(video_cat_dir, validate=True)

    # 2. Load custom keyframes (pkl or jsonl)
    custom_input = Path(args.custom_input)
    if not custom_input.exists():
        _json_print({"status": "REJECTED", "error": f"Custom keyframes input not found: {custom_input}"})
        return 2

    raw_custom = []
    if custom_input.suffix == ".pkl":
        df = pd.read_pickle(custom_input)
        raw_custom = df.to_dict(orient="records")
    elif custom_input.suffix == ".jsonl":
        with open(custom_input, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    raw_custom.append(json.loads(line))
    else:
        _json_print({"status": "REJECTED", "error": f"Unsupported custom input format: {custom_input.suffix}"})
        return 2

    # 3. Load Qwen shard
    qwen_input = Path(args.qwen_input)
    if not qwen_input.exists():
        _json_print({"status": "REJECTED", "error": f"Qwen input not found: {qwen_input}"})
        return 2

    raw_qwen = []
    with open(qwen_input, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                raw_qwen.append(json.loads(line))

    try:
        custom_records, qwen_records, missing_records = build_custom_and_qwen_records(
            raw_custom,
            raw_qwen,
            video_registry=video_registry,
            custom_space_id=args.custom_space_id,
        )
        files_dict = materialize_custom_qwen_catalog(
            custom_records,
            qwen_records,
            missing_records,
            output_dir=args.out,
            video_registry=video_registry,
            custom_space_id=args.custom_space_id,
            validate=True,
        )
        _json_print({
            "status": "BUILT",
            "custom_keyframe_count": len(custom_records),
            "qwen_valid_count": len(qwen_records),
            "qwen_missing_count": len(missing_records),
            "custom_space_id": args.custom_space_id,
            "output_directory": str(args.out),
            "files": {k: str(v) for k, v in files_dict.items()},
        })
        return 0
    except Exception as exc:
        _json_print({"status": "REJECTED", "error": str(exc)})
        return 2


def cmd_validate_custom_qwen_catalog(args: argparse.Namespace) -> int:
    try:
        video_registry = None
        if args.video_catalog:
            video_registry = VideoRegistry.load_from_directory(args.video_catalog, validate=False)

        registry = CustomKeyframeRegistry.load_from_directory(args.catalog_dir, video_registry=video_registry, validate=False)
        expected_video_count = args.expected_video_count if args.expected_video_count is not None else (video_registry.video_count() if video_registry else 873)
        validator = CustomKeyframeValidator(
            expected_keyframe_count=args.expected_count,
            expected_video_count=expected_video_count,
            video_registry=video_registry,
        )
        result = validator.validate(
            registry.to_custom_records(),
            registry.to_qwen_records(),
            missing_records=registry._missing_records,
            custom_space=registry.custom_space,
        )
        _json_print(result.to_dict())
        return 0 if result.is_valid else 3
    except Exception as exc:
        _json_print({"is_valid": False, "errors": [str(exc)]})
        return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aic", description="AIC 2026 reliability/control-plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build-video-catalog", help="xây dựng canonical videos.jsonl và video_space metadata")
    p.add_argument("--input", required=True, help="đường dẫn file JSON/JSONL chứa metadata video gốc (ví dụ asr_videos.jsonl)")
    p.add_argument("--out", required=True, help="thư mục output lưu canonical catalog")
    p.add_argument("--ordinal-space-id", default="v1_natural_series_video")
    p.add_argument("--source-id", default="canonical_video_universe_v1")
    p.set_defaults(func=cmd_build_video_catalog)

    p = sub.add_parser("validate-video-catalog", help="xác thực fail-closed cho canonical video catalog")
    p.add_argument("--catalog-dir", required=True, help="thư mục chứa videos.jsonl và video_space.json")
    p.add_argument("--expected-count", type=int, default=873)
    p.add_argument("--ordinal-space-id", default="v1_natural_series_video")
    p.set_defaults(func=cmd_validate_video_catalog)

    p = sub.add_parser("build-custom-qwen-catalog", help="xây dựng canonical custom_keyframes và qwen_semantics metadata")
    p.add_argument("--custom-input", required=True, help="đường dẫn df_keyframes.pkl hoặc jsonl")
    p.add_argument("--qwen-input", required=True, help="đường dẫn shard_000.jsonl")
    p.add_argument("--video-catalog", required=True, help="thư mục chứa canonical video catalog (M1A)")
    p.add_argument("--out", required=True, help="thư mục output")
    p.add_argument("--custom-space-id", default="custom_keyframes_v1")
    p.set_defaults(func=cmd_build_custom_qwen_catalog)

    p = sub.add_parser("validate-custom-qwen-catalog", help="xác thực fail-closed cho custom keyframes và Qwen catalog")
    p.add_argument("--catalog-dir", required=True, help="thư mục catalog custom/qwen")
    p.add_argument("--video-catalog", help="thư mục video catalog để đối soát ordinal")
    p.add_argument("--expected-count", type=int, default=116767)
    p.add_argument("--expected-video-count", type=int, help="số video kỳ vọng (mặc định 873 hoặc từ video catalog)")
    p.set_defaults(func=cmd_validate_custom_qwen_catalog)

    p = sub.add_parser("doctor", help="check environment/path prerequisites")
    p.add_argument("--config", required=True)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("demo-manifest", help="create a synthetic manifest for testing")
    p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=120)
    p.set_defaults(func=cmd_demo_manifest)

    p = sub.add_parser("shard", help="split a JSONL manifest into deterministic shard files")
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--task", required=True)
    p.set_defaults(func=cmd_shard)

    p = sub.add_parser("run-shard", help="run/resume a shard using a registered handler")
    p.add_argument("--shard", required=True)
    p.add_argument("--artifact-dir", required=True)
    p.add_argument("--handler", default="echo")
    p.add_argument("--checkpoint-every", type=int, default=50)
    p.add_argument("--max-item-retries", type=int, default=2)
    p.set_defaults(func=cmd_run_shard)

    p = sub.add_parser("validate-artifact", help="verify DONE marker, count and checksum")
    p.add_argument("--artifact-dir", required=True)
    p.set_defaults(func=cmd_validate_artifact)

    p = sub.add_parser("status", help="show PENDING/PARTIAL/DONE state for shard directory")
    p.add_argument("--shards", required=True)
    p.add_argument("--artifacts", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("init-db", help="initialize the local SQLite authority database")
    p.add_argument("--db", required=True)
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("audit-dataset", help="run read-only filesystem discovery, video, and keyframe inventory")
    p.add_argument("--config", required=True)
    p.set_defaults(func=cmd_audit_dataset)

    p = sub.add_parser("audit-frame-mapping", help="verify BTC frame index mappings against decoded frames")
    p.add_argument("--config", required=True)
    p.set_defaults(func=cmd_audit_frame_mapping)

    p = sub.add_parser("audit-clip", help="verify CLIP feature shapes and keyframe alignment")
    p.add_argument("--config", required=True)
    p.set_defaults(func=cmd_audit_clip)

    p = sub.add_parser("audit-report", help="aggregate audit outputs into M0A_REPORT.md")
    p.add_argument("--audit-dir", required=True)
    p.set_defaults(func=cmd_audit_report)

    p = sub.add_parser("build-clip-manifest", help="tạo manifest CLIP từ layout canonical đã khóa")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_build_clip_manifest)

    p = sub.add_parser("build-clip-index", help="xây CLIP FAISS index từ manifest đã xác thực")
    p.add_argument("--config", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model-name", required=True)
    p.add_argument("--model-revision", required=True)
    p.add_argument("--config-hash", required=True)
    p.add_argument("--git-commit")
    p.set_defaults(func=cmd_build_clip_index)

    p = sub.add_parser("search-clip-index", help="truy vấn FAISS bằng vector CLIP tương thích")
    p.add_argument("--index", required=True)
    p.add_argument("--query-vector", required=True)
    p.add_argument("--top-k", type=int, default=20)
    p.set_defaults(func=cmd_search_clip_index)

    p = sub.add_parser("search-clip-text", help="truy vấn text bằng OpenCLIP ViT-B-32")
    p.add_argument("--index", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--top-k", type=int, default=20)
    p.add_argument("--model-name", default="ViT-B-32")
    p.add_argument("--pretrained", default="openai")
    p.add_argument("--device", default="cpu")
    p.set_defaults(func=cmd_search_clip_text)

    p = sub.add_parser("validate-eval-dataset", help="xác thực evaluation dataset theo contract versioned")
    p.add_argument("--dataset", required=True, help="file JSON evaluation dataset")
    p.set_defaults(func=cmd_validate_eval_dataset)

    p = sub.add_parser("import-combined-queries", help="import Group A combined TXT thành eval dataset chưa gán nhãn")
    p.add_argument("--input", required=True, help="file combined TXT UTF-8")
    p.add_argument("--out", required=True, help="file JSON dataset đầu ra")
    p.add_argument("--dataset-id", default="group-a-unlabeled")
    p.add_argument("--dataset-version", default="v1")
    p.add_argument("--source-relpath", help="đường dẫn nguồn tương đối để lưu provenance")
    p.add_argument("--expected-sha256", help="checksum nguồn cần khớp; sai checksum sẽ fail closed")
    p.set_defaults(func=cmd_import_combined_queries)

    p = sub.add_parser("run-baseline-eval", help="chạy CLIP-only evaluation trên đúng một split")
    p.add_argument("--dataset", required=True)
    p.add_argument("--index-dir", required=True, help="thư mục M1 index có DONE.json hợp lệ")
    p.add_argument("--out", required=True, help="thư mục artifact mới; không ghi đè run hoàn tất")
    p.add_argument("--split", required=True, choices=("dev", "holdout"))
    p.add_argument("--experiment-name", required=True)
    p.add_argument("--pipeline-description", default="CLIP-only ViT-B-32/openai baseline")
    p.add_argument("--model-name", default="ViT-B-32")
    p.add_argument("--pretrained", default="openai")
    p.add_argument("--device", default="cpu")
    p.set_defaults(func=cmd_run_baseline_eval)

    p = sub.add_parser("eval-summary", help="xác thực và hiển thị summary của evaluation run")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(func=cmd_eval_summary)

    p = sub.add_parser("export-eval-candidates", help="xuất CSV review candidates và failure sheet")
    p.add_argument("--dataset", required=True)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--out", required=True, help="thư mục artifact mới; không ghi đè artifact hoàn tất")
    p.set_defaults(func=cmd_export_eval_candidates)

    p = sub.add_parser("build-asr-pilot-manifest", help="tạo ASR pilot manifest từ Group A candidates")
    p.add_argument("--config", required=True, help="config chứa data_root/work_root")
    p.add_argument("--candidate-review", required=True, help="candidate_review.csv đã validate")
    p.add_argument("--video-inventory", help="videos.jsonl; mặc định <work_root>/audit/videos.jsonl")
    p.add_argument("--out", required=True, help="ASR pilot manifest JSONL mới")
    p.add_argument("--min-videos", type=int, default=100)
    p.add_argument("--max-videos", type=int, default=250)
    p.add_argument("--primary-rank", type=int, default=10)
    p.add_argument("--expanded-rank", type=int, default=20)
    p.set_defaults(func=cmd_build_asr_pilot_manifest)

    p = sub.add_parser("split-asr-shards", help="chia ASR manifest thành shard portable")
    p.add_argument("--manifest", required=True)
    p.add_argument("--num-shards", type=int, required=True)
    p.add_argument("--out-dir", required=True)
    p.set_defaults(func=cmd_split_asr_shards)

    p = sub.add_parser("run-asr-shard", help="chạy/resume faster-whisper trên một ASR shard")
    p.add_argument("--config", required=True, help="config local/Colab/Kaggle chứa data_root")
    p.add_argument("--shard", required=True)
    p.add_argument("--out-dir", required=True, help="artifact directory riêng cho shard")
    p.add_argument("--model", default="medium")
    p.add_argument("--model-revision", default="medium")
    p.add_argument("--language", default="vi")
    p.add_argument("--task", default="transcribe", choices=("transcribe", "translate"))
    p.add_argument("--beam-size", type=int, default=5)
    p.add_argument("--vad-filter", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--word-timestamps", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--compute-type", help="mặc định cuda=float16, cpu=int8")
    p.add_argument("--limit-videos", type=int, help="smoke-only: chỉ xử lý N video đầu của shard")
    p.add_argument("--force", action="store_true", help="archive artifact cũ rồi chạy version mới")
    p.set_defaults(func=cmd_run_asr_shard)

    p = sub.add_parser("validate-asr-shard", help="validate DONE/checksum/count/timestamp của ASR shard")
    p.add_argument("--artifact-dir", required=True)
    p.add_argument("--duration-tolerance-sec", type=float, default=1.0)
    p.set_defaults(func=cmd_validate_asr_shard)

    p = sub.add_parser("merge-asr-shards", help="validate và merge immutable ASR shard artifacts")
    p.add_argument("--shards-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.set_defaults(func=cmd_merge_asr_shards)

    p = sub.add_parser("build-asr-fts", help="xây SQLite FTS5 từ ASR segments")
    p.add_argument("--segments", required=True)
    p.add_argument("--out", required=True, help="artifact directory mới chứa SQLite index + DONE/checksum")
    p.set_defaults(func=cmd_build_asr_fts)

    p = sub.add_parser("search-asr", help="tìm ASR segments độc lập bằng BM25")
    p.add_argument("--index", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--top-k", type=int, default=20)
    p.set_defaults(func=cmd_search_asr)

    p = sub.add_parser("export-asr-candidates", help="xuất ASR-only review CSV cho eval queries")
    p.add_argument("--dataset", required=True, help="evaluation dataset JSON")
    p.add_argument("--index", required=True, help="ASR FTS artifact directory")
    p.add_argument("--out", required=True, help="review artifact directory mới")
    p.add_argument("--top-k", type=int, default=20)
    p.add_argument("--metadata", help="M1 metadata JSONL để map nearest verified keyframe")
    p.set_defaults(func=cmd_export_asr_candidates)

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
