from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.core.hashing import sha256_file
from aic2026.core.paths import normalize_relpath


class ClipIndexContractError(ValueError):
    """Dữ liệu CLIP vi phạm hợp đồng mapping đã khóa."""


def write_clip_manifest(data_root: str | Path, output_path: str | Path) -> int:
    """Tạo manifest M1 từ ba thư mục canonical đã được khóa ở M0."""
    root = Path(data_root)
    csv_dir = root / "data_extracted" / "map-keyframes"
    keyframe_root = root / "data_extracted" / "keyframes"
    clip_dir = root / "data_extracted" / "clip-features-32"
    for path in (csv_dir, keyframe_root, clip_dir):
        if not path.is_dir():
            raise ClipIndexContractError(f"Thiếu thư mục canonical: {path}")

    csv_ids = {path.stem for path in csv_dir.glob("*.csv")}
    keyframe_ids = {path.name for path in keyframe_root.iterdir() if path.is_dir()}
    clip_ids = {path.stem for path in clip_dir.glob("*.npy")}
    if not csv_ids or csv_ids != keyframe_ids or csv_ids != clip_ids:
        raise ClipIndexContractError(
            "Tập video giữa CSV, keyframe và CLIP không giống nhau: "
            f"CSV={len(csv_ids)}, keyframe={len(keyframe_ids)}, CLIP={len(clip_ids)}"
        )

    lines = []
    for video_id in sorted(csv_ids):
        record = {
            "video_id": video_id,
            "csv_relpath": f"data_extracted/map-keyframes/{video_id}.csv",
            "keyframe_dir_relpath": f"data_extracted/keyframes/{video_id}",
            "clip_relpath": f"data_extracted/clip-features-32/{video_id}.npy",
        }
        lines.append(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    atomic_write_text(output_path, "".join(lines))
    return len(lines)


def stable_embedding_id(keyframe_id: str) -> int:
    """Sinh ID dương 63-bit ổn định, độc lập với thứ tự duyệt file."""
    digest = hashlib.blake2b(keyframe_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & ((1 << 63) - 1)


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            required = {"video_id", "csv_relpath", "keyframe_dir_relpath", "clip_relpath"}
            missing = required.difference(record)
            if missing:
                raise ClipIndexContractError(
                    f"Dòng manifest {line_number} thiếu trường: {', '.join(sorted(missing))}"
                )
            for field in required - {"video_id"}:
                record[field] = normalize_relpath(str(record[field]))
            records.append(record)
    if not records:
        raise ClipIndexContractError("Manifest CLIP rỗng")
    video_ids = [str(record["video_id"]) for record in records]
    if len(video_ids) != len(set(video_ids)):
        raise ClipIndexContractError("Manifest CLIP chứa video_id trùng lặp")
    return records


def _validated_video_rows(data_root: Path, record: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    csv_path = data_root / record["csv_relpath"]
    keyframe_dir = data_root / record["keyframe_dir_relpath"]
    clip_path = data_root / record["clip_relpath"]
    for path in (csv_path, keyframe_dir, clip_path):
        if not path.exists():
            raise ClipIndexContractError(f"Thiếu đầu vào: {path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    vectors = np.load(clip_path, mmap_mode="r")
    if vectors.ndim != 2 or vectors.shape[0] != len(csv_rows):
        raise ClipIndexContractError(
            f"{record['video_id']}: CSV={len(csv_rows)}, CLIP shape={vectors.shape}"
        )

    # Google Drive có độ trễ cao; liệt kê một lần thay vì gọi stat cho từng ordinal.
    keyframe_names = {
        path.name for path in keyframe_dir.iterdir() if path.is_file() and path.suffix.lower() == ".jpg"
    }
    if len(keyframe_names) != len(csv_rows):
        raise ClipIndexContractError(
            f"{record['video_id']}: CSV={len(csv_rows)}, keyframe={len(keyframe_names)}"
        )

    metadata: list[dict[str, Any]] = []
    for clip_row, row in enumerate(csv_rows):
        try:
            ordinal = int(row["n"])
            frame_idx = int(row["frame_idx"])
            pts_time = float(row["pts_time"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ClipIndexContractError(
                f"{record['video_id']}: dòng CSV {clip_row + 2} không hợp lệ"
            ) from exc
        if ordinal != clip_row + 1:
            raise ClipIndexContractError(
                f"{record['video_id']}: clip_row={clip_row} phải ánh xạ n={clip_row + 1}, nhận n={ordinal}"
            )
        keyframe_name = f"{ordinal:03d}.jpg"
        if keyframe_name not in keyframe_names:
            raise ClipIndexContractError(
                f"{record['video_id']}: thiếu keyframe ordinal {keyframe_name}"
            )
        keyframe_id = f"{record['video_id']}:{ordinal}"
        metadata.append(
            {
                "embedding_id": stable_embedding_id(keyframe_id),
                "keyframe_id": keyframe_id,
                "video_id": record["video_id"],
                "csv_n": ordinal,
                "clip_row": clip_row,
                "frame_idx": frame_idx,
                "pts_time": pts_time,
                "keyframe_relpath": f"{record['keyframe_dir_relpath']}/{keyframe_name}",
            }
        )
    return np.asarray(vectors, dtype=np.float32), metadata


def _normalized(vectors: np.ndarray) -> np.ndarray:
    if not np.isfinite(vectors).all():
        raise ClipIndexContractError("Vector CLIP chứa NaN hoặc infinity")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ClipIndexContractError("Vector CLIP có norm bằng 0")
    return np.ascontiguousarray(vectors / norms, dtype=np.float32)


def build_clip_index(
    data_root: str | Path,
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    model_name: str,
    model_revision: str,
    config_hash: str,
    git_commit: str | None = None,
) -> dict[str, Any]:
    """Xây FAISS cosine index; DONE.json chỉ được ghi sau mọi kiểm tra."""
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError("M1 cần dependency faiss-cpu") from exc

    root = Path(data_root)
    manifest = Path(manifest_path)
    target = Path(output_dir)
    started_at = datetime.now(timezone.utc).isoformat()
    records = _load_manifest(manifest)
    target.mkdir(parents=True, exist_ok=True)
    if (target / "DONE.json").exists():
        raise FileExistsError(f"Artifact đã hoàn tất, không được ghi đè: {target}")

    dimension: int | None = None
    seen_ids: set[int] = set()
    all_vectors: list[np.ndarray] = []
    metadata: list[dict[str, Any]] = []
    for record in records:
        vectors, rows = _validated_video_rows(root, record)
        if dimension is None:
            dimension = vectors.shape[1]
        elif vectors.shape[1] != dimension:
            raise ClipIndexContractError(
                f"Dimension không đồng nhất: cần {dimension}, nhận {vectors.shape[1]}"
            )
        ids = {row["embedding_id"] for row in rows}
        if len(ids) != len(rows) or seen_ids.intersection(ids):
            raise ClipIndexContractError("Phát hiện embedding_id trùng hoặc hash collision")
        seen_ids.update(ids)
        all_vectors.append(_normalized(vectors))
        metadata.extend(rows)

    vectors = np.concatenate(all_vectors, axis=0)
    ids = np.asarray([row["embedding_id"] for row in metadata], dtype=np.int64)
    index = faiss.IndexIDMap2(faiss.IndexFlatIP(int(dimension)))
    index.add_with_ids(vectors, ids)
    if index.ntotal != len(metadata):
        raise ClipIndexContractError("Số vector trong FAISS không khớp metadata")

    index_path = target / "clip.index"
    metadata_path = target / "metadata.jsonl"
    fd, tmp_name = tempfile.mkstemp(prefix="clip.index.", suffix=".tmp", dir=target)
    os.close(fd)
    try:
        faiss.write_index(index, tmp_name)
        os.replace(tmp_name, index_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    atomic_write_text(
        metadata_path,
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in metadata),
    )
    marker = {
        "schema_version": 1,
        "task": "clip_faiss_index",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "model_revision": model_revision,
        "config_hash": config_hash,
        "git_commit": git_commit,
        "input_manifest_sha256": sha256_file(manifest),
        "expected_count": len(metadata),
        "processed_count": len(metadata),
        "failures": 0,
        "vector_dim": dimension,
        "metric": "cosine_via_normalized_inner_product",
        "index_file": index_path.name,
        "index_sha256": sha256_file(index_path),
        "metadata_file": metadata_path.name,
        "metadata_sha256": sha256_file(metadata_path),
    }
    atomic_write_json(target / "DONE.json", marker)
    return marker


def search_clip_index(
    index_path: str | Path, query_vector: np.ndarray, top_k: int
) -> list[tuple[int, float]]:
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError("M1 cần dependency faiss-cpu") from exc
    index = faiss.read_index(str(index_path))
    query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
    if query.shape[1] != index.d:
        raise ClipIndexContractError(f"Query dim={query.shape[1]}, index dim={index.d}")
    query = _normalized(query)
    scores, ids = index.search(query, top_k)
    return [(int(item_id), float(score)) for item_id, score in zip(ids[0], scores[0]) if item_id >= 0]


def encode_clip_text(
    query_text: str,
    *,
    model_name: str = "ViT-B-32",
    pretrained: str = "openai",
    device: str = "cpu",
) -> np.ndarray:
    """Mã hóa text bằng đúng encoder được notebook BTC công bố."""
    if not query_text.strip():
        raise ValueError("Câu truy vấn không được rỗng")
    try:
        import open_clip
        import torch
    except ImportError as exc:
        raise RuntimeError("Text retrieval cần dependency open-clip-torch") from exc
    model, _, _ = open_clip.create_model_and_transforms(
        model_name,
        pretrained=pretrained,
        device=device,
    )
    tokenizer = open_clip.get_tokenizer(model_name)
    model.eval()
    tokens = tokenizer([query_text]).to(device)
    with torch.no_grad():
        vector = model.encode_text(tokens)
        vector = vector / vector.norm(dim=-1, keepdim=True)
    return vector.cpu().numpy()[0].astype(np.float32)
