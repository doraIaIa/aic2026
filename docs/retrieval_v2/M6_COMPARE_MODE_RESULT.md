# M6 — Compare Mode + Lane Diagnostics Acceptance Report

**Milestone:** M6 — Multi-Lane Compare Mode & Candidate Diagnostics  
**Status:** ACCEPTED / CLOSED  
**Date:** 2026-08-20  
**Backend Commit Reference:** `7d2aaec` (`feat(search): add compare mode diagnostics`)  
**Frontend Commit Reference:** `a029409` (`feat(ui): add compare mode`)  
**Quality Status:** `BLOCKED_BY_GROUND_TRUTH` (15 DEV queries, scored = 0, unscored = 15)  

---

## 1. Executive Summary & Architectural Invariant

M6 establishes the operational multi-lane comparison and candidate diagnostic tool for AIC 2026.

### Core Architectural Invariants:
1. **Parallel Independent Execution:** Each retrieval lane runs isolated with its own representation, native indexing, and raw scoring semantics.
2. **Canonical Evidence Identity:** All lane hits share the same canonical `video_id` space and map directly to `EvidenceWindowV1` for exact-frame visual inspection and timeline navigation.
3. **Strictly NO Fusion / NO Reranking / NO Score Normalization:** Compare Mode **MUST NOT** normalize raw scores, cross-rank, weight lanes, vote, or merge results into a single list.
4. **Diagnostic Candidate Diversity:** Overlap matrix computes set-algebra diagnostics (Video Union Count, Intersection Count, Pairwise Overlap, and Jaccard similarity) solely to measure modality complementary coverage.
5. **Deterministic Free-Text Defaults & Manual Explicit Configuration:** Free-text lanes take the natural query directly. Structured lanes (`btc_objects`, `qwen_structured`) require manual operator configuration; if enabled without configuration, they report `SKIPPED_INVALID_CONFIG` without failing the batch.

---

## 2. DEV Benchmark Results (15 DEV Queries, Top-20 per Lane)

Executed via `aic2026.evaluation.compare_benchmark.run_compare_dev_benchmark()` on `F:\AIC_WORK\artifacts\evaluation\internal-verified-v1\query_manifest.jsonl`:

- **Dataset Checksum (SHA256):** `a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`
- **Total Queries Executed:** 15
- **Total Lanes Profiled:** 10 Free-Text Lanes
- **Mean Top-20 Video Union Count:** **92.47 unique videos** per query
- **Error Count Across All Lanes:** **0**

### Per-Lane Benchmark Breakdown:

| Lane ID | Query Mode | Status Counts (15 Queries) | Latency p50 (ms) | Latency p95 (ms) | Mean Top-K Hits | Mean Unique Videos |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `siglip_custom` | Visual (SigLIP2, 116k CUSTOM) | 15 OK, 0 Error | 60.92 ms | 7009.74 ms (cold) | 20.0 | 12.80 |
| `btc_clip` | Visual (OpenCLIP, 177k BTC) | 15 OK, 0 Error | 52.44 ms | 3053.15 ms (cold) | 20.0 | 8.73 |
| `asr_bm25` | Speech Lexical (FTS5 BM25) | 15 OK, 0 Error | 456.77 ms | 1440.62 ms | 20.0 | 15.27 |
| `asr_bge` | Speech Semantic (BGE-M3 Dense) | 15 OK, 0 Error | 497.88 ms | 6413.85 ms (cold) | 20.0 | 17.20 |
| `ocr_bm25` | Text Lexical (FTS5 BM25) | 15 OK, 0 Error | 404.50 ms | 3867.56 ms | 20.0 | 11.00 |
| `ocr_trigram` | Text Typo-Tolerant (3-Gram) | 0 OK, 15 EMPTY, 0 Error | 59.79 ms | 492.95 ms | 0.0 | 0.00 |
| `ocr_bge` | Text Semantic (BGE-M3 Dense) | 15 OK, 0 Error | 554.97 ms | 10517.07 ms (cold) | 20.0 | 14.60 |
| `media_bm25` | Video Metadata (FTS5 BM25) | 15 OK, 0 Error | 25.11 ms | 92.12 ms | 20.0 | 20.00 |
| `qwen_bm25` | Vision-Lang Lexical (FTS5) | 0 OK, 15 EMPTY, 0 Error | 15.96 ms | 777.38 ms | 0.0 | 0.00 |
| `qwen_bge` | Vision-Lang Dense (BGE-Large) | 15 OK, 0 Error | 94.55 ms | 2576.43 ms (cold) | 20.0 | 16.47 |

---

## 3. Structured Lane Functional Probes

Executed via `aic2026.evaluation.compare_benchmark.run_structured_functional_probes()`:

- **Qwen Structured Probes:** 5/5 PASSED (traffic police, red car outdoor, child walking dog, cooking kitchen, fire truck).
- **BTC Objects Probes:** 5/5 PASSED (Person, Car + Motorcycle, Traffic light, Fire truck, Dog).
- **Multi-Modal Combined Probes:** 3/3 PASSED (Free-text + Qwen facets + Object classes in single compare execution).
- **All Probes Result:** `13 / 13 PASSED` (100% functional integrity).

---

## 4. Test & Regression Status

- **Core Repository (`F:/AIC_DEV/aic2026`):**
  - pytest command: `pytest -q tests`
  - Result: **377 passed, 2 skipped** (Zero regressions).
- **Frontend Repository (`F:/aic-video-search-demo`):**
  - vitest command: `npm test -- --run`
  - Result: **13 suites / 59 passed** (Zero regressions).
  - TypeScript typecheck: `npm run check` (PASS, 0 errors).
  - Production build: `npm run build` (PASS, 0 errors).

---

## 5. M6 Status Sign-off

- `M6_STATUS = ACCEPTED`
- `M6_DIAGNOSTICS_READY = YES`
- `NEXT_PHASE = AWAITING_INSTRUCTION`
