"""SigLIP2 CUSTOM FAISS index builder.

Builds a deterministic FAISS IndexFlatIP from 116,767 verified CUSTOM SigLIP2
image embeddings, producing:
  - siglip_custom.faiss
  - siglip_custom_rowmap.jsonl
  - siglip_custom_passport.json
  - DONE.json
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_siglip_index(
    runtime_dir: str | Path,
    output_dir: str | Path,
    *,
    embedding_root: str | Path | None = None,
    self_test_count: int = 20,
    max_workers: int = 16,
) -> dict[str, Any]:
    """Build the SigLIP CUSTOM FAISS FlatIP index.

    Args:
        runtime_dir: Path to retrieval_data_v1 containing runtime/mapping.sqlite
        output_dir: Where to write the FAISS index artifacts
        embedding_root: Root path containing output/embeddings/*.npy (defaults to DATA_REGISTRY.btc_drive_root)
        self_test_count: Number of self-vector top-1 tests to run
        max_workers: Parallel workers for reading .npy files
    """
    import faiss

    runtime_dir = Path(runtime_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load canonical keyframe rowmap from mapping.sqlite ──
    db_path = runtime_dir / "runtime" / "mapping.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"mapping.sqlite not found at {db_path}")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()
    cur.execute(
        """
        SELECT v.video_id, v.ordinal AS video_ordinal,
               ck.keyframe_uid, ck.frame_idx, ck.timestamp_ms,
               ck.embedding_index, ck.image_relpath, ck.raw_pts_time
        FROM custom_keyframes ck
        JOIN videos v ON ck.video_id = v.video_id
        ORDER BY v.ordinal ASC, ck.embedding_index ASC
        """
    )
    db_rows = cur.fetchall()
    conn.close()

    if len(db_rows) != 116767:
        raise ValueError(f"Expected 116767 custom keyframes, got {len(db_rows)}")

    # ── 2. Resolve embedding root ──
    if embedding_root is None:
        from aic2026.core.data_registry import DATA_REGISTRY
        embedding_root = Path(DATA_REGISTRY.btc_drive_root)
    else:
        embedding_root = Path(embedding_root)

    emb_dir = embedding_root / "output" / "embeddings"
    if not emb_dir.exists():
        raise FileNotFoundError(f"SigLIP embedding directory not found: {emb_dir}")

    # ── 3. Group rows by video_id ──
    video_to_rows: dict[str, list[sqlite3.Row]] = {}
    video_order: list[str] = []
    seen_keyframe_uids: set[str] = set()

    for r in db_rows:
        vid = r["video_id"]
        uid = r["keyframe_uid"]
        if not uid.startswith("CUSTOM:"):
            raise ValueError(f"Non-CUSTOM keyframe_uid in SigLIP rowmap: {uid}")
        if uid in seen_keyframe_uids:
            raise ValueError(f"Duplicate keyframe_uid: {uid}")
        seen_keyframe_uids.add(uid)

        if vid not in video_to_rows:
            video_to_rows[vid] = []
            video_order.append(vid)
        video_to_rows[vid].append(r)

    print(f"Building SigLIP FAISS index from {len(db_rows)} keyframes across {len(video_order)} videos...")
    t0 = time.perf_counter()

    # ── 4. Parallel read of all .npy files into memory ──
    print(f"  Reading {len(video_order)} .npy files (parallel {max_workers} workers)...")
    video_arrays: dict[str, np.ndarray] = {}

    def load_one_video(vid: str) -> tuple[str, np.ndarray]:
        npy_file = emb_dir / f"{vid}.npy"
        if not npy_file.exists():
            raise FileNotFoundError(f"Missing SigLIP embedding file: {npy_file}")
        arr = np.load(str(npy_file))
        if arr.ndim != 2 or arr.shape[1] != 768:
            raise ValueError(f"Invalid shape for {vid}: {arr.shape}")
        if arr.dtype != np.float32:
            arr = arr.astype(np.float32)
        return vid, arr

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(load_one_video, vid): vid for vid in video_order}
        for fut in as_completed(futures):
            vid, arr = fut.result()
            video_arrays[vid] = arr

    print(f"  Loaded all {len(video_arrays)} embedding arrays in {time.perf_counter() - t0:.1f}s")

    # ── 5. Populate matrix and rowmap in exact canonical order ──
    matrix = np.empty((116767, 768), dtype=np.float32)
    rowmap: list[dict[str, Any]] = []
    faiss_row = 0

    for vid in video_order:
        arr = video_arrays[vid]
        for r in video_to_rows[vid]:
            emb_idx = r["embedding_index"]
            if emb_idx >= arr.shape[0]:
                raise ValueError(
                    f"embedding_index {emb_idx} out of range for {vid} (shape={arr.shape})"
                )
            matrix[faiss_row] = arr[emb_idx]
            rowmap.append({
                "faiss_row": faiss_row,
                "keyframe_uid": r["keyframe_uid"],
                "video_id": vid,
                "video_ordinal": r["video_ordinal"],
                "frame_idx": r["frame_idx"],
                "timestamp_ms": r["timestamp_ms"],
                "raw_pts_time": r["raw_pts_time"],
                "embedding_index": emb_idx,
                "image_relpath": r["image_relpath"],
            })
            faiss_row += 1

    assert faiss_row == 116767, f"Row count mismatch: {faiss_row} != 116767"

    # ── 6. Validate vectors ──
    print("  Validating vectors...")
    nan_count = int(np.isnan(matrix).any(axis=1).sum())
    inf_count = int(np.isinf(matrix).any(axis=1).sum())
    if nan_count > 0:
        raise ValueError(f"NaN vectors found: {nan_count}")
    if inf_count > 0:
        raise ValueError(f"Inf vectors found: {inf_count}")

    norms = np.linalg.norm(matrix, axis=1)
    norm_min = float(norms.min())
    norm_max = float(norms.max())
    norm_mean = float(norms.mean())
    print(f"  Vector norms: min={norm_min:.6f}, mean={norm_mean:.6f}, max={norm_max:.6f}")

    # ── 7. Build FAISS IndexFlatIP ──
    print("  Building FAISS IndexFlatIP...")
    index = faiss.IndexFlatIP(768)
    matrix_c = np.ascontiguousarray(matrix, dtype=np.float32)
    index.add(matrix_c)
    assert index.ntotal == 116767, f"FAISS ntotal mismatch: {index.ntotal}"

    # ── 8. Write artifacts ──
    index_path = output_dir / "siglip_custom.faiss"
    faiss.write_index(index, str(index_path))
    print(f"  Wrote FAISS index: {index_path} ({index_path.stat().st_size / (1024*1024):.1f} MB)")

    rowmap_path = output_dir / "siglip_custom_rowmap.jsonl"
    with open(rowmap_path, "w", encoding="utf-8") as f:
        for entry in rowmap:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"  Wrote rowmap: {rowmap_path}")

    index_sha256 = _sha256_file(index_path)
    rowmap_sha256 = _sha256_file(rowmap_path)

    # ── 9. Self-vector test ──
    print(f"  Running {self_test_count} self-vector top-1 tests...")
    rng = np.random.RandomState(42)
    test_indices = rng.choice(116767, size=self_test_count, replace=False)
    self_test_passed = 0
    for idx in test_indices:
        query_vec = matrix_c[idx : idx + 1]
        scores, ids = index.search(query_vec, 10)
        top_id = int(ids[0][0])
        top_score = float(scores[0][0])
        # Top-1 matches self directly or matches an identical vector with dot=1.0
        if top_id == idx or (
            np.isclose(top_score, 1.0, atol=1e-5)
            and np.array_equal(matrix_c[idx], matrix_c[top_id])
        ):
            self_test_passed += 1
        else:
            print(f"    FAIL: row {idx} -> top-1 = {top_id}, top_score = {top_score:.6f}")
    print(f"  Self-vector top-1: {self_test_passed}/{self_test_count}")
    if self_test_passed != self_test_count:
        raise ValueError(f"Self-vector test FAILED: {self_test_passed}/{self_test_count}")

    build_duration = time.perf_counter() - t0

    # ── 10. Write passport ──
    passport = {
        "index_id": "siglip_custom_faiss_v1",
        "lane_id": "siglip_custom",
        "artifact_type": "FAISS_INDEX",
        "frame_space": "CUSTOM",
        "entity_space": "CUSTOM_KEYFRAME",
        "model_id": "google/siglip2-base-patch16-224",
        "model_revision": None,
        "processor_contract": {
            "padding": "max_length",
            "truncation": True,
            "max_length": 64,
        },
        "normalization_policy": "L2_UNIT_NORMALIZED",
        "dimension": 768,
        "source_dtype": "float32",
        "index_dtype": "float32",
        "metric": "INNER_PRODUCT",
        "index_type": "IndexFlatIP",
        "row_count": 116767,
        "rowmap_count": 116767,
        "rowmap_checksum": rowmap_sha256,
        "index_checksum": index_sha256,
        "source_artifact_ref": "output/embeddings/*.npy",
        "m1_runtime_build_id": None,
        "m1f_validation_ref": "M1F_CROSS_SPACE_DRILLDOWN_RESULT.md",
        "vector_norms": {
            "min": round(norm_min, 6),
            "mean": round(norm_mean, 6),
            "max": round(norm_max, 6),
        },
        "nan_rows": nan_count,
        "inf_rows": inf_count,
        "duplicate_keyframe_uids": 0,
        "unknown_custom_keyframes": 0,
        "videos_covered": len(video_order),
        "self_vector_top1": f"{self_test_passed}/{self_test_count}",
        "build_duration_sec": round(build_duration, 2),
        "index_size_bytes": index_path.stat().st_size,
        "build_id": f"siglip_build_{int(time.time())}",
        "git_revision": None,
        "created_at": _utc_now(),
        "status": "READY",
        "schema_version": "v1",
    }

    try:
        passport["git_revision"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        pass

    try:
        conn2 = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        cur2 = conn2.cursor()
        cur2.execute("SELECT value FROM runtime_meta WHERE key = 'build_id'")
        r = cur2.fetchone()
        if r:
            passport["m1_runtime_build_id"] = r[0]
        conn2.close()
    except Exception:
        pass

    passport_path = output_dir / "siglip_custom_passport.json"
    with open(passport_path, "w", encoding="utf-8") as f:
        json.dump(passport, f, indent=2, ensure_ascii=False)

    # ── 11. Write DONE.json ──
    done = {
        "task": "siglip_faiss_index",
        "schema_version": 1,
        "index_file": "siglip_custom.faiss",
        "rowmap_file": "siglip_custom_rowmap.jsonl",
        "passport_file": "siglip_custom_passport.json",
        "index_sha256": index_sha256,
        "rowmap_sha256": rowmap_sha256,
        "row_count": 116767,
        "dimension": 768,
        "metric": "INNER_PRODUCT",
        "self_vector_top1": f"{self_test_passed}/{self_test_count}",
        "build_duration_sec": round(build_duration, 2),
        "created_at": _utc_now(),
        "status": "READY",
    }
    with open(output_dir / "DONE.json", "w", encoding="utf-8") as f:
        json.dump(done, f, indent=2)

    print(f"\nSigLIP index build complete in {build_duration:.1f}s")
    print(f"  Index:   {index_sha256[:16]}...")
    print(f"  Rowmap:  {rowmap_sha256[:16]}...")
    print(f"  Rows:    {index.ntotal}")
    print(f"  Self-test: {self_test_passed}/{self_test_count} PASS")

    return passport
