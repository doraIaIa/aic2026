from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from aic2026.core.config import load_config
from aic2026.core.paths import PathResolver
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

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aic", description="AIC 2026 reliability/control-plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
