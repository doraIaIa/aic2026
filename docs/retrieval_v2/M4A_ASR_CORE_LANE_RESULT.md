# M4A Acceptance Report — ASR BM25 + BGE-M3 Core Retrieval Lane

- **Milestone**: `M4 — ASR / OCR / Metadata Retrieval Lanes`
- **Internal Slice**: `M4A — ASR BM25 + BGE-M3 Core Retrieval Lane`
- **Date**: 2026-08-19
- **Repository**: `F:/AIC_DEV/aic2026`
- **Final Commit**: `e94c1ff0cf9a5b74ffd61fc99edcb88e7f457d4e` (`feat(retrieval): add asr bm25 and bge lanes`)
- **Target Branch**: `main`

---

## 1. Executive Summary & Authoritative Operational State

```ini
M4A_ACCEPTANCE = PASS
M4_ASR_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH
M4B_READY = YES
```

Milestone M4A establishes the first text-evidence retrieval subsystem in the Retrieval V2 architecture. It delivers **TWO independent, production-grade ASR retrieval legs** over the frozen canonical universe of **107,540 Whisper-medium Vietnamese ASR segments**:

1. **`asr_bm25`**: SQLite FTS5 lexical BM25 retrieval over `asr_fts` with safe query escaping and NFC/accentless normalization.
2. **`asr_bge`**: `BAAI/bge-m3` dense semantic embedding retrieval via an exact `IndexFlatIP(1024)` FAISS index and deterministic rowmap.

Both legs adhere to the unified `SearchProvider` contract, return segment evidence (`ProviderHit`), remain separately benchmarkable, and **are NOT score-fused in M4A**.

---

## 2. Canonical ASR Corpus & Provenance

| Metric / Invariant | Authority Value | M4A Measured Status | Result |
| :--- | :--- | :--- | :--- |
| Canonical ASR Segments | 107,540 | 107,540 | **EXACT MATCH** |
| Videos Represented | 873 | 873 | **EXACT MATCH** |
| Videos with $\ge 1$ Segment (`HAS_SEGMENTS`) | 859 | 859 | **EXACT MATCH** |
| Zero-ASR Videos (`ZERO_ASR_SEGMENTS`) | 14 | 14 | **EXACT MATCH** |
| Segment UID Format | `ASR:<video_id>:<source_segment_id>` | `ASR:<video_id>:<source_segment_id>` | **VALID** |
| ASR Model / Language | `Whisper-medium` / `vi` | `Whisper-medium` / `vi` | **FROZEN** |
| Text Modification / LLM Translation | None | None | **UNTOUCHED** |

---

## 3. Retrieval Leg 1: ASR BM25 (Lexical)

### 3.1 Implementation Architecture
- **Provider Class**: `AsrBm25Provider` in [`src/aic2026/retrieval/providers/asr_bm25.py`](file:///F:/AIC_DEV/aic2026/src/aic2026/retrieval/providers/asr_bm25.py)
- **FTS5 Table**: `asr_fts` in `mapping.sqlite` (107,540 indexed rows)
- **Normalizer**: `TextNormalizer` (`v1_nfc_accentless` NFC normalization + diacritic stripping)
- **Query Strategy**:
  1. Conjunctive AND match with quote escaping (`"token1" AND "token2"...`)
  2. Disjunctive OR match fallback (`"token1" OR "token2"...`)
  3. Accentless fallback (`text_accentless: "token1" OR "token2"...`)
- **Score Semantics**: `bm25_lower_is_better` (raw SQLite BM25 ranking; lower/more negative is better; never labeled as confidence).
- **Candidate Scoping**: Direct SQL filtering `f.video_id IN (...)`.

### 3.2 Operational Health
```json
{
  "lane_id": "asr_bm25",
  "status": "OK",
  "sqlite_reachable": true,
  "sqlite_version": "3.45.1",
  "fts5_available": true,
  "fts_table": "asr_fts",
  "fts_rows": 107540,
  "canonical_asr_segments": 107540,
  "videos_with_segments": 859,
  "zero_asr_videos": 14,
  "tokenizer": "unicode61",
  "normalizer_version": "v1_nfc_accentless"
}
```

---

## 4. Retrieval Leg 2: ASR BGE-M3 (Dense Semantic)

### 4.1 Implementation Architecture
- **Provider Class**: `AsrBgeProvider` in [`src/aic2026/retrieval/providers/asr_bge.py`](file:///F:/AIC_DEV/aic2026/src/aic2026/retrieval/providers/asr_bge.py)
- **Index Engine**: `AsrBgeIndex` in [`src/aic2026/retrieval/asr_bge_index.py`](file:///F:/AIC_DEV/aic2026/src/aic2026/retrieval/asr_bge_index.py)
- **Model**: `BAAI/bge-m3` via HuggingFace `transformers`
- **Dense Contract**: `[CLS]` token pooling + L2 normalization (`torch.nn.functional.normalize(p=2, dim=1)`), float32, 1024 dimensions. Identical encoding contract for corpus and query.
- **FAISS Metric**: `IndexFlatIP(1024)` (exact cosine inner product).
- **Candidate Scoping**: Adaptive overfetch with set filtering.

### 4.2 Production Artifacts
- **Artifact Directory**: `F:/AIC_WORK/artifacts/retrieval_v2/asr_bge_v1/`
- **FAISS Index File**: `asr_bge.faiss` (440,483,885 bytes, 107,540 rows)
- **Index Checksum (SHA256)**: `b084d12764697e7c23b25ec70f02c67a1d7b6a9c461b8c0ca629626edeabc8ff`
- **Rowmap File**: `asr_bge_rowmap.jsonl` (38,819,773 bytes, 107,540 rows)
- **Rowmap Checksum (SHA256)**: `f12af969af87d28f49412d28a88099506aa17409d243ac09a9d5403449dc2799`
- **Shards**: 20 deterministic shards (shards 000..019) with individual `.npy`, `.jsonl`, and `DONE_xxx.json` manifests.
- **Build Duration**: 5,343.16s (~89m) across 4 parallel worker processes.

### 4.3 Self-Vector Top-1 Verification
- **Test Set**: 20 deterministic distinct-text segment vectors reconstructed from FAISS.
- **Result**: **`20 / 20 PASS`** (Top-1 returned same segment row / vector with score 1.000000).

---

## 5. DEV Benchmark Evaluation (15 Queries)

Evaluated against the DEV query split in `F:/AIC_WORK/artifacts/evaluation/internal-verified-v1/`.

### 5.1 Quality Evaluation Status
> [!IMPORTANT]
> **`M4_ASR_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH`**
> 
> Across all 15 DEV queries, verified ground truth contains `scored = 0, unscored = 15`. Therefore, while operational retrieval and candidate recall are fully functional, **no quality/recall claims are made**.

### 5.2 Performance & Latency Metrics
| Metric | ASR BM25 (`asr_bm25`) | ASR BGE-M3 (`asr_bge`) |
| :--- | :--- | :--- |
| **Total Queries** | 15 | 15 |
| **Scored Queries** | 0 | 0 |
| **Unscored Queries** | 15 | 15 |
| **Empty Results** | 0 (0.0%) | 0 (0.0%) |
| **Mean Latency** | 441.21 ms | 250.83 ms |
| **p50 Latency** | 418.77 ms | 238.50 ms |
| **p95 Latency** | 660.81 ms | 356.92 ms |
| **Min / Max Latency** | 212.81 ms / 1029.89 ms | 172.50 ms / 441.96 ms |
| **Score Semantics** | `bm25_lower_is_better` | `cosine_ip_higher_is_better` |

### 5.3 Paired Comparison & Candidate Diversity
Paired comparison over the identical 15 queries and `Top-K = 20`:

| Paired Diversity Metric | Value |
| :--- | :--- |
| **Candidate Video-set Jaccard (Mean)** | `0.1003` (10.03% overlap) |
| **Candidate Video-set Jaccard (Median)** | `0.1034` (10.34% overlap) |
| **Mean Shared Candidate Videos** | `2.80` videos / query |
| **Mean BM25-Exclusive Candidate Videos** | `12.47` videos / query |
| **Mean BGE-Exclusive Candidate Videos** | `14.40` videos / query |

**Conclusion**: BM25 and BGE-M3 exhibit strong complementarity (only ~10% candidate overlap), confirming that lexical and dense semantic ASR retrieval cover distinct evidence surfaces.

---

## 6. CLI and API Contracts

### 6.1 CLI Surface
- `aic build-asr-bge [--db DB] [--out-dir OUT] [--shards N] [--workers W] [--threads T]`
- `aic search-asr-bm25 "<query>" [--top-k K] [--video-id VID] [--json]`
- `aic asr-bm25-health`
- `aic search-asr-bge "<query>" [--top-k K] [--video-id VID] [--json]`
- `aic asr-bge-health`

### 6.2 HTTP API Endpoints
- `GET  /api/v1/lanes/asr-bm25/health`
- `POST /api/v1/lanes/asr-bm25/search`
- `GET  /api/v1/lanes/asr-bge/health`
- `POST /api/v1/lanes/asr-bge/search`

---

## 7. Test Suite Status

- **Baseline Test Suite**: 266 tests passing
- **M4A Test Additions**: +20 new tests
  - [`tests/test_asr_bm25_lane.py`](file:///F:/AIC_DEV/aic2026/tests/test_asr_bm25_lane.py) (8 tests)
  - [`tests/test_asr_bge_index.py`](file:///F:/AIC_DEV/aic2026/tests/test_asr_bge_index.py) (3 tests)
  - [`tests/test_asr_bge_lane.py`](file:///F:/AIC_DEV/aic2026/tests/test_asr_bge_lane.py) (3 tests)
  - [`tests/test_asr_benchmark.py`](file:///F:/AIC_DEV/aic2026/tests/test_asr_benchmark.py) (1 test)
  - [`tests/test_search_api_asr.py`](file:///F:/AIC_DEV/aic2026/tests/test_search_api_asr.py) (5 tests)
- **Final Backend Test Result**: **`286 passed in 59.71s (100% PASS)`**
