"""Qwen Semantic Core BGE-M3 Dense Retrieval Index Builder (M5B - REV2 GPU-SAFE).

Builds a deterministic FAISS IndexFlatIP index over eligible Qwen semantic core
documents serialized according to document policy `qwen_semantic_core_v1`.

GPU-SAFE / NO CPU CORPUS-EMBEDDING FALLBACK (REV2):
- Requires CUDA runtime (`torch.cuda.is_available() == True`).
- Exactly 1 BGE model instance on CUDA (no multi-process model replicas on single GPU).
- Zero CPU fallback events. Fails closed with QWEN_BGE_CUDA_UNAVAILABLE / QWEN_BGE_GPU_BUILD_FAILED.
- Sharded and resumable via `DONE_xxx.json` per shard.
"""
from __future__ import annotations

import gc
import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import faiss
import numpy as np

from aic2026.core.hashing import sha256_file

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & Contracts
# ---------------------------------------------------------------------------
BGE_MODEL_ID = "BAAI/bge-m3"
BGE_DENSE_DIMENSION = 1024
DEFAULT_NUM_SHARDS = 20
DEFAULT_BATCH_SIZE = 64
DOCUMENT_POLICY_ID = "qwen_semantic_core_v1"
CANONICAL_QWEN_TOTAL = 116767

INCLUDED_FIELDS = [
    "caption",
    "objects",
    "attributes",
    "scene",
    "visible_actions",
]
EXCLUDED_FIELDS = [
    "spatial_relations",
    "counts",
]


# ---------------------------------------------------------------------------
# Document Policy Serialization (qwen_semantic_core_v1)
# ---------------------------------------------------------------------------
def serialize_qwen_semantic_core_v1(row: dict[str, Any] | sqlite3.Row) -> str:
    """Serialize a single Qwen frame observation into a controlled semantic document.
    
    Included: caption, objects, attributes, scene, visible_actions.
    Excluded: spatial_relations, counts.
    Omit empty sections. No translation, no LLM rewriting.
    """
    parts: list[str] = []

    # 1. Caption
    cap = (row["caption"] or "").strip()
    if cap:
        parts.append(f"caption: {cap}")

    # 2. Structured items (in frozen order)
    for field_name, label in [
        ("objects_json", "objects"),
        ("attributes_json", "attributes"),
        ("scene_json", "scene"),
        ("visible_actions_json", "visible actions"),
    ]:
        raw_val = row[field_name]
        if not raw_val or raw_val == "[]":
            continue
        try:
            if isinstance(raw_val, str):
                items = json.loads(raw_val)
            elif isinstance(raw_val, list):
                items = raw_val
            else:
                items = [raw_val]
            if not isinstance(items, list):
                items = [items]
            clean_items = [str(x).strip() for x in items if x and str(x).strip()]
            if clean_items:
                parts.append(f"{label}: {'; '.join(clean_items)}")
        except Exception:
            continue

    return "\n".join(parts).strip()


@dataclass
class QwenBgeRowmapEntry:
    dense_row: int
    keyframe_uid: str
    video_id: str
    frame_idx: int
    timestamp_ms: int
    document_policy_id: str
    document_sha256: str
    caption: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# GPU Dense Encoding Engine
# ---------------------------------------------------------------------------
def encode_texts_bge_m3(
    texts: Sequence[str],
    *,
    model: Any,
    tokenizer: Any,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_length: int = 512,
    device: str | None = None,
) -> np.ndarray:
    """Encode a list of texts into normalized float32 1024D BGE-M3 dense vectors.
    
    GPU-accelerated with length-sorted batching and adaptive OOM retry.
    """
    import torch

    if not texts:
        return np.zeros((0, BGE_DENSE_DIMENSION), dtype=np.float32)

    # Determine target device
    if device is None:
        device = "cuda" if next(model.parameters()).is_cuda else "cpu"

    indexed = sorted(enumerate(texts), key=lambda x: len(x[1]))
    sorted_vectors = [None] * len(texts)

    idx_ptr = 0
    current_bs = batch_size

    while idx_ptr < len(indexed):
        chunk = indexed[idx_ptr : idx_ptr + current_bs]
        indices = [c[0] for c in chunk]
        batch_texts = [c[1] for c in chunk]

        try:
            encoded = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            encoded = {k: v.to(device) for k, v in encoded.items()}

            with torch.inference_mode():
                output = model(**encoded)
                # BGE-M3 dense representation: [CLS] token (index 0) L2-normalized
                cls_token = output[0][:, 0]
                normalized = torch.nn.functional.normalize(cls_token, p=2, dim=1)
                vecs = normalized.detach().cpu().numpy().astype(np.float32)

            for orig_i, v in zip(indices, vecs):
                sorted_vectors[orig_i] = v

            idx_ptr += len(chunk)

        except torch.cuda.OutOfMemoryError as oom_err:
            if current_bs > 1:
                logger.warning(
                    "CUDA OOM at batch_size=%d. Clearing cache and reducing to %d.",
                    current_bs,
                    max(1, current_bs // 2),
                )
                torch.cuda.empty_cache()
                gc.collect()
                current_bs = max(1, current_bs // 2)
            else:
                torch.cuda.empty_cache()
                raise RuntimeError(
                    "STOP: QWEN_BGE_GPU_MEMORY_INSUFFICIENT_FOR_FROZEN_CONTRACT (OOM at batch_size=1)"
                ) from oom_err

    dense_matrix = np.array(sorted_vectors, dtype=np.float32)
    return dense_matrix


# ---------------------------------------------------------------------------
# GPU Batch Size Probe (Mandatory Pre-flight)
# ---------------------------------------------------------------------------
def probe_gpu_batch_sizes(
    sample_docs: Sequence[str],
    model: Any,
    tokenizer: Any,
    candidate_batches: Sequence[int] = (1, 2, 4, 8, 16, 32, 64),
) -> dict[str, Any]:
    """Probe candidate batch sizes on CUDA and select the largest stable batch size with headroom."""
    import torch

    probe_table = []
    selected_bs = 1
    max_safe_speed = 0.0

    for bs in candidate_batches:
        if bs > len(sample_docs):
            break
        torch.cuda.empty_cache()
        gc.collect()
        torch.cuda.reset_peak_memory_stats()

        t0 = time.perf_counter()
        try:
            _ = encode_texts_bge_m3(
                sample_docs[: min(len(sample_docs), bs * 2)],
                model=model,
                tokenizer=tokenizer,
                batch_size=bs,
                device="cuda",
            )
            elapsed = time.perf_counter() - t0
            docs_encoded = min(len(sample_docs), bs * 2)
            speed = docs_encoded / elapsed if elapsed > 0 else 0.0

            peak_alloc = torch.cuda.max_memory_allocated()
            peak_res = torch.cuda.max_memory_reserved()

            probe_table.append({
                "batch_size": bs,
                "status": "PASS",
                "docs_per_sec": round(speed, 2),
                "peak_allocated_mb": round(peak_alloc / 1024 / 1024, 2),
                "peak_reserved_mb": round(peak_res / 1024 / 1024, 2),
            })
            selected_bs = bs
            max_safe_speed = speed
        except torch.cuda.OutOfMemoryError:
            probe_table.append({
                "batch_size": bs,
                "status": "OOM",
                "docs_per_sec": 0.0,
                "peak_allocated_mb": 0.0,
                "peak_reserved_mb": 0.0,
            })
            break

    # Choose a stable batch size with headroom (if max tested was 64, 64 or 32 is safe)
    return {
        "probe_table": probe_table,
        "selected_batch_size": selected_bs,
        "speed_docs_per_sec": round(max_safe_speed, 2),
    }


# ---------------------------------------------------------------------------
# GPU-Safe Sharded Builder (REV2)
# ---------------------------------------------------------------------------
def build_qwen_bge_index(
    db_path: str | Path,
    output_dir: str | Path,
    *,
    model_id: str = BGE_MODEL_ID,
    num_shards: int = DEFAULT_NUM_SHARDS,
    batch_size: int | None = None,
    device: str = "cuda",
    threads_per_worker: int = 4,
    workers: int = 1,
) -> dict[str, Any]:
    """Build a sharded BGE-M3 FAISS IndexFlatIP index over eligible Qwen semantic documents on CUDA."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    db_path = Path(db_path)
    output_dir = Path(output_dir)
    shards_dir = output_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.perf_counter()

    # 1. CUDA Pre-Flight Gate
    print("\n" + "=" * 70)
    print("AIC 2026 QWEN BGE CORPUS EMBEDDING PRE-FLIGHT (REV2 GPU-SAFE)")
    print("=" * 70)
    print(f"torch_version: {torch.__version__}")
    print(f"cuda_available: {torch.cuda.is_available()}")
    print(f"torch_cuda_version: {torch.version.cuda}")

    if not torch.cuda.is_available():
        if device == "cuda" or device == "auto":
            raise RuntimeError("STOP = QWEN_BGE_CUDA_UNAVAILABLE: PyTorch CUDA runtime is not available.")

    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A"
    total_vram_bytes = torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else 0
    total_vram_gb = round(total_vram_bytes / 1024 / 1024 / 1024, 2)

    resolved_device = "cuda" if torch.cuda.is_available() and device != "cpu" else "cpu"
    if resolved_device != "cuda" and device != "cpu":
        raise RuntimeError("STOP = QWEN_BGE_CUDA_UNAVAILABLE: GPU corpus embedding required.")

    print(f"gpu_count: {torch.cuda.device_count() if torch.cuda.is_available() else 0}")
    print(f"gpu_name: {gpu_name}")
    print(f"gpu_total_vram_bytes: {total_vram_bytes} ({total_vram_gb} GB)")
    print(f"CORPUS_EMBEDDING_DEVICE = {resolved_device.upper()}")
    print(f"GPU_NAME = {gpu_name}")
    print("MODEL_PROCESSES = 1")
    print("=" * 70 + "\n")

    # 2. Load canonical Qwen rows and build V1 semantic documents
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    total_qwen = c.execute("SELECT COUNT(*) FROM qwen_frames").fetchone()[0]
    if total_qwen != CANONICAL_QWEN_TOTAL:
        raise ValueError(f"Canonical Qwen rows {total_qwen} != expected {CANONICAL_QWEN_TOTAL}")

    rows = c.execute("""
        SELECT keyframe_uid, video_id, frame_idx, timestamp_ms, caption, 
               objects_json, attributes_json, scene_json, visible_actions_json
        FROM qwen_frames
        ORDER BY video_id, frame_idx
    """).fetchall()
    conn.close()

    eligible_docs: list[dict[str, Any]] = []
    empty_caption_count = 0
    empty_doc_count = 0

    dense_row = 0
    for r in rows:
        cap = (r["caption"] or "").strip()
        if not cap:
            empty_caption_count += 1

        doc_text = serialize_qwen_semantic_core_v1(r)
        if not doc_text:
            empty_doc_count += 1
            continue

        doc_sha = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()
        rowmap_entry = QwenBgeRowmapEntry(
            dense_row=dense_row,
            keyframe_uid=r["keyframe_uid"],
            video_id=r["video_id"],
            frame_idx=r["frame_idx"],
            timestamp_ms=r["timestamp_ms"],
            document_policy_id=DOCUMENT_POLICY_ID,
            document_sha256=doc_sha,
            caption=cap,
        )
        eligible_docs.append({
            "doc_text": doc_text,
            "rowmap": rowmap_entry.to_dict(),
        })
        dense_row += 1

    eligible_count = len(eligible_docs)
    logger.info(
        "Total Qwen rows: %d, Eligible V1 docs: %d, Empty docs: %d, Empty captions: %d",
        total_qwen,
        eligible_count,
        empty_doc_count,
        empty_caption_count,
    )

    # 3. Partition into shards
    shard_size = int(np.ceil(eligible_count / num_shards))
    shard_partitions = []
    for s_idx in range(num_shards):
        start_idx = s_idx * shard_size
        end_idx = min((s_idx + 1) * shard_size, eligible_count)
        if start_idx < eligible_count:
            shard_partitions.append((s_idx, eligible_docs[start_idx:end_idx]))

    # Check already completed shards
    pending_shards = []
    completed_shards_info = {}
    for s_idx, s_docs in shard_partitions:
        shard_done_file = shards_dir / f"DONE_{s_idx:03d}.json"
        shard_npy_file = shards_dir / f"embeddings_shard_{s_idx:03d}.npy"
        shard_rowmap_file = shards_dir / f"rowmap_shard_{s_idx:03d}.jsonl"

        is_valid = False
        if shard_done_file.exists() and shard_npy_file.exists() and shard_rowmap_file.exists():
            try:
                done_info = json.loads(shard_done_file.read_text(encoding="utf-8"))
                if (
                    done_info.get("status") == "PASS"
                    and done_info.get("document_count") == len(s_docs)
                    and sha256_file(shard_npy_file) == done_info.get("embeddings_sha256")
                ):
                    completed_shards_info[s_idx] = done_info
                    is_valid = True
            except Exception:
                is_valid = False

        if not is_valid:
            pending_shards.append((s_idx, s_docs))

    print(f"PENDING_SHARDS = {len(pending_shards)}")
    print(f"COMPLETED_SHARDS = {len(completed_shards_info)}")

    # 4. Load single BGE-M3 model on CUDA
    print(f"Loading {model_id} on {resolved_device.upper()} (single process)...")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModel.from_pretrained(model_id, use_safetensors=True)
    if resolved_device == "cuda":
        model.to("cuda")
    model.eval()


    # 5. Batch Size Probe if batch_size not explicitly set
    probe_results = {}
    if batch_size is None or batch_size <= 0:
        sample_texts = [d["doc_text"] for d in eligible_docs[:128]]
        probe_results = probe_gpu_batch_sizes(sample_texts, model, tokenizer)
        batch_size = probe_results["selected_batch_size"]
        print(f"Auto-selected GPU batch size: {batch_size} (probe results: {probe_results})")
    else:
        print(f"Using configured batch size: {batch_size}")

    print(f"BATCH_SIZE = {batch_size}")

    # 6. Sequential Shard Execution on CUDA
    shard_results = [None] * len(shard_partitions)
    for s_idx, done_info in completed_shards_info.items():
        shard_results[s_idx] = done_info

    for s_idx, s_docs in pending_shards:
        t0 = time.perf_counter()
        print(f"Encoding shard {s_idx + 1}/{len(shard_partitions)} ({len(s_docs)} documents) on CUDA...")

        texts = [d["doc_text"] for d in s_docs]
        embeddings = encode_texts_bge_m3(
            texts,
            model=model,
            tokenizer=tokenizer,
            batch_size=batch_size,
            max_length=512,
            device=resolved_device,
        )

        shard_npy_file = shards_dir / f"embeddings_shard_{s_idx:03d}.npy"
        shard_rowmap_file = shards_dir / f"rowmap_shard_{s_idx:03d}.jsonl"
        shard_done_file = shards_dir / f"DONE_{s_idx:03d}.json"

        np.save(shard_npy_file, embeddings)

        with open(shard_rowmap_file, "w", encoding="utf-8") as f:
            for d in s_docs:
                f.write(json.dumps(d["rowmap"], ensure_ascii=False) + "\n")

        npy_sha = sha256_file(shard_npy_file)
        rowmap_sha = sha256_file(shard_rowmap_file)
        elapsed = time.perf_counter() - t0

        shard_res = {
            "status": "PASS",
            "shard_index": s_idx,
            "total_shards": len(shard_partitions),
            "document_count": len(s_docs),
            "embeddings_file": str(shard_npy_file.name),
            "embeddings_sha256": npy_sha,
            "rowmap_file": str(shard_rowmap_file.name),
            "rowmap_sha256": rowmap_sha,
            "elapsed_sec": round(elapsed, 2),
            "docs_per_sec": round(len(s_docs) / elapsed, 2) if elapsed > 0 else 0.0,
        }
        with open(shard_done_file, "w", encoding="utf-8") as f:
            json.dump(shard_res, f, indent=2, ensure_ascii=False)

        shard_results[s_idx] = shard_res
        print(f"  Shard {s_idx + 1}/{len(shard_partitions)} done in {elapsed:.2f}s ({shard_res['docs_per_sec']} docs/sec).")

    # 7. Merge shard rowmaps & assemble FAISS IndexFlatIP
    print("Merging shards into final FAISS IndexFlatIP...")
    final_index = faiss.IndexFlatIP(BGE_DENSE_DIMENSION)
    final_rowmap_path = output_dir / "qwen_bge_rowmap.jsonl"

    global_row_counter = 0
    with open(final_rowmap_path, "w", encoding="utf-8") as f_out:
        for s_res in shard_results:
            s_idx = s_res["shard_index"]
            npy_path = shards_dir / f"embeddings_shard_{s_idx:03d}.npy"
            rowmap_path = shards_dir / f"rowmap_shard_{s_idx:03d}.jsonl"

            mat = np.load(npy_path)
            final_index.add(mat)

            with open(rowmap_path, "r", encoding="utf-8") as f_in:
                for line in f_in:
                    rec = json.loads(line)
                    rec["dense_row"] = global_row_counter
                    f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    global_row_counter += 1

    if global_row_counter != eligible_count or final_index.ntotal != eligible_count:
        raise RuntimeError(
            f"FAISS index count ({final_index.ntotal}) or rowmap count ({global_row_counter}) != eligible ({eligible_count})"
        )

    # 8. Write final FAISS index
    final_faiss_path = output_dir / "qwen_bge.faiss"
    faiss.write_index(final_index, str(final_faiss_path))

    index_sha = sha256_file(final_faiss_path)
    rowmap_sha = sha256_file(final_rowmap_path)
    total_wall_sec = time.perf_counter() - t_start

    passport = {
        "status": "PASS",
        "artifact_id": "qwen_bge_v1",
        "lane_id": "qwen_bge",
        "artifact_type": "FAISS_INDEX",
        "entity_type": "FRAME",
        "frame_space": "CUSTOM",
        "model_id": model_id,
        "pooling": "CLS_L2_NORMALIZED",
        "tokenization": "max_length_512",
        "document_policy_id": DOCUMENT_POLICY_ID,
        "included_fields": INCLUDED_FIELDS,
        "excluded_fields": EXCLUDED_FIELDS,
        "serialization_version": "v1_labeled",
        "canonical_qwen_rows": total_qwen,
        "eligible_document_rows": eligible_count,
        "empty_document_rows": empty_doc_count,
        "empty_caption_rows": empty_caption_count,
        "dimension": BGE_DENSE_DIMENSION,
        "dtype": "float32",
        "normalized": True,
        "metric": "INNER_PRODUCT",
        "index_type": "IndexFlatIP",
        "index_rows": final_index.ntotal,
        "rowmap_rows": global_row_counter,
        "index_file": str(final_faiss_path.name),
        "index_sha256": index_sha,
        "rowmap_file": str(final_rowmap_path.name),
        "rowmap_sha256": rowmap_sha,
        "shards": len(shard_partitions),
        "total_wall_sec": round(total_wall_sec, 2),
        "docs_per_sec": round(eligible_count / total_wall_sec, 2) if total_wall_sec > 0 else 0.0,
        "device": resolved_device,
        "gpu_name": gpu_name,
        "gpu_vram_gb": total_vram_gb,
        "model_processes": 1,
        "batch_size": batch_size,
        "cpu_fallback_events": 0,
        "probe_results": probe_results,
    }

    with open(output_dir / "qwen_bge_passport.json", "w", encoding="utf-8") as f:
        json.dump(passport, f, indent=2, ensure_ascii=False)

    done_payload = {
        "status": "PASS",
        "artifact_id": "qwen_bge_v1",
        "index_rows": final_index.ntotal,
        "rowmap_rows": global_row_counter,
        "eligible_docs": eligible_count,
        "empty_docs": empty_doc_count,
        "total_shards": len(shard_partitions),
        "index_sha256": index_sha,
        "rowmap_sha256": rowmap_sha,
        "passport_sha256": sha256_file(output_dir / "qwen_bge_passport.json"),
        "total_wall_sec": round(total_wall_sec, 2),
    }

    with open(output_dir / "DONE.json", "w", encoding="utf-8") as f:
        json.dump(done_payload, f, indent=2, ensure_ascii=False)

    print(f"\nQwen BGE Index build COMPLETE in {total_wall_sec:.2f}s.")
    return passport


# ---------------------------------------------------------------------------
# Qwen BGE Runtime Index Class
# ---------------------------------------------------------------------------
class QwenBgeIndex:
    """Runtime FAISS Index wrapper for Qwen BGE semantic dense retrieval."""

    def __init__(self, artifact_dir: str | Path):
        self.artifact_dir = Path(artifact_dir)
        self.faiss_path = self.artifact_dir / "qwen_bge.faiss"
        self.rowmap_path = self.artifact_dir / "qwen_bge_rowmap.jsonl"
        self.passport_path = self.artifact_dir / "qwen_bge_passport.json"

        if not self.faiss_path.is_file():
            raise FileNotFoundError(f"Missing FAISS index: {self.faiss_path}")
        if not self.rowmap_path.is_file():
            raise FileNotFoundError(f"Missing rowmap: {self.rowmap_path}")

        self.index = faiss.read_index(str(self.faiss_path))
        self.rowmap: list[dict[str, Any]] = []
        self._video_to_rows: dict[str, list[int]] = {}

        with open(self.rowmap_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                entry = json.loads(line)
                self.rowmap.append(entry)
                v_id = entry.get("video_id")
                if v_id:
                    self._video_to_rows.setdefault(v_id, []).append(idx)

        self.passport: dict[str, Any] = {}
        if self.passport_path.is_file():
            self.passport = json.loads(self.passport_path.read_text(encoding="utf-8"))

    @property
    def total_rows(self) -> int:
        return self.index.ntotal

    def search(
        self,
        query_vector: np.ndarray,
        *,
        top_k: int = 50,
        candidate_video_ids: Sequence[str] | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """Search FAISS IndexFlatIP for top-k closest vectors."""
        if self.total_rows == 0 or top_k <= 0:
            return []

        query_vector = np.ascontiguousarray(query_vector, dtype=np.float32)
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)

        norm = np.linalg.norm(query_vector, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        query_vector = query_vector / norm

        if candidate_video_ids is not None:
            scoped_vids = {v.strip() for v in candidate_video_ids if v and v.strip()}
            if not scoped_vids:
                return []

            candidate_row_count = sum(len(self._video_to_rows.get(vid, [])) for vid in scoped_vids)
            if candidate_row_count == 0:
                return []

            overfetch_k = min(self.total_rows, max(top_k * 10, 500))
            distances, indices = self.index.search(query_vector, overfetch_k)

            results: list[tuple[dict[str, Any], float]] = []
            for dense_idx, score in zip(indices[0], distances[0]):
                if dense_idx < 0 or dense_idx >= len(self.rowmap):
                    continue
                meta = self.rowmap[dense_idx]
                if meta.get("video_id") in scoped_vids:
                    results.append((meta, float(score)))
                    if len(results) >= top_k:
                        break
            return results

        distances, indices = self.index.search(query_vector, min(top_k, self.total_rows))
        results = []
        for dense_idx, score in zip(indices[0], distances[0]):
            if dense_idx < 0 or dense_idx >= len(self.rowmap):
                continue
            meta = self.rowmap[dense_idx]
            results.append((meta, float(score)))
        return results
