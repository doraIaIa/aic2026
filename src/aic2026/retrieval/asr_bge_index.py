"""ASR BGE-M3 Dense Retrieval Index Builder and Runtime Index (M4A).

Constructs and manages a FAISS IndexFlatIP index over 107,540 canonical
Whisper-medium Vietnamese ASR segments using BAAI/bge-m3 (1024D, float32, normalized).
"""
from __future__ import annotations

import json
import logging
import multiprocessing as mp
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from aic2026.core.hashing import sha256_file

logger = logging.getLogger(__name__)

BGE_MODEL_ID = "BAAI/bge-m3"
BGE_DENSE_DIMENSION = 1024
BGE_METRIC = "INNER_PRODUCT"
CANONICAL_ASR_TOTAL = 107540
DEFAULT_NUM_SHARDS = 20
DEFAULT_BATCH_SIZE = 256
MAX_TOP_K = 300
MAX_OVERFETCH_MULTIPLIER = 64


@dataclass
class AsrBgeRowmapEntry:
    global_row: int
    segment_uid: str
    video_id: str
    video_ordinal: int
    start_ms: int
    end_ms: int
    start_sec: float
    end_sec: float
    text: str
    language: str
    model: str
    source_segment_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def encode_texts_bge_m3(
    texts: Sequence[str],
    *,
    model: Any,
    tokenizer: Any,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_length: int = 64,
) -> np.ndarray:
    """Encode a list of texts into normalized float32 1024D BGE-M3 dense vectors.
    
    Uses length-sorted batching for minimal padding overhead and high CPU throughput.
    """
    import torch

    if not texts:
        return np.zeros((0, BGE_DENSE_DIMENSION), dtype=np.float32)

    # Sort indices by text length
    indexed = sorted(enumerate(texts), key=lambda x: len(x[1]))
    sorted_vectors = [None] * len(texts)

    for i in range(0, len(indexed), batch_size):
        chunk = indexed[i : i + batch_size]
        indices = [c[0] for c in chunk]
        batch_texts = [c[1] for c in chunk]

        encoded = tokenizer(
            batch_texts,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        with torch.no_grad():
            output = model(**encoded)
            # BGE-M3 official dense representation: CLS token (index 0) L2-normalized
            cls_token = output[0][:, 0]
            normalized = torch.nn.functional.normalize(cls_token, p=2, dim=1)
            vecs = normalized.cpu().numpy().astype(np.float32)
            for idx, v in zip(indices, vecs):
                sorted_vectors[idx] = v

    dense_matrix = np.array(sorted_vectors, dtype=np.float32)
    return dense_matrix


def _process_single_shard(
    shard_idx: int,
    shard_rows: list[tuple[Any, ...]],
    shards_dir_str: str,
    batch_size: int,
    num_threads: int,
) -> dict[str, Any]:
    """Worker function to build/verify a single shard embeddings and rowmap."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    torch.set_num_threads(num_threads)
    shards_dir = Path(shards_dir_str)
    shard_count = len(shard_rows)

    emb_file = shards_dir / f"embeddings_shard_{shard_idx:03d}.npy"
    rowmap_file = shards_dir / f"rowmap_shard_{shard_idx:03d}.jsonl"
    done_file = shards_dir / f"DONE_{shard_idx:03d}.json"

    # Check if already completed and valid
    if done_file.exists() and emb_file.exists() and rowmap_file.exists():
        try:
            with open(done_file, "r", encoding="utf-8") as f:
                done_meta = json.load(f)
            if (
                done_meta.get("row_count") == shard_count
                and done_meta.get("embeddings_sha256") == sha256_file(emb_file)
                and done_meta.get("rowmap_sha256") == sha256_file(rowmap_file)
            ):
                return done_meta
        except Exception:
            pass

    t0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(BGE_MODEL_ID)
    model = AutoModel.from_pretrained(BGE_MODEL_ID, use_safetensors=True)
    model.eval()

    shard_entries: list[AsrBgeRowmapEntry] = []
    shard_texts: list[str] = []
    for r in shard_rows:
        entry = AsrBgeRowmapEntry(
            global_row=r[0],
            segment_uid=r[1],
            source_segment_id=r[2],
            video_id=r[3],
            video_ordinal=r[4],
            start_ms=r[5],
            end_ms=r[6],
            start_sec=r[7],
            end_sec=r[8],
            text=r[9],
            language=r[10],
            model=r[11],
        )
        shard_entries.append(entry)
        shard_texts.append(r[9])

    vectors = encode_texts_bge_m3(
        shard_texts,
        model=model,
        tokenizer=tokenizer,
        batch_size=batch_size,
    )

    # Validations
    assert vectors.shape == (shard_count, BGE_DENSE_DIMENSION)
    assert vectors.dtype == np.float32
    assert np.isfinite(vectors).all()
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)

    np.save(emb_file, vectors)

    with open(rowmap_file, "w", encoding="utf-8") as f:
        for entry in shard_entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    emb_sha = sha256_file(emb_file)
    rowmap_sha = sha256_file(rowmap_file)
    elapsed = time.perf_counter() - t0

    shard_meta = {
        "shard_idx": shard_idx,
        "row_start": shard_rows[0][0],
        "row_end": shard_rows[-1][0] + 1,
        "row_count": shard_count,
        "embeddings_file": emb_file.name,
        "embeddings_sha256": emb_sha,
        "rowmap_file": rowmap_file.name,
        "rowmap_sha256": rowmap_sha,
        "norm_min": float(np.min(norms)),
        "norm_mean": float(np.mean(norms)),
        "norm_max": float(np.max(norms)),
        "elapsed_sec": round(elapsed, 2),
    }
    with open(done_file, "w", encoding="utf-8") as f:
        json.dump(shard_meta, f, indent=2)

    return shard_meta


def build_asr_bge_index(
    db_path: Path | str,
    output_dir: Path | str,
    *,
    num_shards: int = DEFAULT_NUM_SHARDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    num_threads: int = 4,
    workers: int = 4,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Build the canonical ASR BGE-M3 dense FAISS index and rowmap with parallel shard workers."""
    import faiss

    db_path = Path(db_path)
    output_dir = Path(output_dir)
    shards_dir = output_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.perf_counter()

    # 1. Query all canonical ASR segments in deterministic order
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    c = conn.cursor()
    c.execute(
        """
        SELECT 
            segment_uid,
            source_segment_id,
            video_id,
            video_ordinal,
            start_ms,
            end_ms,
            start_sec,
            end_sec,
            text_raw,
            language,
            model
        FROM canonical_asr_segments
        ORDER BY video_ordinal ASC, start_ms ASC, end_ms ASC, segment_uid ASC
        """
    )
    raw_rows = c.fetchall()
    conn.close()

    total_segments = len(raw_rows)
    if total_segments != CANONICAL_ASR_TOTAL:
        raise ValueError(
            f"Expected {CANONICAL_ASR_TOTAL} canonical ASR segments, got {total_segments}"
        )

    # Attach global row index
    indexed_rows = [
        (idx, *r) for idx, r in enumerate(raw_rows)
    ]

    empty_count = sum(1 for r in raw_rows if not r[8] or not r[8].strip())
    logger.info("Found %d canonical segments (%d empty text)", total_segments, empty_count)

    # 2. Divide into deterministic shards
    shard_size = (total_segments + num_shards - 1) // num_shards
    shards_tasks: list[tuple[int, list[Any], str, int, int]] = []

    for shard_idx in range(num_shards):
        s_start = shard_idx * shard_size
        s_end = min(total_segments, (shard_idx + 1) * shard_size)
        if s_start >= total_segments:
            break

        shard_rows = indexed_rows[s_start:s_end]
        shards_tasks.append((shard_idx, shard_rows, str(shards_dir), batch_size, num_threads))

    logger.info("Dispatching %d shards across %d worker processes...", len(shards_tasks), workers)

    # 3. Execute shards in parallel pool
    completed_shards: dict[int, dict[str, Any]] = {}
    if workers > 1:
        with mp.Pool(processes=workers) as pool:
            for shard_meta in pool.starmap(_process_single_shard, shards_tasks):
                shard_idx = shard_meta["shard_idx"]
                completed_shards[shard_idx] = shard_meta
                if progress_callback:
                    progress_callback(
                        len(completed_shards),
                        len(shards_tasks),
                        f"Shard {shard_idx:03d} done ({shard_meta['row_count']} rows in {shard_meta['elapsed_sec']}s)",
                    )
    else:
        for task in shards_tasks:
            shard_meta = _process_single_shard(*task)
            shard_idx = shard_meta["shard_idx"]
            completed_shards[shard_idx] = shard_meta
            if progress_callback:
                progress_callback(
                    len(completed_shards),
                    len(shards_tasks),
                    f"Shard {shard_idx:03d} done ({shard_meta['row_count']} rows in {shard_meta['elapsed_sec']}s)",
                )

    shards_info = [completed_shards[i] for i in range(len(shards_tasks))]

    # 4. Deterministic Merge across all shards
    logger.info("Merging %d shards into FAISS IndexFlatIP and unified rowmap...", len(shards_info))
    merged_faiss_path = output_dir / "asr_bge.faiss"
    merged_rowmap_path = output_dir / "asr_bge_rowmap.jsonl"
    passport_path = output_dir / "asr_bge_passport.json"
    manifest_path = output_dir / "manifest.json"
    done_path = output_dir / "DONE.json"

    # Merge rowmaps in order
    total_written_rows = 0
    with open(merged_rowmap_path, "w", encoding="utf-8") as f_out:
        for s in shards_info:
            shard_rowmap = shards_dir / s["rowmap_file"]
            with open(shard_rowmap, "r", encoding="utf-8") as f_in:
                for line in f_in:
                    f_out.write(line)
                    total_written_rows += 1

    assert total_written_rows == total_segments, f"Merged rowmap row count {total_written_rows} != {total_segments}"

    # Build and merge FAISS IndexFlatIP
    index = faiss.IndexFlatIP(BGE_DENSE_DIMENSION)
    for s in shards_info:
        shard_emb_path = shards_dir / s["embeddings_file"]
        vecs = np.load(shard_emb_path)
        index.add(vecs)

    assert index.ntotal == total_segments, f"FAISS index rows {index.ntotal} != {total_segments}"
    faiss.write_index(index, str(merged_faiss_path))

    # Checksums
    faiss_sha256 = sha256_file(merged_faiss_path)
    rowmap_sha256 = sha256_file(merged_rowmap_path)
    total_duration_sec = time.perf_counter() - t_start

    passport = {
        "index_id": "asr_bge_v1",
        "lane_id": "asr_bge",
        "artifact_type": "FAISS_INDEX",
        "entity_space": "ASR_SEGMENT",
        "model_id": BGE_MODEL_ID,
        "library": "transformers",
        "dimension": BGE_DENSE_DIMENSION,
        "dtype": "float32",
        "normalized": True,
        "metric": BGE_METRIC,
        "index_type": "IndexFlatIP",
        "canonical_segment_count": total_segments,
        "eligible_dense_segment_count": total_segments,
        "excluded_empty_count": empty_count,
        "rowmap_count": total_segments,
        "index_rows": index.ntotal,
        "index_sha256": faiss_sha256,
        "rowmap_sha256": rowmap_sha256,
        "num_shards": len(shards_info),
        "build_duration_sec": round(total_duration_sec, 2),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(passport_path, "w", encoding="utf-8") as f:
        json.dump(passport, f, indent=2)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"passport": passport, "shards": shards_info}, f, indent=2)

    done_summary = {
        "status": "PASS",
        "index_id": "asr_bge_v1",
        "total_rows": total_segments,
        "index_sha256": faiss_sha256,
        "rowmap_sha256": rowmap_sha256,
        "build_duration_sec": round(total_duration_sec, 2),
    }
    with open(done_path, "w", encoding="utf-8") as f:
        json.dump(done_summary, f, indent=2)

    logger.info(
        "ASR BGE-M3 index build complete: %d rows in %.2fs (SHA: %s...)",
        total_segments,
        total_duration_sec,
        faiss_sha256[:16],
    )
    return passport


class AsrBgeIndex:
    """Thread-safe runtime reader for ASR BGE-M3 FAISS index and rowmap."""

    def __init__(self, artifact_dir: Path | str) -> None:
        self.artifact_dir = Path(artifact_dir)
        self._index: Any = None
        self._rowmap: list[dict[str, Any]] = []
        self._rows_by_video: dict[str, list[int]] = {}
        self._passport: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def load(self) -> None:
        """Load FAISS index, rowmap, and passport into memory."""
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            import faiss

            faiss_path = self.artifact_dir / "asr_bge.faiss"
            rowmap_path = self.artifact_dir / "asr_bge_rowmap.jsonl"
            passport_path = self.artifact_dir / "asr_bge_passport.json"

            if not faiss_path.exists() or not rowmap_path.exists():
                raise FileNotFoundError(f"ASR BGE artifacts missing in {self.artifact_dir}")

            self._index = faiss.read_index(str(faiss_path))
            
            rowmap = []
            rows_by_video: dict[str, list[int]] = {}
            with open(rowmap_path, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    data = json.loads(line)
                    rowmap.append(data)
                    vid = data["video_id"]
                    if vid not in rows_by_video:
                        rows_by_video[vid] = []
                    rows_by_video[vid].append(idx)

            self._rowmap = rowmap
            self._rows_by_video = rows_by_video

            if passport_path.exists():
                with open(passport_path, "r", encoding="utf-8") as f:
                    self._passport = json.load(f)

            assert self._index.ntotal == len(self._rowmap), "Index rows != rowmap rows"
            self._loaded = True

    @property
    def total_rows(self) -> int:
        self.load()
        return self._index.ntotal

    @property
    def passport(self) -> dict[str, Any]:
        self.load()
        return self._passport

    def search_dense(
        self,
        query_vector: np.ndarray,
        top_k: int = 20,
        candidate_video_ids: Sequence[str] | None = None,
    ) -> list[tuple[int, float, dict[str, Any]]]:
        """Search top_k nearest ASR segments by cosine similarity (inner product).
        
        Returns: list of (global_row, score, rowmap_entry).
        """
        self.load()
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)

        # Normalize query vector if needed
        norm = np.linalg.norm(query_vector)
        if norm > 0 and abs(norm - 1.0) > 1e-4:
            query_vector = query_vector / norm

        top_k = min(max(1, top_k), MAX_TOP_K)

        with self._lock:
            if candidate_video_ids and len(candidate_video_ids) > 0:
                scope_set = set(candidate_video_ids)
                fetch_k = min(top_k * 8, self._index.ntotal)
                multiplier = 8
                collected: list[tuple[int, float, dict[str, Any]]] = []

                while multiplier <= MAX_OVERFETCH_MULTIPLIER:
                    scores, indices = self._index.search(query_vector, fetch_k)
                    collected = []
                    for row_idx, score in zip(indices[0], scores[0]):
                        if row_idx < 0 or row_idx >= len(self._rowmap):
                            continue
                        entry = self._rowmap[row_idx]
                        if entry["video_id"] in scope_set:
                            collected.append((int(row_idx), float(score), entry))
                            if len(collected) >= top_k:
                                break

                    if len(collected) >= top_k or fetch_k >= self._index.ntotal:
                        break

                    multiplier *= 2
                    fetch_k = min(top_k * multiplier, self._index.ntotal)

                return collected[:top_k]
            else:
                scores, indices = self._index.search(query_vector, top_k)
                results: list[tuple[int, float, dict[str, Any]]] = []
                for row_idx, score in zip(indices[0], scores[0]):
                    if row_idx < 0 or row_idx >= len(self._rowmap):
                        continue
                    results.append((int(row_idx), float(score), self._rowmap[row_idx]))
                return results

    def verify_self_vectors(self, n: int = 20) -> tuple[int, int]:
        """Verify that searching with embedded vectors returns the exact same row as Top-1.
        
        Uses deterministic unique text segment rows to avoid artificial ties across identical text phrases.
        """
        self.load()
        
        # Select n deterministic unique text rows spaced evenly across the corpus
        step = max(1, len(self._rowmap) // (n * 2))
        seen_texts: set[str] = set()
        test_rows: list[int] = []
        for idx in range(0, len(self._rowmap), step):
            txt = self._rowmap[idx]["text"].strip()
            if txt and txt not in seen_texts:
                seen_texts.add(txt)
                test_rows.append(idx)
                if len(test_rows) >= n:
                    break

        if len(test_rows) < n:
            test_rows = list(range(n))

        passed = 0
        for idx in test_rows:
            vec = self._index.reconstruct(int(idx)).reshape(1, -1)
            scores, res_indices = self._index.search(vec, 1)
            top1_row = res_indices[0][0]
            top1_score = scores[0][0]
            # Match either exact row or exact identical vector score
            if top1_row == idx or (top1_score >= 0.99999 and self._rowmap[top1_row]["text"] == self._rowmap[idx]["text"]):
                passed += 1

        return passed, len(test_rows)
