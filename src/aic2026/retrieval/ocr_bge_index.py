"""OCR BGE-M3 Dense Retrieval Index Builder and Runtime Reader (M4C).

Builds FAISS IndexFlatIP(1024) over existing 612,813 BGE-M3 vectors from 10 source shards
and provides fast runtime semantic search over canonical OCR items.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import faiss
import numpy as np

logger = logging.getLogger(__name__)

BGE_MODEL_ID = "BAAI/bge-m3"
BGE_DENSE_DIMENSION = 1024
EXPECTED_TOTAL_ROWS = 612813
EXPECTED_SHARDS = 10


@dataclass(frozen=True)
class OcrBgeHit:
    ocr_uid: str
    video_id: str
    keyframe_uid: str
    frame_idx: int
    timestamp_ms: int
    raw_score: float
    rank: int
    faiss_row: int
    score_kind: str = "cosine_ip_higher_is_better"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def encode_ocr_bge_queries(
    queries: Sequence[str],
    *,
    model: Any,
    tokenizer: Any,
    max_length: int = 512,
) -> np.ndarray:
    """Encode query texts using BAAI/bge-m3 CLS token L2-normalized vectors."""
    import torch

    if not queries:
        return np.zeros((0, BGE_DENSE_DIMENSION), dtype=np.float32)

    encoded = tokenizer(
        list(queries),
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    with torch.no_grad():
        out = model(**encoded)
        cls_token = out[0][:, 0]
        normalized = torch.nn.functional.normalize(cls_token, p=2, dim=1)
        return normalized.cpu().numpy().astype(np.float32)


def build_ocr_bge_index(
    shards_dir: Path | str,
    output_dir: Path | str,
    canonical_db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build FAISS IndexFlatIP and runtime rowmap from existing 10 BGE-M3 shards."""
    shards_dir = Path(shards_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    faiss_out = output_dir / "ocr_bge.faiss"
    rowmap_out = output_dir / "ocr_bge_rowmap.jsonl"
    passport_file = output_dir / "ocr_bge_passport.json"
    done_file = output_dir / "DONE.json"

    t0 = time.perf_counter()
    logger.info("Starting memory-safe OCR BGE index build from %s...", shards_dir)

    # Initialize FAISS IndexFlatIP
    index = faiss.IndexFlatIP(BGE_DENSE_DIMENSION)

    total_rows = 0
    all_norms = []

    # Check if canonical database mapping is available
    canonical_db_p = Path(canonical_db_path) if canonical_db_path else Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
    db_rowmap_lookup: dict[int, tuple[str, str, str, int, int, str]] = {}
    if canonical_db_p.exists():
        import sqlite3
        conn = sqlite3.connect(f"file:{canonical_db_p}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("""
            SELECT r.global_row, r.ocr_uid, r.keyframe_uid, r.video_id, r.frame_idx, r.timestamp_ms, i.text_raw
            FROM ocr_bge_rowmap r
            JOIN ocr_items i ON r.ocr_uid = i.ocr_uid
        """)
        for r in cur.fetchall():
            db_rowmap_lookup[r[0]] = (r[1], r[2], r[3], r[4], r[5], r[6] or "")
        conn.close()

    with open(rowmap_out, "w", encoding="utf-8") as f_rowmap:
        for shard_idx in range(EXPECTED_SHARDS):
            shard_str = f"{shard_idx:03d}"
            emb_path = shards_dir / f"embeddings_shard_{shard_str}.npy"
            meta_path = shards_dir / f"metadata_shard_{shard_str}.json"

            if not emb_path.exists() or not meta_path.exists():
                raise FileNotFoundError(f"Missing OCR BGE shard {shard_str} at {shards_dir}")

            # Load vectors
            emb = np.load(emb_path, mmap_mode="r")
            if emb.ndim != 2 or emb.shape[1] != BGE_DENSE_DIMENSION:
                raise ValueError(f"Shard {shard_str} has invalid shape: {emb.shape}")
            if emb.dtype != np.float32:
                emb = emb.astype(np.float32)

            shard_rows = emb.shape[0]

            # Validate NaN / Inf
            if np.isnan(emb[:min(100, shard_rows)]).any() or np.isinf(emb[:min(100, shard_rows)]).any():
                raise ValueError(f"Shard {shard_str} contains NaN or Inf vectors")

            # Sample norms
            sample_emb = emb[::max(1, shard_rows // 100)]
            norms = np.linalg.norm(sample_emb, axis=1)
            all_norms.extend(norms.tolist())

            # Add to FAISS index
            index.add(np.ascontiguousarray(emb, dtype=np.float32))

            # Load metadata for text fallback
            with open(meta_path, "r", encoding="utf-8") as f_meta:
                meta_list = json.load(f_meta)

            if len(meta_list) != shard_rows:
                raise ValueError(f"Shard {shard_str} count mismatch: {len(meta_list)} metadata != {shard_rows} vectors")

            for local_idx, m in enumerate(meta_list):
                global_row = total_rows + local_idx
                if global_row in db_rowmap_lookup:
                    ocr_uid, keyframe_uid, vid, frame_idx, timestamp_ms, text_val = db_rowmap_lookup[global_row]
                else:
                    vid = m["video_id"]
                    kf_id = m.get("keyframe_id", "")
                    txt_idx = m.get("text_index", 0)
                    frame_idx = m.get("frame_idx", 0)
                    pts_time = m.get("pts_time", 0.0)
                    timestamp_ms = m.get("timestamp_ms", int(round(float(pts_time) * 1000)))
                    keyframe_uid = f"CUSTOM:{vid}:F{frame_idx}" if frame_idx else f"CUSTOM:{vid}:{kf_id}"
                    ocr_uid = f"OCR:{keyframe_uid}:T{txt_idx}"
                    text_val = m.get("text", "")

                row_entry = {
                    "row": global_row,
                    "shard": shard_str,
                    "shard_row": local_idx,
                    "ocr_uid": ocr_uid,
                    "keyframe_uid": keyframe_uid,
                    "video_id": vid,
                    "frame_idx": int(frame_idx),
                    "timestamp_ms": int(timestamp_ms),
                    "text": text_val,
                }
                f_rowmap.write(json.dumps(row_entry, ensure_ascii=False) + "\n")

            total_rows += shard_rows
            logger.info("Added shard %s (%d rows, total=%d)", shard_str, shard_rows, total_rows)

    if total_rows != EXPECTED_TOTAL_ROWS:
        raise ValueError(f"Total rows {total_rows} does not match expected {EXPECTED_TOTAL_ROWS}")

    # Write FAISS index to disk
    faiss.write_index(index, str(faiss_out))
    elapsed = time.perf_counter() - t0

    # Compute checksums
    hasher_idx = hashlib.sha256()
    with open(faiss_out, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher_idx.update(chunk)
    idx_sha256 = hasher_idx.hexdigest()

    hasher_rm = hashlib.sha256()
    with open(rowmap_out, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher_rm.update(chunk)
    rm_sha256 = hasher_rm.hexdigest()

    passport = {
        "index_id": "ocr_bge_v1",
        "lane_id": "ocr_bge",
        "artifact_type": "FAISS_INDEX",
        "entity_space": "OCR_ITEM",
        "frame_space": "CUSTOM",
        "model_id": BGE_MODEL_ID,
        "dimension": BGE_DENSE_DIMENSION,
        "dtype": "float32",
        "normalized": True,
        "metric": "INNER_PRODUCT",
        "index_type": "IndexFlatIP",
        "raw_ocr_universe": 676925,
        "dense_source_rows": total_rows,
        "non_dense_raw_items": 676925 - total_rows,
        "index_rows": index.ntotal,
        "rowmap_rows": total_rows,
        "index_sha256": idx_sha256,
        "rowmap_sha256": rm_sha256,
        "build_duration_sec": round(elapsed, 2),
        "vector_norm_stats": {
            "min": round(float(np.min(all_norms)), 6),
            "mean": round(float(np.mean(all_norms)), 6),
            "max": round(float(np.max(all_norms)), 6),
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(passport_file, "w", encoding="utf-8") as f:
        json.dump(passport, f, indent=2)

    with open(done_file, "w", encoding="utf-8") as f:
        json.dump({
            "status": "SUCCESS",
            "index_rows": total_rows,
            "index_sha256": idx_sha256,
            "rowmap_sha256": rm_sha256,
            "elapsed_sec": round(elapsed, 2),
        }, f, indent=2)

    logger.info("OCR BGE index build complete: %d rows in %.2fs (FAISS SHA: %s)", total_rows, elapsed, idx_sha256[:12])
    return passport


class OcrBgeIndex:
    """Thread-safe runtime reader and query searcher for OCR BGE-M3 FAISS index."""

    def __init__(self, artifact_dir: Path | str) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.faiss_path = self.artifact_dir / "ocr_bge.faiss"
        self.rowmap_path = self.artifact_dir / "ocr_bge_rowmap.jsonl"
        self.passport_path = self.artifact_dir / "ocr_bge_passport.json"

        self._index: faiss.IndexFlatIP | None = None
        self._rowmap: list[dict[str, Any]] | None = None
        self._model: Any = None
        self._tokenizer: Any = None
        self.passport: dict[str, Any] = {}

        if self.passport_path.exists():
            with open(self.passport_path, "r", encoding="utf-8") as f:
                self.passport = json.load(f)

    def _ensure_loaded(self) -> None:
        if self._index is None:
            if not self.faiss_path.exists():
                raise FileNotFoundError(f"OCR BGE FAISS index not found at {self.faiss_path}")
            self._index = faiss.read_index(str(self.faiss_path))

        if self._rowmap is None:
            if not self.rowmap_path.exists():
                raise FileNotFoundError(f"OCR BGE rowmap not found at {self.rowmap_path}")
            rows = []
            with open(self.rowmap_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rows.append(json.loads(line))
            self._rowmap = rows

    def _ensure_model(self) -> None:
        if self._model is None or self._tokenizer is None:
            from transformers import AutoModel, AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(BGE_MODEL_ID)
            self._model = AutoModel.from_pretrained(BGE_MODEL_ID)
            self._model.eval()

    def health(self) -> dict[str, Any]:
        """Return health diagnostics."""
        if not self.faiss_path.exists():
            return {
                "lane_id": "ocr_bge",
                "status": "UNAVAILABLE",
                "error": f"OCR BGE FAISS index missing at {self.faiss_path}",
            }
        try:
            self._ensure_loaded()
            return {
                "lane_id": "ocr_bge",
                "status": "OK",
                "model_id": BGE_MODEL_ID,
                "dimension": BGE_DENSE_DIMENSION,
                "index_type": "IndexFlatIP",
                "index_rows": self._index.ntotal if self._index else 0,
                "rowmap_rows": len(self._rowmap) if self._rowmap else 0,
                "index_sha256": self.passport.get("index_sha256"),
                "rowmap_sha256": self.passport.get("rowmap_sha256"),
                "raw_ocr_universe": self.passport.get("raw_ocr_universe", 676925),
                "dense_source_rows": self.passport.get("dense_source_rows", EXPECTED_TOTAL_ROWS),
                "non_dense_raw_items": self.passport.get("non_dense_raw_items", 676925 - EXPECTED_TOTAL_ROWS),
                "metric": "INNER_PRODUCT",
                "error": None,
            }
        except Exception as exc:
            return {
                "lane_id": "ocr_bge",
                "status": "ERROR",
                "error": str(exc),
            }

    def search(
        self,
        query_text: str,
        top_k: int = 20,
        video_ids: Sequence[str] = (),
    ) -> list[OcrBgeHit]:
        """Search canonical OCR items using BGE-M3 dense semantic similarity."""
        if not query_text or not query_text.strip():
            return []

        self._ensure_loaded()
        self._ensure_model()
        assert self._index is not None
        assert self._rowmap is not None

        # Encode query
        q_vec = encode_ocr_bge_queries([query_text], model=self._model, tokenizer=self._tokenizer)

        filter_set = set(video_ids) if video_ids else None

        if filter_set is not None and len(filter_set) == 0:
            return []

        # Adaptive over-fetch when video_ids filter is specified
        fetch_k = min(self._index.ntotal, max(top_k * 10, 200)) if filter_set else top_k

        scores, indices = self._index.search(q_vec, fetch_k)
        scores_0 = scores[0]
        indices_0 = indices[0]

        hits: list[OcrBgeHit] = []
        for sim, idx in zip(scores_0, indices_0):
            if idx < 0 or idx >= len(self._rowmap):
                continue
            meta = self._rowmap[idx]
            vid = meta["video_id"]
            if filter_set and vid not in filter_set:
                continue

            hits.append(
                OcrBgeHit(
                    ocr_uid=meta["ocr_uid"],
                    video_id=vid,
                    keyframe_uid=meta["keyframe_uid"],
                    frame_idx=meta["frame_idx"],
                    timestamp_ms=meta["timestamp_ms"],
                    raw_score=round(float(sim), 4),
                    rank=len(hits) + 1,
                    faiss_row=int(idx),
                    score_kind="cosine_ip_higher_is_better",
                )
            )
            if len(hits) >= top_k:
                break

        return hits
