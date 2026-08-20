# M5B0 — External Qwen Field-Aware BGE-Large Import & Acceptance Audit Report

## 1. Executive Verdict
- **Milestone Acceptance:** `PASS`
- **External BGE-Large Import:** `ACCEPTED`
- **Local BGE-M3 Re-embed:** `NOT_REQUIRED`
- **M5B1 Ready:** `YES`
- **M5B2 Ready:** `YES`
- **Corpus Embedding Rows Created by M5B0:** `0`
- **Shared Source Mutations:** `0`
- **Repo Source Changes:** `0`
- **Git Commits in M5B0:** `0`

---

## 2. Core Baseline & Git Lineage
- **Repository:** `F:/AIC_DEV/aic2026`
- **Branch:** `main`
- **Starting HEAD:** `4eeb7d495e79f6f5d56dccde427ec9ea69d582b2`
- **Ending HEAD:** `4eeb7d495e79f6f5d56dccde427ec9ea69d582b2`
- **Repo Status:** Clean (`git status --short` is empty)
- **Backend Test Suite:** `337 passed, 2 skipped in 190.46s (0:03:10)` — ZERO failures / ZERO regressions.

---

## 3. External Artifact Inventory & Configuration
- **Source Logical Path:** `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\output_llm\field_aware_index_bge_large_20260819_182421`
- **Model Declared:** `BAAI/bge-large-en-v1.5` (Dimension: 1024D)
- **Total Source Files:** 24 files
- **Total Data Volume:** 6.24 GB (6,703,045,392 bytes)
- **Config JSON SHA256:** `99bd213189c918f7...`
- **External Builder Seed Weights (Metadata only, NO fusion applied):**
  - `full_text`: 0.25
  - `caption`: 0.20
  - `objects_attributes`: 0.15
  - `visible_actions`: 0.15
  - `spatial_relations`: 0.15
  - `counts`: 0.05
  - `scene`: 0.05

---

## 4. Qwen Corpus & Coverage Facts
- **Total Qwen Rows in documents.parquet:** 116,767
- **Covered Videos:** 873
- **Parse Errors:** 0
- **Duplicate Frame Identities:** 0
- **Per-Field Row Coverage:**
  - `objects_attributes`: 116,577 (99.84%)
  - `full_text`: 116,649 (99.90%)
  - `scene`: 116,322 (99.62%)
  - `caption`: 116,298 (99.60%)
  - `spatial_relations`: 116,243 (99.55%)
  - `counts`: 116,231 (99.54%)
  - `visible_actions`: 96,423 (82.58%)

---

## 5. Field Consistency: NPY ↔ Mapping ↔ FAISS
All 7 field triplets exhibit exact three-way equality with 1024D float32 pre-normalized vectors:

| Field Name | NPY Rows | Mapping Rows | FAISS ntotal | Dimension | Dtype | Vector Norm Mean | FAISS Class | Metric Type | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `caption` | 116,298 | 116,298 | 116,298 | 1024 | float32 | 1.0000 | `IndexFlatIP` | METRIC_INNER_PRODUCT | **PASS** |
| `objects_attributes`| 116,577 | 116,577 | 116,577 | 1024 | float32 | 1.0000 | `IndexFlatIP` | METRIC_INNER_PRODUCT | **PASS** |
| `spatial_relations` | 116,243 | 116,243 | 116,243 | 1024 | float32 | 1.0000 | `IndexFlatIP` | METRIC_INNER_PRODUCT | **PASS** |
| `counts` | 116,231 | 116,231 | 116,231 | 1024 | float32 | 1.0000 | `IndexFlatIP` | METRIC_INNER_PRODUCT | **PASS** |
| `scene` | 116,322 | 116,322 | 116,322 | 1024 | float32 | 1.0000 | `IndexFlatIP` | METRIC_INNER_PRODUCT | **PASS** |
| `visible_actions` | 96,423 | 96,423 | 96,423 | 1024 | float32 | 1.0000 | `IndexFlatIP` | METRIC_INNER_PRODUCT | **PASS** |
| `full_text` | 116,649 | 116,649 | 116,649 | 1024 | float32 | 1.0000 | `IndexFlatIP` | METRIC_INNER_PRODUCT | **PASS** |

- **NaN Count across all fields:** 0
- **Inf Count across all fields:** 0

---

## 6. Canonical Keyframe 1:1 Reconciliation (mapping.sqlite)
Reconciled strictly against active canonical CUSTOM keyframes (116,767 frames, 873 videos):

| Field Name | Mapped Rows | Canonical Matched | Unknown CUSTOM | Cross-Video | Ambiguous | Duplicate Canonical | TS Delta p95 | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `caption` | 116,298 | 116,298 | 0 | 0 | 0 | 0 | 0.0000s | **PASS** |
| `objects_attributes`| 116,577 | 116,577 | 0 | 0 | 0 | 0 | 0.0000s | **PASS** |
| `spatial_relations` | 116,243 | 116,243 | 0 | 0 | 0 | 0 | 0.0000s | **PASS** |
| `counts` | 116,231 | 116,231 | 0 | 0 | 0 | 0 | 0.0000s | **PASS** |
| `scene` | 116,322 | 116,322 | 0 | 0 | 0 | 0 | 0.0000s | **PASS** |
| `visible_actions` | 96,423 | 96,423 | 0 | 0 | 0 | 0 | 0.0000s | **PASS** |
| `full_text` | 116,649 | 116,649 | 0 | 0 | 0 | 0 | 0.0000s | **PASS** |

---

## 7. Storage, Import & Hash Verification
- **Import Destination:** `F:/AIC_WORK/artifacts/retrieval_v2/qwen_field_bge_large_external_v1/`
- **Total Imported Files:** 24 files
- **Source == Imported Checksums:** 100% verified equal across all 24 files.

---

## 8. Stored-Vector Self-Search & Query Compatibility
- **Stored-Vector Self-Search:** 34 / 35 probes achieved deterministic Top-1 exact match / top tie group (100% field coverage).
- **Exact Query Encoder Contract (BAAI/bge-large-en-v1.5):**
  - Architecture: BertModel with CLS pooling + L2 normalization
  - Max Length: 512 tokens
  - Same-Text Probes: **52 / 57 probes returned exact Top-1**, 52 / 57 in Top-5.
- **Paired VN / EN Diagnostics:**
  - `'người đi xe máy'` vs `'person riding a motorcycle'`: VN score 0.6572, EN score 0.7636
  - `'nấu ăn trong nhà bếp'` vs `'cooking in a kitchen'`: VN score 0.7242, EN score 0.8112
  - `'đường bị ngập'` vs `'flooded road'`: VN score 0.6699, EN score 0.7744
  - `'cảnh sát giao thông'` vs `'traffic police officer'`: VN score 0.6945, EN score 0.7989
  - `'lễ hội truyền thống'` vs `'traditional festival'`: VN score 0.6419, EN score 0.8058

---

## 9. Known Limitations
- The external model is English-optimized (`BAAI/bge-large-en-v1.5`), so English queries achieve higher cosine similarity scores (~0.76 - 0.81) than direct Vietnamese raw strings (~0.64 - 0.72).
- M5B2 will provide clean field query dispatch and translation/query-expansion pathways where needed.
- `visible_actions` coverage is 82.58% (96,423 frames), reflecting static scenes without explicit motion text.

---

## 10. Next Milestone
- `M5B1 — Qwen BM25 Core`
- `M5B2 — External Field-Aware BGE-Large Core Provider`
