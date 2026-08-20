# M5B1 — Qwen Caption BM25 Core Retrieval Lane Acceptance Report

## 1. Executive Verdict
- **Milestone Acceptance:** `PASS`
- **M5B2 Ready:** `YES`
- **M5 Overall Status:** `OPEN`
- **Quality Evaluation Status:** `BLOCKED_BY_GROUND_TRUTH` (scored = 0, unscored = 15)
- **Corpus Embedding Rows Created by M5B1:** `0`
- **FAISS Indexes Created by M5B1:** `0`
- **Qwen Inference Rows Created by M5B1:** `0`
- **Shared Source / Canonical / M1 Runtime Mutations:** `0`
- **Frontend Changes:** `0`

---

## 2. Core Baseline & Git Lineage
- **Repository:** `F:/AIC_DEV/aic2026`
- **Branch:** `main`
- **Starting HEAD:** `4eeb7d495e79f6f5d56dccde427ec9ea69d582b2`
- **Baseline Test Suite:** `337 passed, 2 skipped`
- **M5B1 Final Test Suite:** `341 passed, 2 skipped in 214s` (0 failures, 0 regressions)
- **Repo Status:** Clean

---

## 3. Current Qwen Corpus Authority
- **CUSTOM Keyframes:** 116,767
- **Canonical Qwen Rows:** 116,767
- **Qwen Semantic Status OK:** 116,767
- **Qwen Missing:** 0
- **Qwen Orphan:** 0
- **Covered Videos:** 873

---

## 4. Active Qwen FTS5 Lexical Corpus
- **Active Table Name:** `qwen_caption_fts`
- **SQLite Virtual Table Definition:**
  ```sql
  CREATE VIRTUAL TABLE qwen_caption_fts USING fts5(
      keyframe_uid UNINDEXED,
      video_id UNINDEXED,
      caption_raw,
      caption_norm,
      caption_accentless,
      tokenize = 'unicode61'
  )
  ```
- **Indexed Fields:** `caption_raw`, `caption_norm`, `caption_accentless`
- **Tokenizer:** `unicode61`
- **Normalizer:** `v1_nfc_accentless`
- **FTS Row Count:** 116,767
- **Orphan FTS Rows:** 0
- **Mapping Failures:** 0

---

## 5. Provider Specification (`qwen_bm25`)
- **Provider ID:** `qwen_bm25`
- **Entity Type:** `FRAME`
- **Frame Space:** `CUSTOM`
- **Score Type:** `sqlite_fts5_bm25`
- **Score Direction:** `LOWER_IS_BETTER`
- **Score Formula:** Raw SQLite FTS5 `bm25(qwen_caption_fts, 0.0, 0.0, 10.0, 10.0, 8.0)`
- **Query Normalization & Fallback Stages:**
  1. *Stage 1 (Conjunctive Safe Literal):* `"token1" "token2" ...`
  2. *Stage 2 (Accentless Literal Fallback):* `(safe_q) OR (caption_accentless: accentless_q)`
- **Candidate Video Scoping:** SQL predicate `WHERE qwen_caption_fts MATCH ? AND fts.video_id IN (...)` (zero leakage on empty or restricted scopes).
- **Result Payload:**
  - `lane`: `qwen_bm25`
  - `keyframe_uid`: `CUSTOM:Lxx_Vxxx:Fxxx`
  - `video_id`: `Lxx_Vxxx`
  - `frame_idx`: canonical integer
  - `timestamp_ms`: canonical integer
  - `caption`: raw caption text
  - `objects`, `attributes`, `scene`, `visible_actions`: read-only Qwen semantic metadata
  - `raw_score`: float BM25 score
  - `score_type`: `sqlite_fts5_bm25`
  - `score_direction`: `LOWER_IS_BETTER`

---

## 6. Functional Probes & Verification

### 6.1. Source-Derived Caption Probes (24 Probes)
Deterministic selection across multiple video series (`L21`, `L22`, `L24`, `L25`, `L26`, `L27`, `L28`, `L29`, `L30`):
- All 24 probes returned valid hits with exact CUSTOM frame identities and valid timestamps.
- Zero SQL errors or execution crashes.

### 6.2. Diacritic & Normalization Probes (6 Probes)
- `'xe máy'` (5 hits) vs `'xe may'` (5 hits) — 100% matched
- `'đường phố'` (5 hits) vs `'duong pho'` (5 hits) — 100% matched
- `'cảnh sát'` (4 hits) vs `'canh sat'` (4 hits) — 100% matched
- `'sông nước'` (5 hits) vs `'song nuoc'` (5 hits) — 100% matched

### 6.3. Query Safety Probes
- Punctuation, quotes, slashes, brackets (`'xe "máy" (chạy nhanh)'`, `'người / xe - đường phố!'`): handled safely without SQL syntax errors.
- Empty query / whitespace: cleanly rejected with `ValueError` / `HTTP 400 Bad Request`.
- SQL/FTS injection strings (`'AND OR NOT MATCH NEAR *'`, `''''''''''''`): cleanly executed returning 0 hits without crash.

### 6.4. Candidate Scope Probes
- **1-Video Scope (`L21_V001`):** 100% hits isolated to `L21_V001` (0 leakage).
- **5-Video Scope:** 100% hits within the 5 target videos (0 leakage).
- **Empty Scope (`[]`):** 0 hits returned (clean empty).
- **Invalid Video ID Scope:** 0 hits returned (clean zero).

### 6.5. Latency Profile
- **FTS Search p50:** 4.25 ms
- **FTS Search p90:** 8.46 ms
- **FTS Search p95:** 14.68 ms
- **FTS Search Max:** 29.02 ms

---

## 7. DEV Benchmark Execution
- **Benchmark Runner:** `aic2026.evaluation.qwen_bm25_benchmark`
- **Dataset Directory:** `F:\AIC_WORK\artifacts\evaluation\internal-verified-v1`
- **Manifest SHA256:** `a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`
- **Labels SHA256:** `ce10ad6312bf5a48bdfefafea1a76a28c864cd51cde83b069759d691ae8d39f4`
- **Queries Evaluated:** 15 queries (DEV split)
- **Scored Queries:** 0
- **Unscored Queries:** 15
- **Quality Status:** `BLOCKED_BY_GROUND_TRUTH`
- **Output Artifacts:** `F:\AIC_WORK\artifacts\evaluation\qwen_bm25_v1\m5b1_qwen_bm25_1787193376\`

---

## 8. Mutation Audit
- **Raw / Shared Source Mutations:** 0
- **Canonical / Runtime DB Mutations:** 0
- **Corpus Embedding Rows Created:** 0
- **FAISS Indexes Created:** 0
- **Qwen Inference Rows:** 0
- **Qwen Structured Code Changes:** 0
- **External BGE-Large Artifact Changes:** 0
- **BTC Object Changes:** 0
- **Taxonomy / Pruning / Fusion Changes:** 0
- **Frontend Changes:** 0

---

## 9. Known Limitations
- Lexical caption search relies strictly on the English/Vietnamese text present in `qwen_caption_fts`.
- Semantic paraphrase, cross-lingual translation, and concept abstraction are delegated to M5B2 (`field_aware_bge_large`).
- Quality evaluation remains `BLOCKED_BY_GROUND_TRUTH` pending verified competition ground truth annotations.

---

## 10. Rollback Plan
- Revert the feature commit `feat(retrieval): add qwen caption bm25 lane` via standard `git revert`.
