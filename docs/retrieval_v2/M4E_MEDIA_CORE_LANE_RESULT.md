# Milestone M4E — Media-info / Metadata Core Retrieval Lane Acceptance Report

## 1. Executive Summary & Verification Verdict

| Parameter | Value |
| :--- | :--- |
| **M4E_ACCEPTANCE** | **PASS** |
| **M4F_READY** | **YES** |
| **M4_MEDIA_QUALITY_EVAL_STATUS** | **BLOCKED_BY_GROUND_TRUTH** |
| **M4_ASR_SUBSYSTEM_CLOSED** | **YES** |
| **M4_OCR_SUBSYSTEM_CLOSED** | **YES** |
| **M4_LANE_CLOSED** | **NO** (M4F UI lane exposure & operational closure remains) |

The existing 873-row canonical BTC Media-info corpus and `media_fts` FTS5 table in `mapping.sqlite` have been turned into a first-class, standalone VIDEO-level Retrieval V2 lane (`media_bm25`).

---

## 2. Git Identity & Lineage

| Parameter | Value |
| :--- | :--- |
| **Repository** | `F:/AIC_DEV/aic2026` |
| **Milestone** | M4 — ASR / OCR / Metadata Retrieval Lanes |
| **Internal Slice** | M4E — Media-info / Metadata Core Retrieval Lane |
| **Starting HEAD** | `2d53f5198e76d4b742350b6cac51c7de1de89f20` |
| **Feature Commit** | `feat(retrieval): add media info bm25 lane` |
| **Required Logical Ancestors** | `feat(retrieval): add ocr bm25 trigram and bge lanes (M4C)`<br>`docs(retrieval-v2): close OCR UI standalone lanes for M4D` |

---

## 3. Data Hub & FTS5 Integrity Verification

| Metric | Target | Verified Value | Status |
| :--- | :--- | :--- | :--- |
| **Canonical Videos** | 873 | **873** | PASS |
| **Media-info Rows** | 873 | **873** | PASS |
| **Media FTS Rows** | 873 | **873** | PASS |
| **Media Canonical Checksum** | `7b16a48ff935d5a690980e1b02391b15b09c3cd010844eea83ea6725d225999d` | `7b16a48ff935d5a690980e1b02391b15b09c3cd010844eea83ea6725d225999d` | PASS |
| **FTS Orphan Rows** | 0 | **0** | PASS |
| **Media Rows without FTS** | 0 | **0** | PASS |
| **Runtime Build ID** | `m1e_20260819_090208_347742` | `m1e_20260819_090208_347742` | PASS |
| **Author Field Coverage** | 873 / 873 | **873 (100%)** | PASS |
| **Publish Date Coverage** | 873 / 873 | **873 (100%)** | PASS |

---

## 4. Schema, Tokenizer & BM25 Weights

### 4.1 `media_fts` FTS5 Table Schema
- Columns: `video_id`, `title_raw`, `title_norm`, `title_accentless`, `keywords`, `description`
- Tokenizer: `unicode61`
- Normalizer: `v1_nfc_accentless`

### 4.2 BM25 Column Weights (V1 Seed, not calibrated against GT)
- `video_id`: `0` (excluded from relevance scoring)
- `title_raw`: `10`
- `title_norm`: `10`
- `title_accentless`: `8`
- `keywords`: `6`
- `description`: `2`

### 4.3 Structured Relational Filters Supported
- `author_filter`: Supported via `LOWER(media_info.author) LIKE ?` (normalized match)
- `publish_date_from` / `publish_date_to`: Supported via numeric date comparison on `SUBSTR(publish_date, 7, 4) || SUBSTR(publish_date, 4, 2) || SUBSTR(publish_date, 1, 2)` (dd/mm/yyyy format)
- `candidate_video_ids`: Explicit video scope isolation with FTS rank preservation.

---

## 5. VIDEO Evidence Contract & Invariants

- **Entity Type:** `VIDEO`
- **Source Space:** `MEDIA_INFO`
- **Frame Space:** `NONE`
- **Score Kind:** `bm25_lower_is_better`
- **Fabricated Keyframe IDs:** **0**
- **Fabricated Frame Indices:** **0**
- **Fabricated Timestamps:** **0** (sentinel `0.0` used for `start_sec`/`end_sec`/`anchor_sec` without asserting temporal authority)
- **Exact-frame Claim:** **None** (Media-info is a video-level prior, never temporal truth)

---

## 6. Verification & Evaluation Results

### 6.1 Real Query Smokes (>= 10 queries)

| Query | Hits | Top-1 Video | Top-1 Title | Latency (ms) |
| :--- | :--- | :--- | :--- | :--- |
| `HTV` | 5 | `L24_V017` | Ấn tượng với Lân lên Mai Hoa Thung tại Cúp Chợ Lớn | 8.39 |
| `60 Giây` | 5 | `L21_V001` | 60 Giây Sáng - Ngày 01082024 - HTV Tin Tức Mới Nhất | 1.13 |
| `Món Ngon Mỗi Ngày` | 5 | `L26_V347` | CUỐN CHẢ CHAY_MÓN NGON CHO NGÀY RẰM | 5.81 |
| `Bí Quyết Ôn Thi THPT` | 5 | `L25_V002` | BÍ QUYẾT ÔN THI THPT 2024 Môn Lịch sử | 1.35 |
| `Mê Kông` | 5 | `L28_V023` | Tản Mạn Mê Kông, Đến Và Ở Lại TẬP 24 | 0.62 |
| `Cúp Chợ Lớn` | 5 | `L24_V036` | Đoàn Lân Miếu Bảy Bà - An Giang Cúp Chợ Lớn | 0.46 |
| `xe đạp` | 5 | `L30_V001` | Lan tỏa năng lượng tích cực 2024 Chàng trai xe đạp | 0.49 |
| `du lịch` | 5 | `L30_V036` | Lan tỏa năng lượng tích cực 2024 Du lịch miệt vườn | 1.40 |
| `2024` | 5 | `L24_V036` | Đoàn Lân Miếu Bảy Bà - An Giang Cúp Chợ Lớn 2024 | 1.38 |
| `60 Giây Official` | 5 | `L21_V001` | 60 Giây Sáng - Ngày 01082024 | 0.69 |
| `chương trình dạy nấu ăn các món ngon mỗi ngày hướng dẫn chi tiết` | 5 | `L30_V030` | Lan tỏa năng lượng tích cực 2024 Thắp sáng ước mơ | 11.05 |
| `tên_lạ_hoàn_toàn_không_có_trong_corpus_xyz_12345` | 0 | - | (clean empty result) | 0.63 |

### 6.2 Controlled Source-Text Probes (19 deterministic videos)
- 19 probes spanning series L21 to L29 tested with distinctive title phrases.
- Distinctive titles/keywords correctly retrieve source video at rank 1.
- Broader shared series titles (e.g. repeated news boilerplate) return the correct series cluster.

### 6.3 Scope Isolation Probes
- 1-video scope (`L21_V001`): 1 hit returned, 100% scoped.
- 5-video scope: 4 hits returned, 100% strictly within candidate set.
- Invalid scope (`NON_EXISTENT_XYZ`): 0 hits returned, clean empty result.

### 6.4 Latency Profile
- **FTS Query Latency:** p50 = `1.23 ms`, p95 = `2.31 ms`
- **Mapping Latency:** p50 = `0.35 ms`, p95 = `0.83 ms`
- **DEV Benchmark Latency:** p50 = `14.72 ms`, p95 = `20.68 ms`

### 6.5 DEV Benchmark Summary
- **Dataset:** `internal-verified-v1` (`a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`)
- **Total DEV Queries:** 15
- **Scored Queries:** 0
- **Unscored Queries:** 15
- **Empty Results:** 0
- **Candidate Video Diversity:** 156 unique videos retrieved across Top-20
- **Quality Status:** `BLOCKED_BY_GROUND_TRUTH`
- **Artifacts Generated:** `artifacts/evaluation/media_bm25_v1/m4e_run_001/` (`DONE.json`, `per_query.jsonl`, `summary.json`, `summary.md`)

---

## 7. Test Suite Status

| Test Module | Tests | Status | Duration |
| :--- | :--- | :--- | :--- |
| `tests/test_media_bm25_lane.py` | 11 | **PASS** | 0.82s |
| `tests/test_media_benchmark.py` | 1 | **PASS** | 0.25s |
| `tests/test_search_api_media.py` | 4 | **PASS** | 0.08s |
| **Full Test Suite (`pytest -q tests`)** | **314** | **PASS** | **72.40s** |

---

## 8. Prohibited Changes & Invariants Audit

- ✅ Raw/canonical/runtime mutations: **0**
- ✅ Media BGE embedding / FAISS index: **0** (Tier-1 lexical BM25 only)
- ✅ Frontend modifications in M4E: **0** (`F:/aic-video-search-demo` untouched)
- ✅ Qwen / Object / Pruning / Fusion modifications: **0**
- ✅ No new dependencies added (`pyproject.toml` / `requirements.txt` untouched)

---

## 9. Rollback Plan

```bash
git revert <m4e-commit-hash>
rm -rf artifacts/evaluation/media_bm25_v1/
```
