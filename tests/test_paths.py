from pathlib import Path

import pytest

from aic2026.core.paths import PathContractError, PathResolver, normalize_relpath


def test_normalize_relative_path():
    assert normalize_relpath(r"Videos\L01_V001.mp4") == "Videos/L01_V001.mp4"


def test_reject_absolute_windows_path():
    with pytest.raises(PathContractError):
        normalize_relpath(r"G:\AIC_2026\Videos\L01_V001.mp4")


def test_reject_parent_escape():
    with pytest.raises(PathContractError):
        normalize_relpath("../secret.txt")


def test_resolver_joins_relative(tmp_path: Path):
    resolver = PathResolver(tmp_path / "data", tmp_path / "work", tmp_path / "artifacts")
    assert resolver.source("Videos/a.mp4") == tmp_path / "data" / "Videos" / "a.mp4"
