from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_toml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("rb") as f:
        return tomllib.load(f)


def load_config(config_path: str | Path, base_path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(config_path)
    if base_path is None:
        candidate = config_path.parent / "base.toml"
        base_path = candidate if candidate.exists() else None
    base = load_toml(base_path) if base_path else {}
    override = load_toml(config_path)
    return _deep_merge(base, override)
