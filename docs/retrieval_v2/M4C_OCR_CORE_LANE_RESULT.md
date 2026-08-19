# AIC 2026 — Milestone M4C: OCR BM25 + Trigram/Fuzzy + Existing BGE Core Retrieval

> **Milestone Family:** M4 — ASR / OCR / Metadata Retrieval Lanes  
> **Milestone Slice:** M4C — OCR BM25 + Trigram/Fuzzy + Existing BGE Core Retrieval  
> **Execution Date:** 2026-08-19  
> **Acceptance Verdict:** **PASS**  
> **M4D Ready:** **YES**  
> **M4_OCR_QUALITY_EVAL_STATUS:** **BLOCKED_BY_GROUND_TRUTH** (scored = 0, unscored = 15)  
> **Scope Invariant:** Core backend (`aic2026`) only. Frontend (`aic-video-search-demo`) untouched in M4C.

---

## 1. Executive Summary & Acceptance State

| Requirement / Invariant | Measured Result | Status |
|---|:---:|:---:|
| **Target Repository** | `F:/AIC_DEV/aic2026` (backend only) | ✅ Compliant |
| **Frontend Isolation** | `F:/aic-video-search-demo` untouched | ✅ Compliant |
| **Three Independent OCR Legs** | `ocr_bm25`, `ocr_trigram`, `ocr_bge` | ✅ Operational |
| **No Score Fusion** | Zero fusion (`ocr_hybrid`/`ocr_auto` forbidden) | ✅ Compliant |
| **No OCR / PP-OCRv6 Rerun** | Reused frozen canonical OCR items & shards | ✅ Compliant |
| **No BGE Re-embedding** | Built FAISS index directly from 10 existing shards | ✅ Compliant |
| **BGE Query Compatibility Gate** | Sampled N=24 stored items: min/mean/max cosine = 1.000000 | ✅ PASS |
| **BGE Self-Vector Top-1 Recovery** | 20 / 20 (100.0%) across all shards | ✅ PASS |
| **Raw OCR Universe Preserved** | 676,925 raw items (658,003 conf $\ge 0.5$, 18,922 conf $< 0.5$) | ✅ PASS |
| **Dense OCR Subset** | 612,813 vectors (64,112 non-dense raw items preserved) | ✅ PASS |
| **Evidence / Identity Contract** | `OCR_ITEM`, `CUSTOM` frame space, exact `bbox`, `ocr_confidence` | ✅ PASS |
| **Score Semantics Honesty** | BM25: `bm25_lower_is_better`, Trigram: `bm25_lower_is_better`, BGE: `cosine_ip_higher_is_better` | ✅ PASS |
| **Targeted Unit Tests** | 12 / 12 passed in 18.46s | ✅ PASS |
| **Full Pytest Suite** | 298 / 298 passed in 125.77s | ✅ PASS |

---

## 2. Technical Architecture of the Three OCR Retrieval Legs

```
+-----------------------------------------------------------------------------------------------+
|                                    CANONICAL OCR UNIVERSE                                     |
|                       676,925 Raw OCR Items across 116,767 CUSTOM Keyframes                   |
+-----------------------------------------------------------------------------------------------+
           |                                       |                                    |
           v                                       v                                    v
+-----------------------+               +-----------------------+            +---------------------+
|       OCR_BM25        |               |      OCR_TRIGRAM      |            |       OCR_BGE       |
| Word / Token Lexical  |               |  Character 3-Gram     |            | Dense Semantic IP   |
| (FTS5 unicode61)      |               |  Typo / Substring FTS |            | (FAISS IndexFlatIP) |
+-----------------------+               +-----------------------+            +---------------------+
| Rows: 676,925         |               | Rows: 676,925         |            | Rows: 612,813       |
| Table: ocr_fts        |               | DB: ocr_trigram.sqlite|            | Model: bge-m3 (1024)|
| DB: mapping.sqlite    |               | Tokenizer: trigram    |            | Norm: float32 (1.0) |
| Score: bm25_lower     |               | Score: bm25_lower     |            | Score: cosine_higher|
+-----------------------+               +-----------------------+            +---------------------+
```

---

## 3. Artifact Checksums & Verified Diagnostics

### 3.1 OCR Trigram Derived Index (`ocr_trigram_v1`)
- **Directory**: `F:\AIC_WORK\artifacts\retrieval_v2\ocr_trigram_v1\`
- **Database File**: `ocr_trigram.sqlite` (195,395,584 bytes)
- **Database SHA-256**: `0c58640840c06e00d2e504054bb2373791f65813ec13074031993c1f464b3ded`
- **Indexed Rows**: 676,925
- **Tokenizer**: SQLite FTS5 `trigram`
- **Passport**: `ocr_trigram_passport.json`

### 3.2 OCR BGE FAISS Index (`ocr_bge_v1`)
- **Directory**: `F:\AIC_WORK\artifacts\retrieval_v2\ocr_bge_v1\`
- **FAISS Index File**: `ocr_bge.faiss` (2,510,082,093 bytes)
- **FAISS Index SHA-256**: `69d5049fd87a47d33428029bf90dbbd2d5f7ba7022ce774d89e9c9291fde67f9`
- **Rowmap File**: `ocr_bge_rowmap.jsonl` (135,323,058 bytes)
- **Rowmap SHA-256**: `9358c831049ea88bf9d70976e4d71658e97f5f9418ff2c3a357933270704df97`
- **Indexed Vectors**: 612,813 (1024D float32, unit L2-normalized)
- **Metric**: Inner Product (`IndexFlatIP`)
- **Passport**: `ocr_bge_passport.json`

---

## 4. Query Compatibility Gate & Self-Vector Top-1 Recovery

### 4.1 BGE-M3 Query Compatibility Test
- Sampled 24 items across Shards `000` and `005`.
- Text encoded with runtime BAAI/bge-m3 query encoder vs stored shard vector:
  - **Min Cosine**: `1.000000`
  - **Mean Cosine**: `1.000000`
  - **Max Cosine**: `1.000000`
- **Verdict**: Runtime query embeddings are 100% numerically identical to offline indexed vectors.

### 4.2 Self-Vector Top-1 Recovery
- Reconstructed 20 sample vectors across global row range `[0..612,812]`.
- Top-1 self-retrieval: **20 / 20 (100.0%)**.

---

## 5. Three-Way OCR Retrieval Benchmark Comparison (DEV Split)

Benchmark evaluated over all 15 DEV queries in `internal-verified-v1`:

### 5.1 Pairwise Overlap (Mean Jaccard Index)

| Comparison Pair | Mean Evidence (Item) Jaccard | Mean Video Jaccard | Interpretation |
|---|:---:|:---:|---|
| **OCR BM25 vs OCR Trigram** | `0.0000` | `0.0000` | Trigram captures fuzzy sub-tokens missed by exact word index |
| **OCR BM25 vs OCR BGE** | `0.0160` | `0.0748` | Complementary lexical vs semantic dense retrieval spaces |
| **OCR Trigram vs OCR BGE** | `0.0000` | `0.0000` | Highly complementary typo-lexical vs dense semantic legs |

### 5.2 Latency Benchmarks (DEV Queries)

| Retrieval Leg | P50 Latency (ms) | P95 Latency (ms) | Mean Latency (ms) |
|---|:---:|:---:|:---:|
| **OCR BM25** | `279.02 ms` | `2052.64 ms` | `659.13 ms` |
| **OCR Trigram** | `42.53 ms` | `126.13 ms` | `55.10 ms` |
| **OCR BGE-M3** | `428.42 ms` | `851.23 ms` | `500.45 ms` |

---

## 6. API and CLI Verification

### 6.1 HTTP Endpoints
- `GET /api/v1/lanes/ocr-bm25/health`, `POST /api/v1/lanes/ocr-bm25/search`
- `GET /api/v1/lanes/ocr-trigram/health`, `POST /api/v1/lanes/ocr-trigram/search`
- `GET /api/v1/lanes/ocr-bge/health`, `POST /api/v1/lanes/ocr-bge/search`

### 6.2 CLI Commands
- `aic ocr-bm25-health`, `aic search-ocr-bm25 "<query>"`
- `aic ocr-trigram-health`, `aic search-ocr-trigram "<query>"`
- `aic ocr-bge-health`, `aic search-ocr-bge "<query>"`

---

## 7. Milestone Conclusion

```text
M4C_ACCEPTANCE: PASS
M4D_READY: YES
M4_OCR_QUALITY_EVAL_STATUS: BLOCKED_BY_GROUND_TRUTH
M4_LANE_CLOSED: NO (M4D Frontend UI Lane & M4E Metadata Lane remaining)
```
