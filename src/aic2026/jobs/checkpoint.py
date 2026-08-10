from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aic2026.core.atomic import atomic_write_json


def load_checkpoint(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {
            "schema_version": 1,
            "completed_item_ids": [],
            "failed": {},
        }
    raw = json.loads(p.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError(f"Unsupported checkpoint schema: {raw.get('schema_version')}")
    raw.setdefault("completed_item_ids", [])
    raw.setdefault("failed", {})
    return raw


def save_checkpoint(path: str | Path, checkpoint: dict[str, Any]) -> None:
    checkpoint = dict(checkpoint)
    checkpoint["schema_version"] = 1
    checkpoint["completed_item_ids"] = sorted(set(checkpoint.get("completed_item_ids", [])))
    atomic_write_json(path, checkpoint)
