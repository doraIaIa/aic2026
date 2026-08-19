# Milestone M1E — Runtime SQLite, FTS, Minimal Verified Taxonomy & Index Registry Acceptance Report

## 1. Executive Summary & Verification Verdict

**M1E_ACCEPTANCE: PASS**  
**M1F_READY: YES**

The production, fully rebuildable Data Hub runtime bundle has been successfully materialized from the active canonical M1A–M1D artifacts into `retrieval_data_v1` (`F:\AIC_WORK\artifacts\retrieval_data_v1`) without mutating raw Google Drive archives or creating competing database abstractions.

- **SQLite Engine:** SQLite 3.45.1 with native FTS5 virtual table engine.
- **Relational Integrity:** `PRAGMA integrity_check` = `ok`, `PRAGMA foreign_key_check` = `0 violations`.
- **Relational Size:** `mapping.sqlite` = 1,096,323,072 bytes (1.09 GB), single standalone clean database without uncommitted journal/WAL sidecars.
- **Build Duration:** 110.15s for full streaming ingestion, indexing, and validation.
- **Full Test Suite:** 236 passed in 7.02s (100% pass rate).

---

## 2. Git Identity & Audit Provenance

| Parameter | Value |
| :--- | :--- |
| **Repository** | AIC 2026 |
| **Milestone** | M1 — Data Hub & Unified Mapping |
| **Slice** | M1E — Runtime SQLite + FTS + Minimal Verified Taxonomy + Index Registry |
| **Starting HEAD** | `aa6ba4121fec4b7d797ef09b4b2c6e3a096235db` |
| **Target Commit** | `feat(data-hub): build runtime sqlite fts and index registry` |
| **Runtime Build ID** | `m1e_20260819_090208_347742` |
| **Runtime Logical Root** | `artifacts/retrieval_data_v1` |

---

## 3. Relational Table & FTS5 Statistics

### 3.1 Relational Entity Counts

| Table | Entity Space | Description | Row Count |
| :--- | :--- | :--- | :--- |
| `videos` | `VIDEO` | Canonical video universe (M1A) | **873** |
| `media_info` | `VIDEO` | YouTube video metadata priors (M1D) | **873** |
| `custom_keyframes` | `CUSTOM_KEYFRAME` | Custom extracted keyframes (M1B) | **116,767** |
| `qwen_frames` | `CUSTOM_KEYFRAME` | Qwen rich multimodal semantic annotations (M1B) | **116,767** |
| `asr_video_coverage` | `VIDEO` | ASR video-level coverage status (M1C) | **873** |
| `canonical_asr_segments` | `ASR_SEGMENT` | Whisper Medium Vietnamese ASR segments (M1C) | **107,540** |
| `ocr_keyframes` | `CUSTOM_KEYFRAME` | OCR keyframe coverage status (M1C) | **116,767** |
| `ocr_items` | `OCR_ITEM` | Canonical raw OCR text detections (M1C) | **676,925** |
| `ocr_bge_rowmap` | `OCR_ITEM` | 1:1 row mappings to 10 BGE-M3 vector shards (M1C) | **612,813** |
| `btc_keyframes` | `BTC_KEYFRAME` | BTC map keyframes (M1D) | **177,321** |
| `btc_clip_rows` | `BTC_KEYFRAME` | BTC raw CLIP ViT-B/32 1:1 row mappings (M1D) | **177,321** |
| `btc_object_coverage` | `BTC_KEYFRAME` | BTC keyframe object coverage status (M1D) | **177,321** |
| `taxonomy_nodes` | `TAXONOMY` | Flat taxonomy graph nodes (Program V1 + L25 Subjects) | **18** |
| `video_memberships` | `TAXONOMY` | Video branch memberships | **961** (873 Program + 88 Subject) |
| `artifacts` | `RUNTIME` | Registered canonical file artifacts | **12** |
| `vector_indexes` | `RUNTIME` | Registered vector embedding matrices / indices | **4** |

### 3.2 Modality-Separated FTS5 Virtual Tables

| Virtual Table | Indexed Columns | Tokenizer / Normalizer | Row Count |
| :--- | :--- | :--- | :--- |
| `asr_fts` | `text_raw`, `text_norm`, `text_accentless` | `unicode61` + `v1_nfc_accentless` | **107,540** |
| `ocr_fts` | `text_raw`, `text_norm`, `text_accentless` | `unicode61` + `v1_nfc_accentless` | **676,925** |
| `qwen_caption_fts` | `caption_raw`, `caption_norm`, `caption_accentless` | `unicode61` + `v1_nfc_accentless` | **116,767** |
| `media_fts` | `title_raw`, `title_norm`, `title_accentless`, `keywords`, `description` | `unicode61` + `v1_nfc_accentless` | **873** |

---

## 4. Program V1 & L25 Subject Taxonomy Audit

### 4.1 Program V1 Distribution & Status

| Program Branch ID | Series | Total Videos | VERIFIED | INFERRED | OUTLIER | Evidence / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `program/news` | L21, L22 | 60 | 60 | 0 | 0 | 60 Giây multi-topic news confirmed by ASR |
| `program/sports/cycling` | L23 | 25 | 25 | 0 | 0 | HTV Sports cycling broadcast confirmed by ASR |
| `program/cultural-performance/lion-dragon-dance` | L24 | 43 | 5 | 38 | 0 | 5 direct ASR verified; 38 inferred via series prior |
| `program/education/exam-prep` | L25 | 88 | 88 | 0 | 0 | Bí Quyết Ôn Thi THPT confirmed by lecture ASR |
| `program/cooking/demonstration` | L26 | 498 | 498 | 0 | 0 | Món Ngon Mỗi Ngày cooking confirmed by ASR |
| `program/travel-experience` | L27 | 16 | 16 | 0 | 0 | Travel & local food experience confirmed by ASR |
| `program/documentary/mekong-history-geography` | L28 | 24 | 24 | 0 | 0 | Ký sự Mê Kông History & Geography confirmed by ASR |
| `program/documentary/mekong-people-culture-environment` | L29 | 23 | 23 | 0 | 0 | Ký sự Mê Kông People & Culture confirmed by ASR |
| `program/positive-community-local-life-feature` | L30 | 96 | 94 | 1 | 1 | 94 verified; L30_V029 inferred (zero-ASR); L30_V096 outlier |
| **TOTAL PROGRAM V1** | **All 10** | **873** | **833** | **39** | **1** | **Exactly 1 primary Program leaf per video** |

### 4.2 L25 Deep Subject Distribution

All 88 L25 lecture videos are mapped 100% deterministically to 9 subject nodes without semantic guessing:
- `subject/education/literature`: 10 videos
- `subject/education/history`: 10 videos
- `subject/education/biology`: 10 videos
- `subject/education/chemistry`: 10 videos
- `subject/education/physics`: 10 videos
- `subject/education/english`: 10 videos
- `subject/education/geography`: 10 videos
- `subject/education/mathematics`: 10 videos
- `subject/education/economics-law`: 8 videos
- **Total L25 Subject Memberships:** **88 / 88 (100%)**

---

## 5. Vector Artifact & Index Registry

| Index ID | Artifact Type | Entity / Frame Space | Model ID | Dimension | Dtype | Row Count | Mapped Rows | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `btc_clip_raw_features_v1` | `RAW_EMBEDDING_MATRIX` | `KEYFRAME` / `BTC` | `openai/clip-vit-base-patch32` | 512 | `float16` | 177,321 | 177,321 | `READY` |
| `clip-faiss-btc-v1` | `FAISS_INDEX` | `KEYFRAME` / `BTC` | `openai/clip-vit-base-patch32` | 512 | `float32` | 177,321 | 177,321 | `READY` |
| `ocr_bge_m3_sharded_v1` | `SHARDED_EMBEDDINGS` | `OCR_ITEM` / `CUSTOM` | `BAAI/bge-m3` | 1024 | `float32` | 612,813 | 612,813 | `EMBEDDINGS_READY_INDEX_NOT_BUILT` |
| `custom_siglip2_raw_features_v1` | `RAW_EMBEDDING_MATRIX` | `KEYFRAME` / `CUSTOM` | `google/siglip2-base-patch16-224` | 768 | `float32` | 116,767 | 116,767 | `EMBEDDINGS_READY_INDEX_NOT_BUILT` |

- **SigLIP2 Provenance:** Verified across all 873 `.npy` arrays in `output/embeddings/` (116,767 total keyframe rows, 768-D float32, unit L2 norm ~1.000000). FAISS index is not built in M1E and is accurately recorded as `EMBEDDINGS_READY_INDEX_NOT_BUILT`.
- **BTC Objects External Corpus:** 17,732,100 detections registered in `artifacts` with SHA-256 `78f087b931d94e2efd0c69c8e6dd4072abdb23ccf55c9b3ea253aea85aeaf24c` and status `READY_EXTERNAL`. Relational imported detection count = 0 (only 177,321 keyframe coverage records imported into SQLite).

---

## 6. Smoke Mapping Traces & API Lookup Timings

### 6.1 FTS5 Smoke Mapping Traces
- **ASR FTS:** Query `"60 giây"` $\to$ `ASR:L22_V019:L22_V019:000142` (Time: 426780ms–428780ms, Video: `L22_V019`).
- **ASR FTS:** Query `"áo vàng"` $\to$ `ASR:L23_V006:L23_V006:000058` (Time: 175250ms–177250ms, Video: `L23_V006`).
- **OCR FTS:** Query `"BỆNH VIỆN"` $\to$ `OCR:CUSTOM:L22_V002:F1664:T0` (Keyframe: `CUSTOM:L22_V002:F1664`, Video: `L22_V002`).
- **OCR FTS:** Query `"THÀNH PHỐ"` $\to$ `OCR:CUSTOM:L21_V029:F4623:T3` (Keyframe: `CUSTOM:L21_V029:F4623`, Video: `L21_V029`).
- **Qwen Caption FTS:** Query `"xe đạp"` $\to$ Keyframe `CUSTOM:L27_V015:F4606` (Video: `L27_V015`, Caption: "Trải nghiệm đạp xe quanh làng quê...").
- **Media FTS:** Query `"HTV"` $\to$ Video `L24_V017` (Title: "Ấn tượng với Lân lên Mai Hoa Thung tại Cúp Chợ Lớn - HTV 2024").

### 6.2 Sub-Millisecond API Lookup Timings

| Method | Description | Latency |
| :--- | :--- | :--- |
| `get_video` | Canonical video record by ID | **0.075 ms / lookup** |
| `get_keyframe (BTC)` | BTC keyframe by UID | **0.081 ms / lookup** |
| `get_keyframe (CUSTOM)` | CUSTOM keyframe by UID | **0.068 ms / lookup** |
| `get_asr_near` | Temporal speech segments in window | **0.156 ms / lookup** |
| `get_ocr_for_keyframe` | Raw OCR text items on keyframe | **0.056 ms / lookup** |
| `get_memberships` | Program and Subject memberships | **0.092 ms / lookup** |
| `get_vector_index` | Vector artifact registry descriptor | **0.090 ms / lookup** |

---

## 7. M1E Final Verification Signature

```text
M1E RUNTIME DATA HUB COMPLETE

Starting HEAD: aa6ba4121fec4b7d797ef09b4b2c6e3a096235db
Final HEAD: 6dc39500ee5001c6c3bf76aac4120936583be939
Commit: feat(data-hub): build runtime sqlite fts and index registry

Runtime build ID: m1e_20260819_090208_347742
SQLite version: 3.45.1
FTS5: AVAILABLE
mapping.sqlite size: 1,096,323,072 bytes (1.09 GB)
Build duration: 110.15s

Videos: 873
CUSTOM keyframes: 116767
Qwen frames: 116767
ASR segments: 107540
OCR raw items: 676925
OCR BGE rows: 612813
BTC keyframes: 177321
BTC CLIP rows: 177321
BTC object coverage: 177321
External BTC detections: 17732100
Media-info: 873

Program memberships: 873
Program VERIFIED: 833
Program INFERRED: 39
Program OUTLIER: 1
L25 subjects: 88

ASR FTS rows: 107540
OCR FTS rows: 676925
Qwen FTS rows: 116767
Media FTS rows: 873

SigLIP rows: 116767
SigLIP dim: 768
SigLIP mapped: 116767
SigLIP index status: EMBEDDINGS_READY_INDEX_NOT_BUILT

BTC CLIP rows: 177321
BTC FAISS rows: 177321
BTC mapped: 177321

OCR BGE rows: 612813
OCR BGE mapped: 612813
OCR dense index status: EMBEDDINGS_READY_INDEX_NOT_BUILT

SQLite integrity_check: ok
SQLite foreign_key_check: clean (0 violations)
Raw/canonical mutations: 0
Inference/embedding/FAISS rebuild: 0

Targeted tests: 8 passed
Full tests: 236 passed in 7.02s

M1E_ACCEPTANCE: PASS
M1F_READY: YES
Files changed outside scope: NONE
Known limitations: OCR and SigLIP2 FAISS indexes not built in M1E (status accurately recorded as EMBEDDINGS_READY_INDEX_NOT_BUILT); hard query routing/pruning deferred to M2.
Rollback: git reset --hard aa6ba4121fec4b7d797ef09b4b2c6e3a096235db

NEXT:
M1F — Cross-Space Timeline + Full Data Hub Drilldown Validation
```
