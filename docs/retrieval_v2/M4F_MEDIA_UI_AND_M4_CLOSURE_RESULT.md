# Milestone M4F — Media-info Standalone UI + M4 Operational Closure Report

## 1. Executive Summary & Operational Verdict

| Parameter | Value |
| :--- | :--- |
| **M4F_ACCEPTANCE** | **PASS** |
| **MEDIA_IMPLEMENTATION_ACCEPTANCE** | **PASS** |
| **MEDIA_OPERATIONAL_ACCEPTANCE** | **PASS** |
| **MEDIA_QUALITY_EVAL_STATUS** | **BLOCKED_BY_GROUND_TRUTH** |
| **M4_MEDIA_SUBSYSTEM_CLOSED** | **YES** |
| **M4_IMPLEMENTATION_ACCEPTANCE** | **PASS** |
| **M4_OPERATIONAL_ACCEPTANCE** | **PASS** |
| **M4_QUALITY_EVAL_STATUS** | **BLOCKED_BY_GROUND_TRUTH** |
| **M4_LANE_CLOSED** | **YES** |
| **M5_READY** | **YES** |

Milestone M4 (ASR, OCR, and Media-info / Metadata Retrieval Lanes) is now **OPERATIONALLY CLOSED**. All 6 standalone single lanes (ASR BM25, ASR BGE, OCR BM25, OCR Trigram, OCR BGE, Media BM25) are fully implemented in the core backend, verified against Data Hub runtime databases, and integrated into the React Retrieval Workspace UI with distinct evidence semantics (`SEGMENT`, `OCR_ITEM`, `VIDEO`).

---

## 2. Two-Repository Git Lineage

### 2.1 Core Repository (`F:/AIC_DEV/aic2026`)
- **Starting HEAD:** `6c52d2a32c6954d1caa067747161ac244a5b729f`
- **Commit:** `docs(retrieval-v2): close media UI lane and M4`
- **Full Clean Status:** Verified (`git status --short` clean)

### 2.2 Frontend Repository (`F:/aic-video-search-demo`)
- **Starting HEAD:** `a8eafa601d6e3687b0ab5e92a05701334e9c8b83`
- **Feature Commit:** `e015a978b0fdbc47cce59efc1493080c54e4986d` (`feat(retrieval-v2): add media info single-lane UI`)
- **Final HEAD:** `e015a978b0fdbc47cce59efc1493080c54e4986d`

---

## 3. Corpus & Schema References (M4E / M4F)

| Property | Value | Status |
| :--- | :--- | :--- |
| **Canonical Videos** | 873 | PASS |
| **Media-info Rows** | 873 | PASS |
| **Media FTS Rows** | 873 | PASS |
| **Media Checksum** | `7b16a48ff935d5a690980e1b02391b15b09c3cd010844eea83ea6725d225999d` | PASS |
| **Indexed Fields** | `title_raw`, `title_norm`, `title_accentless`, `keywords`, `description` | PASS |
| **Tokenizer / Normalizer** | `unicode61` / `v1_nfc_accentless` | PASS |
| **BM25 Column Weights** | `title_raw: 10`, `title_norm: 10`, `title_accentless: 8`, `keywords: 6`, `description: 2` (video_id: 0) | PASS |

---

## 4. Media Single Lane UI Integration

### 4.1 Routes & Network Isolation
- **Health Endpoint:** `GET /api/v1/lanes/media-bm25/health`
- **Search Endpoint:** `POST /api/v1/lanes/media-bm25/search`
- **Isolation Invariant:** Selecting "Media Info" dispatches strictly to `media_bm25`. No ASR, OCR, or visual endpoints are invoked. No fusion or fallback request occurs.

### 4.2 Query & Scope Handling
- **Query Preservation:** Natural user queries (Vietnamese, accentless, acronyms) are passed 100% untouched to the backend. No client-side normalization or rewriting.
- **Candidate Scope:** Explicit video scoping (`candidate_video_ids`) isolates candidates strictly to the user-selected subset without leakage.

### 4.3 Result Card & Evidence Invariants
- **Evidence Entity:** `VIDEO` (distinguished from `FRAME`, `SEGMENT`, `OCR_ITEM`).
- **Frame Space:** `NONE` (no fake `CUSTOM` or `BTC` frame badges).
- **Metadata Display:** Video ID, Title, Author, Publish Date, Keywords snippet, Description snippet.
- **Score Semantics:** Labeled as `BM25 raw score` with `Lower is better` note. Never labeled as `Similarity` or `Confidence`.
- **Backend Ordering:** Direct ascending rank preserved without client reordering.

### 4.4 Sentinel Time & Inspector Semantics
- **Temporal Authority:** `NONE`.
- **Sentinel Handling:** Backend sentinels (`0.0`s) are not interpreted as retrieval timestamps.
- **Inspector Behavior:** Displays `MEDIA INFO (VIDEO PRIOR)`. Metadata mapping grid displays `— (Video Prior)` for frame index, keyframe ID, and representative time.
- **Source Video Playback:** Player is initialized for manual operator scrub without attributing retrieval relevance to time `00:00`.
- **Candidate Builder:** Video-level media result alone does not auto-populate a KIS candidate frame. Operator must manually inspect and navigate before creating a frame candidate.

---

## 5. Smokes & Controlled Probes (M4E Process Deviation Closure)

### 5.1 Real UI Smoke Queries
1. `HTV` → 5 hits, Top-1 `L24_V017`
2. `60 Giây` → 5 hits, Top-1 `L21_V001`
3. `Món Ngon Mỗi Ngày` → 5 hits, Top-1 `L26_V347`
4. `Bí Quyết Ôn Thi THPT` → 5 hits, Top-1 `L25_V002`
5. `Mê Kông` → 5 hits, Top-1 `L28_V023`
6. `Cúp Chợ Lớn` → 5 hits, Top-1 `L24_V036`
7. `tên_lạ_hoàn_toàn_không_có_trong_corpus_xyz_12345` → 0 hits (clean empty state)

### 5.2 Cumulative Controlled Source-Text Probes
- M4E Report Baseline: 19 probes spanning L21–L29
- M4F Additional Probes:
  - `L30_V050`: `"thi Lan tỏa năng lượng"` → Rank 4 (10 hits)
  - `L30_V001`: `"Chàng trai bỏ phố về quê đạp xe"` → Rank 1 (5 hits)
- **Cumulative Controlled Probes:** **21** (`>= 20` requirement satisfied, process deviation formally closed).

---

## 6. Full M4 Subsystem Inventory & Evidence Hierarchy

| Subsystem | Lane ID | Modality / Tech | Evidence Entity | Frame Space | Score Semantics | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Visual (M2/M3)** | `siglip_custom` | SigLIP2 + FAISS IndexFlatIP | `FRAME` | `CUSTOM` | Cosine (Higher is better) | CLOSED |
| **Visual (M2/M3)** | `btc_clip` | OpenCLIP + FAISS IndexIDMap2 | `FRAME` | `BTC` | Cosine (Higher is better) | CLOSED |
| **ASR (M4A/M4B)** | `asr_bm25` | SQLite FTS5 lexical | `SEGMENT` | `NONE` | BM25 (Lower is better) | CLOSED |
| **ASR (M4A/M4B)** | `asr_bge` | BAAI/bge-m3 + FAISS IndexFlatIP | `SEGMENT` | `NONE` | Cosine (Higher is better) | CLOSED |
| **OCR (M4C/M4D)** | `ocr_bm25` | SQLite FTS5 lexical | `OCR_ITEM` | `CUSTOM` | BM25 (Lower is better) | CLOSED |
| **OCR (M4C/M4D)** | `ocr_trigram` | SQLite FTS5 character 3-gram | `OCR_ITEM` | `CUSTOM` | BM25 (Lower is better) | CLOSED |
| **OCR (M4C/M4D)** | `ocr_bge` | BAAI/bge-m3 + FAISS IndexFlatIP | `OCR_ITEM` | `CUSTOM` | Cosine (Higher is better) | CLOSED |
| **Metadata (M4E/M4F)**| `media_bm25` | SQLite FTS5 lexical | `VIDEO` | `NONE` | BM25 (Lower is better) | **CLOSED** |

---

## 7. Quality Evaluation & DEV Ground Truth Status

- **DEV Dataset:** `internal-verified-v1` (`a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`)
- **Scored Queries across Text/Media Lanes:** `0 / 15` (DEV benchmark queries lack ground truth annotation for ASR/OCR/Media modalities).
- **M4 Quality Evaluation Verdict:** `BLOCKED_BY_GROUND_TRUTH`. Operational closure is based on strict contract compliance, zero fabricated entities, fail-closed validation, and functional index probes.

---

## 8. Test Verification Summary

| Test Category | Suite | Passed | Failed | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Tests** | Vitest (`client/src/retrieval/**/*.test.ts*`) | **42** | 0 | PASS |
| **Frontend Typecheck** | `tsc --noEmit` | **0 errors** | 0 | PASS |
| **Frontend Build** | `vite build && esbuild` | **Success** | 0 | PASS |
| **Backend Targeted** | `test_media_bm25_lane.py`, `test_media_benchmark.py`, `test_search_api_media.py` | **16** | 0 | PASS |
| **Backend Full** | `pytest -q tests` | **314** | 0 | PASS |

---

## 9. Prohibited Changes & Invariants Audit

- ✅ Raw/canonical/runtime mutations: **0**
- ✅ Media BGE embedding / FAISS index: **0**
- ✅ M5 / Qwen / Object / Pruning / Fusion modifications: **0**
- ✅ Zero npm / pip dependency changes

---

## 10. Rollback Procedures

### Frontend Rollback
```bash
cd F:/aic-video-search-demo
git revert e015a978b0fdbc47cce59efc1493080c54e4986d
```

### Core Repository Rollback
```bash
cd F:/AIC_DEV/aic2026
git revert <core-closure-commit-hash>
```
