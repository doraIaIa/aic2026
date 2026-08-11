import csv
import json
from pathlib import Path

import numpy as np
import pytest

faiss = pytest.importorskip("faiss")

from aic2026.retrieval.clip_faiss import (
    ClipIndexContractError,
    build_clip_index,
    search_clip_index,
    write_clip_manifest,
    encode_clip_text,
)


def _write_fixture(tmp_path: Path, *, second_n: int = 2) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    csv_dir = data_root / "data_extracted" / "map-keyframes"
    keyframe_dir = data_root / "data_extracted" / "keyframes" / "L01_V001"
    clip_dir = data_root / "data_extracted" / "clip-features-32"
    csv_dir.mkdir(parents=True)
    keyframe_dir.mkdir(parents=True)
    clip_dir.mkdir(parents=True)
    with (csv_dir / "L01_V001.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["n", "pts_time", "fps", "frame_idx"])
        writer.writeheader()
        writer.writerow({"n": 1, "pts_time": 0, "fps": 25, "frame_idx": 0})
        writer.writerow({"n": second_n, "pts_time": 3, "fps": 25, "frame_idx": 75})
    (keyframe_dir / "001.jpg").write_bytes(b"1")
    (keyframe_dir / "002.jpg").write_bytes(b"2")
    np.save(clip_dir / "L01_V001.npy", np.array([[1, 0], [0, 1]], dtype=np.float16))
    manifest = tmp_path / "clip_manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "video_id": "L01_V001",
                "csv_relpath": "data_extracted/map-keyframes/L01_V001.csv",
                "keyframe_dir_relpath": "data_extracted/keyframes/L01_V001",
                "clip_relpath": "data_extracted/clip-features-32/L01_V001.npy",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return data_root, manifest


def test_build_and_search_clip_index_preserves_locked_mapping(tmp_path: Path):
    data_root, manifest = _write_fixture(tmp_path)
    output = tmp_path / "index"
    marker = build_clip_index(
        data_root,
        manifest,
        output,
        model_name="test-clip",
        model_revision="test-revision",
        config_hash="abc",
    )
    rows = [json.loads(line) for line in (output / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["csv_n"] == 1 and rows[0]["clip_row"] == 0 and rows[0]["frame_idx"] == 0
    assert rows[0]["keyframe_relpath"].endswith("/001.jpg")
    assert rows[1]["csv_n"] == 2 and rows[1]["clip_row"] == 1 and rows[1]["frame_idx"] == 75
    assert rows[1]["keyframe_relpath"].endswith("/002.jpg")
    assert marker["processed_count"] == 2
    assert search_clip_index(output / "clip.index", np.array([1, 0]), 1)[0][0] == rows[0]["embedding_id"]


def test_build_clip_index_fails_closed_on_nonsequential_csv_n(tmp_path: Path):
    data_root, manifest = _write_fixture(tmp_path, second_n=3)
    with pytest.raises(ClipIndexContractError, match="clip_row=1"):
        build_clip_index(
            data_root,
            manifest,
            tmp_path / "index",
            model_name="test-clip",
            model_revision="test-revision",
            config_hash="abc",
        )


def test_write_clip_manifest_uses_only_relative_canonical_paths(tmp_path: Path):
    data_root, _ = _write_fixture(tmp_path)
    output = tmp_path / "manifest.jsonl"
    assert write_clip_manifest(data_root, output) == 1
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["video_id"] == "L01_V001"
    assert row["csv_relpath"] == "data_extracted/map-keyframes/L01_V001.csv"
    assert not Path(row["clip_relpath"]).is_absolute()


def test_encode_clip_text_rejects_empty_query_without_loading_model():
    with pytest.raises(ValueError, match="không được rỗng"):
        encode_clip_text("   ")
