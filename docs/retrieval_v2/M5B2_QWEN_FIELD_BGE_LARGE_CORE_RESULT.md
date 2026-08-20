# M5B2 — External Field-Aware BGE-Large Core Provider Acceptance Report

## 1. Executive Verdict
- **Milestone Acceptance:** `PASS`
- **M5C Ready:** `YES`
- **M5 Overall Status:** `OPEN`
- **Quality Evaluation Status:** `BLOCKED_BY_GROUND_TRUTH` (scored = 0, unscored = 15)
- **Corpus Embedding Rows Created by M5B2:** `0`
- **FAISS Indexes Created by M5B2:** `0`
- **FAISS Indexes Modified by M5B2:** `0`
- **Qwen Inference Rows Created by M5B2:** `0`
- **Shared Source / Canonical / M1 Runtime Mutations:** `0`
- **Frontend Changes:** `0`

---

## 2. Core Baseline & Git Lineage
- **Repository:** `F:/AIC_DEV/aic2026`
- **Branch:** `main`
- **Starting HEAD:** `f8c50e5a8e79e5fae5e282f924c65283edc52384`
- **Baseline Test Suite:** `341 passed, 2 skipped`
- **M5B2 Final Test Suite:** `343 passed, 2 skipped in 218s` (0 failures, 0 regressions)
- **Repo Status:** Clean

---

## 3. Imported External Artifact Authority
- **Logical Artifact ID:** `qwen_field_bge_large_external_v1`
- **Runtime Location:** `F:\AIC_WORK\artifacts\retrieval_v2\qwen_field_bge_large_external_v1\source`
- **Model Declared:** `BAAI/bge-large-en-v1.5`
- **Embedding Dimension:** 1024
- **Vector Dtype:** `float32`
- **L2 Normalization:** YES
- **FAISS Index Class:** `IndexFlatIP`
- **FAISS Metric:** `METRIC_INNER_PRODUCT`
- **Accepted Field Spaces (7 Fields):**
  - `caption`: 116,298 rows
  - `objects_attributes`: 116,577 rows
  - `spatial_relations`: 116,243 rows
  - `counts`: 116,231 rows
  - `scene`: 116,322 rows
  - `visible_actions`: 96,423 rows (82.58% coverage)
  - `full_text`: 116,649 rows
- **Canonical Frame Mapping:**
  - `keyframe_uid`: `CUSTOM:{video_id}:F{frame_idx}`
  - `timestamp_ms`: `int(round(pts_time * 1000.0))`
  - `unknown CUSTOM`: 0
  - `cross-video mapping`: 0
  - `ambiguous mapping`: 0
  - `duplicate canonical`: 0

---

## 4. Query Encoder Specification
- **Model Checkpoint:** `BAAI/bge-large-en-v1.5`
- **Tokenizer / Architecture:** `AutoTokenizer` / `AutoModel` (Safetensors)
- **Pooling Strategy:** `CLS` token (`outputs[0][:, 0]`)
- **Max Sequence Length:** 512 tokens
- **Instruction Prefix:** None (frozen per M5B0 contract)
- **Output Dtype / Dimension:** `float32` / 1024
- **Normalization:** L2 normalized (`F.normalize(p=2, dim=1)`), norm = 1.0000
- **Process Memory & Concurrency:**
  - Python processes with BGE model: 1
  - Model instances: 1 (shared across all 7 fields)
  - Memory before model load: 129 MB
  - Memory after model load: 1,490 MB
  - Memory after loading representative field index: 2,600 MB
  - Configured device: `auto` / `cuda`
  - Resolved device: `cuda`

---

## 5. Provider Specification (`qwen_bge`)
- **Provider ID:** `qwen_bge`
- **Entity Type:** `FRAME`
- **Frame Space:** `CUSTOM`
- **Score Type:** `faiss_inner_product_l2norm`
- **Score Direction:** `HIGHER_IS_BETTER`
- **Default Field:** `full_text`
- **Field Policy:** Exactly one explicit field per request. No AUTO field, no multi-field fusion, no weighted blending in M5B2.
- **Query Handling:**
  - `original_query` is preserved in full.
  - Optional `embedding_query` allows caller-supplied English or specialized query encoding without hidden automatic translation.
- **Candidate Video Scoping & Adaptive Over-fetch:**
  - `search_k = min(max(top_k * 4, 64), ntotal)`
  - Geometrically expands `search_k *= 4` capped at `ntotal`.
  - Zero leakage across 1-video, 5-video, series set, empty, and invalid scopes.
- **Missing Field Rows:** Treated as non-indexed frames, NOT negative evidence.

---

## 6. Real-Data Functional Probes

### 6.1. Compatibility Probes (14 Probes across 7 Fields)
- 14 / 14 probes returned exact canonical CUSTOM keyframes with valid timestamps and finite inner product scores.
- Zero NaN / Inf values, 0 SQL errors, 0 mapping contradictions.

### 6.2. Stored-Vector Sanity Probes (7 Fields)
- Reconstructed row 0 stored vector from each of the 7 FAISS indexes.
- Self-similarity inner product score: `1.000000` for all 7 fields.

### 6.3. VN / EN Paired Diagnostics (5 Paired Queries)
- Paired raw Vietnamese query vs caller-supplied English `embedding_query`.
- English queries showed tighter semantic alignment consistent with M5B0 findings:
  - `"người phụ nữ mặc áo dài truyền thống"` (0.7149) vs `"woman wearing traditional ao dai dress"` (0.7852)
  - `"xe máy chạy trên đường phố đông đúc"` (0.7212) vs `"motorcycles driving on busy city street"` (0.7934)
  - `"chợ hoa tết náo nhiệt"` (0.7128) vs `"vibrant lunar new year flower market"` (0.7780)
  - `"bác sĩ đang khám bệnh trong bệnh viện"` (0.7741) vs `"doctor examining patient in hospital clinic"` (0.8120)
  - `"cầu thủ đá bóng trên sân cỏ"` (0.6697) vs `"football player kicking ball on soccer field"` (0.7645)

### 6.4. Field Functional Probes (35 Probes: 5 per Field)
- `caption` (5/5 PASS): top-1 scores 0.70 - 0.76
- `objects_attributes` (5/5 PASS): top-1 scores 0.68 - 0.74
- `spatial_relations` (5/5 PASS): top-1 scores 0.65 - 0.72
- `counts` (5/5 PASS): top-1 scores 0.64 - 0.71
- `scene` (5/5 PASS): top-1 scores 0.69 - 0.77
- `visible_actions` (5/5 PASS): top-1 scores 0.68 - 0.86
- `full_text` (5/5 PASS): top-1 scores 0.65 - 0.72

### 6.5. Query Safety Probes
- Punctuation, quotes, slashes, brackets, Unicode diacritics: safely encoded, norm = 1.0000.
- Query > 512 tokens: deterministically truncated to 512 tokens, norm = 1.0000.
- Whitespace-only input: cleanly returns 0 hits without model invocation or crash.

### 6.6. Candidate Scope Isolation Probes
- **1-Video Scope (`L21_V001`):** 100% hits isolated to `L21_V001` (0 leakage).
- **5-Video Scope:** 100% hits within the 5 target videos (0 leakage).
- **Empty Scope (`[]`):** 0 hits returned (clean empty).
- **Invalid Video ID Scope:** 0 hits returned (clean zero).
- **Low-Coverage Field (`visible_actions`):** Terminated cleanly without infinite loop.

### 6.7. Natural Query Smokes (14 AIC-Style Queries)
- 14 / 14 queries executed on `full_text` with valid top candidates and latencies under 350ms (excluding initial model load).

---

## 7. DEV Benchmark Results

### 7.1. Primary Standalone Benchmark (`field="full_text"`)
- **Dataset Directory:** `F:\AIC_WORK\artifacts\evaluation\internal-verified-v1`
- **Manifest SHA256:** `a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`
- **Queries Evaluated:** 15 queries (DEV split)
- **Scored Queries:** 0
- **Unscored Queries:** 15
- **Empty Results:** 0
- **Unique Candidate Videos:** 97
- **Quality Status:** `BLOCKED_BY_GROUND_TRUTH`
- **Latency Profile:**
  - Search p50: 243.99 ms
  - Search p90: 773.67 ms
  - Search p95: 3,888.60 ms
  - Search Max: 11,007.39 ms (includes cold JIT / index page-in)
- **Artifact Output:** `F:\AIC_WORK\artifacts\evaluation\qwen_bge_v1\m5b2_qwen_bge_full_text_1787194386\`

### 7.2. Independent 7-Field Diagnostic Benchmark
| Field | Expected Rows | Empty Results | Unique Candidate Videos | Latency p50 (ms) | Latency p95 (ms) |
|---|---|---|---|---|---|
| `caption` | 116,298 | 0 | 103 | 265.24 | 3,612.50 |
| `objects_attributes` | 116,577 | 0 | 112 | 216.43 | 3,615.55 |
| `spatial_relations` | 116,243 | 0 | 83 | 229.28 | 3,147.77 |
| `counts` | 116,231 | 0 | 43 | 256.88 | 3,583.30 |
| `scene` | 116,322 | 0 | 105 | 1,038.72 | 5,151.43 |
| `visible_actions` | 96,423 | 0 | 91 | 1,353.58 | 4,900.30 |
| `full_text` | 116,649 | 0 | 97 | 1,439.62 | 4,240.67 |

---

## 8. Mutation Audit
- **Corpus Embedding Rows Created:** 0
- **FAISS Indexes Created:** 0
- **FAISS Indexes Modified:** 0
- **Qwen Inference Rows Created:** 0
- **Shared Source / Raw Data Mutations:** 0
- **Canonical / Runtime DB Mutations:** 0
- **External Artifact File Mutations:** 0
- **Qwen BM25 Code Changes:** 0
- **Qwen Structured Code Changes:** 0
- **Frontend Changes:** 0
- **BTC Objects / Taxonomy / Fusion Changes:** 0

---

## 9. Known Limitations
- Model is English-centric (`BAAI/bge-large-en-v1.5`); direct Vietnamese queries produce lower cosine similarity than English translations.
- M5B2 operates on single explicit fields; multi-field combination and routing belong to later milestones.
- Quality evaluation is `BLOCKED_BY_GROUND_TRUTH` pending verified competition ground truth labels.

---

## 10. Rollback Plan
- Revert the feature commit `feat(retrieval): add qwen field-aware bge lane` via standard `git revert`.
