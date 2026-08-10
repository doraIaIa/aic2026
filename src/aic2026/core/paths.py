from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class PathContractError(ValueError):
    pass


def normalize_relpath(value: str) -> str:
    raw = value.replace("\\", "/")
    p = PurePosixPath(raw)
    if p.is_absolute():
        raise PathContractError(f"Path must be relative, got absolute path: {value}")
    if any(part in {"", ".", ".."} for part in p.parts):
        raise PathContractError(f"Path contains unsafe segments: {value}")
    # Windows drive prefixes can survive as a first PurePosixPath segment.
    if p.parts and len(p.parts[0]) >= 2 and p.parts[0][1] == ":":
        raise PathContractError(f"Windows drive-prefixed path is not allowed: {value}")
    return p.as_posix()


@dataclass(frozen=True)
class PathResolver:
    data_root: Path
    work_root: Path
    artifact_root: Path

    @classmethod
    def from_config(cls, config: dict) -> "PathResolver":
        paths = config.get("paths", {})
        missing = [k for k in ("data_root", "work_root", "artifact_root") if not paths.get(k)]
        if missing:
            raise PathContractError(f"Missing configured path(s): {', '.join(missing)}")
        return cls(
            data_root=Path(paths["data_root"]).expanduser(),
            work_root=Path(paths["work_root"]).expanduser(),
            artifact_root=Path(paths["artifact_root"]).expanduser(),
        )

    def source(self, relpath: str) -> Path:
        return self.data_root / Path(normalize_relpath(relpath))

    def work(self, relpath: str) -> Path:
        return self.work_root / Path(normalize_relpath(relpath))

    def artifact(self, relpath: str) -> Path:
        return self.artifact_root / Path(normalize_relpath(relpath))
