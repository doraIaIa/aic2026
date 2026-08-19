# Milestone M5A — Qwen Structured Facet Core Retrieval Lane Report

## 1. Executive Summary & Acceptance Verdict

| Parameter | Value |
| :--- | :--- |
| **M5A_ACCEPTANCE** | **PASS** |
| **M5B_READY** | **YES** |
| **M5_QWEN_STRUCTURED_QUALITY_EVAL_STATUS** | **BLOCKED_BY_GROUND_TRUTH** |

Milestone slice **M5A** is complete. The 116,767 Qwen semantic observations attached to CUSTOM keyframes have been transformed into a standalone, deterministic, explainable STRUCTURED FACET retrieval lane (`qwen_structured`).

---

## 2. Core Repository Git Lineage

- **Starting HEAD:** `5bd8ca55b392f41df3a6fb23a43ab71ad48d45a8`
- **Feature Commit:** `a38771764ebcff7741d4c2b9a7c36d2c4314c46f` (`feat(retrieval): add qwen structured facet lane`)
- **Report / Closure Commit:** `docs(retrieval-v2): record M5A qwen structured acceptance`

---

## 3. Canonical Qwen Corpus & Schema Baseline

| Property | Value | Status |
| :--- | :--- | :--- |
| **CUSTOM Keyframes** | 116,767 | PASS |
| **Qwen Raw Rows** | 116,767 | PASS |
| **Qwen Valid Joined Rows** | 116,767 | PASS |
| **Qwen Semantic Status OK** | 116,767 | PASS |
| **Qwen Missing / Orphan** | 0 / 0 | PASS |
| **Covered Videos** | 873 | PASS |
| **Zero-Facet Valid Rows** | 180 (0.15% supplemented from M1B_R1) | PASS |
| **Rows with >= 1 Facet** | 116,587 (99.85%) | PASS |

---

## 4. Qwen Vocabulary Audit & Namespace Metrics

### 4.1 Namespace Distributions
Total raw observations across all namespaces: **3,902,205**.

| Namespace | Source Field | Total Observations | Unique Raw Phrases | Unique Facets | Frame Coverage | p50 / p90 Len |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `action` | `visible_actions_json` | 274,315 | 86,412 | 73,849 | 96,423 | 24 / 41 chars |
| `attribute` | `attributes_json` | 965,495 | 178,540 | 153,124 | 116,281 | 24 / 45 chars |
| `count` | `counts_json` | 494,999 | 67,812 | 61,207 | 116,231 | 18 / 32 chars |
| `object` | `objects_json` | 1,003,553 | 32,845 | 29,184 | 116,531 | 9 / 18 chars |
| `relation` | `spatial_relations_json`| 763,063 | 320,412 | 313,744 | 116,243 | 42 / 68 chars |
| `scene` | `scene_json` | 400,780 | 42,925 | 39,679 | 116,322 | 19 / 36 chars |

### 4.2 Normalization & Collision Policy
- **Normalizer Version:** `deterministic_text_v1` (Unicode NFC, lowercase, whitespace collapsing, safe punctuation trimming).
- **Alias Policy:** `explicit_alias_v1` (Accentless aliases derived deterministically; no auto-merging of distinct concepts).
- **Safe Format Variants:** 55,274 (purely case, whitespace, or edge punctuation differences).
- **Review Required Collisions:** 0 (no destructive ambiguity).

---

## 5. Derived Postings Index Artifacts

Built at `artifacts/retrieval_v2/qwen_structured_v1/`:
- **`qwen_facets.sqlite`** (Size: 788,221,952 bytes, Checksum SHA256: `6d4afc7677103eaa46b6b5dcada7d911b3697341ea48da681d10ad6fcf141ece`)
- **`qwen_structured_passport.json`**
- **`vocabulary_audit.json`** & **`vocabulary_audit.md`**
- **`DONE.json`**
- **Build Duration:** 242.19s

### Relational & FTS Tables
- `frame_registry`: 116,767 rows (1:1 with CUSTOM keyframe UIDs)
- `facet_dictionary`: 670,787 unique facets
- `facet_aliases`: 55,274 raw formatting alias rows
- `frame_facets`: 3,889,259 postings
- `facet_fts`: FTS5 full-text index for sublinear lexical facet discovery

---

## 6. Provider Contract & Scoring Semantics

- **Provider Name:** `qwen_structured`
- **Entity Type:** `FRAME`
- **Frame Space:** `CUSTOM`
- **Score Type:** `qwen_facet_support`
- **Score Direction:** `HIGHER_IS_BETTER`
- **Scoring Model:** OR / weighted IDF rarity support:
  $$\text{score}(\text{frame}) = \sum_{f \in \text{matched}} w_{\text{ns}}(f) \times \left[\ln\left(\frac{N + 1}{\text{df}(f) + 1}\right) + 1.0\right]$$
- **Tie-Breaking:** Deterministic ascending keyframe UID / frame ordinal.
- **Matched Facet Explanation:** Every hit provides full matched facet breakdown (`facet_id`, `namespace`, `raw_value`, `canonical_value`, `idf`, `contribution`).
- **Visible Actions Limitation:** Strictly documented as keyframe-level observations; no temporal interval persistence claimed.
- **Confidence Claim:** None. Qwen outputs have no calibrated model confidence.

---

## 7. Functional Verification & Controlled Probes

### 7.1 Source-Facet Probes (36 Probes)
Target keyframes chosen from real observations across 6 namespaces.
- `object` (10 probes): 10/10 found at Rank 1 (scores 9.49 – 11.57)
- `attribute` (6 probes): 6/6 found at Rank 1 (scores 10.87 – 11.97)
- `scene` (6 probes): 6/6 found at Rank 1 (scores 9.89 – 11.97)
- `action` (6 probes): 6/6 found at Rank 1 (scores 10.58 – 11.97)
- `relation` (4 probes): 4/4 found at Rank 1 (scores 11.28 – 11.97)
- `count` (4 probes): 4/4 found at Rank 1 (scores 10.36 – 11.97)
- **Result:** **36 / 36 found at Rank 1 (100%)**.

### 7.2 Composed Multi-Facet Probes (12 Probes)
Frames with >= 3 distinct namespaces tested together.
- Example: `CUSTOM:L21_V001:F15` (`relation` + `attribute` + `count`) → Rank 1 (Score: 28.0689, Latency: 7.02ms)
- **Result:** **12 / 12 found at Rank 1 (100%)** with multi-namespace scoring.

### 7.3 Plain-Text Lexical Smokes (13 Queries)
- `motorcycle riding` → 20 hits, Top-1 `L21_V003` (Score 20.9792, Facets: `action/motorcycle riding`, `relation/...`)
- `red car` → 20 hits, Top-1 `L21_V002`
- `city street` → 20 hits, Top-1 `L21_V008`
- `police officer` → 20 hits, Top-1 `L21_V007`
- `kitchen cooking` → 20 hits, Top-1 `L26_V191`
- `xe máy` → 1 hit
- `damaged road water` → 20 hits, Top-1 `L21_V001`
- `hospital hallway` → 20 hits, Top-1 `L21_V001`
- `wildfire night` → 20 hits, Top-1 `L21_V002`
- `swollen river bank` → 20 hits, Top-1 `L21_V001`
- `hoàn_toàn_không_có_trong_từ_điển_12345_xyz` → 0 hits (clean empty state)

---

## 8. DEV Benchmark Evaluation

Evaluated against `internal-verified-v1` (`a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`):
- **Queries Evaluated:** 15
- **Scored / Unscored:** 0 / 15
- **Quality Status:** `BLOCKED_BY_GROUND_TRUTH` (No ground truth annotation exists for Qwen facets in DEV dataset).
- **Latency Distribution:**
  - p50: **169.09 ms**
  - p90: **209.22 ms**
  - p95: **211.98 ms**
  - p99: **213.75 ms**
  - Mean: **170.72 ms**
- **Unique Videos Retrieved across 15 queries:** 79 videos.
- **Run Artifacts:** `artifacts/evaluation/qwen_structured_v1/m5a_run_001/` (`summary.json`, `summary.md`, `per_query.jsonl`, `DONE.json`).

---

## 9. Automated Test Verification

| Suite | Tests | Result |
| :--- | :--- | :--- |
| `tests/test_qwen_structured_index.py` | 4 passed | PASS |
| `tests/test_qwen_structured_lane.py` | 4 passed | PASS |
| `tests/test_qwen_structured_benchmark.py` | 1 passed | PASS |
| `tests/test_search_api_qwen_structured.py` | 3 passed | PASS |
| **Targeted M5A Tests** | **12 passed** | **PASS** |
| **Full Pytest Suite** | **326 passed** (314 baseline + 12 new) | **PASS** |

---

## 10. Invariants & Scope Boundaries Audit

- ✅ Raw/canonical/runtime mutations: **0**
- ✅ Qwen model inference executed: **0**
- ✅ Qwen caption BGE: **None**
- ✅ Qwen caption lexical lane: **None**
- ✅ BTC Object modifications: **0**
- ✅ Taxonomy / Pruning / Fusion changes: **0**
- ✅ Frontend modifications: **0**
- ✅ Zero pip dependency additions

---

## 11. Rollback Procedures

```bash
cd F:/AIC_DEV/aic2026
git revert <m5a-closure-commit-hash>
git revert a38771764ebcff7741d4c2b9a7c36d2c4314c46f
```
