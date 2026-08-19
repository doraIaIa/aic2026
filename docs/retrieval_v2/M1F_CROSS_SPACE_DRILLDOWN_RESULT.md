# Milestone M1F — Cross-Space Timeline + Full Data Hub Drilldown Validation Acceptance Report

## 1. Executive Summary & Verification Verdict

**M1F_ACCEPTANCE: PASS**  
**M1_DATA_HUB_CLOSED: YES**  
**M2_RETRIEVAL_LANES_READY: YES**

The entire coordinate space and multimodal evidence universe of the AIC 2026 Data Hub has been validated end-to-end. Cross-space traversal between BTC and CUSTOM frame spaces operates with deterministic tie-breaking and explicit error delta reporting (`delta_ms`). Candidate evidence resolves back to source-video exact-frame authority without mixing namespaces or substituting YouTube `media_info` durations.

- **Corpus Traversal:** All **116,767 CUSTOM $\to$ nearest BTC** and **177,321 BTC $\to$ nearest CUSTOM** associations computed with 0 cross-video leakage.
- **Source Video Timeline Authority:** All **873 source videos** verified via `MediaResolver` ffprobe metadata; **0 out-of-range timestamps** across all 294,088 keyframes.
- **Video & Frame Drilldowns:** **873 / 873 video drilldowns passed**, reproducing 100% of canonical totals.
- **Special Status Preservation:** `ZERO_ASR_SEGMENTS` (14 videos), `OUTLIER` taxonomy (`L30_V096`), `INFERRED` memberships, low-confidence OCR, and raw-without-dense OCR items remain fully visible without false rejection.
- **Full Test Suite:** **245 passed in 10.01s** (100% pass rate).

---

## 2. Git Identity & Audit Provenance

| Parameter | Value |
| :--- | :--- |
| **Repository** | AIC 2026 |
| **Milestone** | M1 — Data Hub & Unified Mapping |
| **Slice** | M1F — Cross-Space Timeline + Full Data Hub Drilldown Validation |
| **Starting HEAD** | `7521c8a0484edae03ab1440b39e806f438134097` |
| **Target Commit** | `feat(data-hub): validate cross-space timeline and drilldown` |
| **Runtime Build ID** | `m1e_20260819_090208_347742` |
| **Validation ID** | `m1f_val_1787132458` |
| **Derived Summary** | `artifacts/retrieval_data_v1/runtime/cross_space_validation_summary.json` |

---

## 3. Full Invariant Relational Counts

All 873 video drilldowns aggregated across `mapping.sqlite` match the frozen canonical counts exactly:

| Dimension / Entity | Expected Count | Drilldown Aggregate | Status |
| :--- | :--- | :--- | :--- |
| **Videos** | 873 | **873** | **PASS** |
| **Media-Info Prior** | 873 | **873** | **PASS** |
| **CUSTOM Keyframes** | 116,767 | **116,767** | **PASS** |
| **Qwen Semantic Frames** | 116,767 | **116,767** | **PASS** |
| **ASR Video Coverage** | 873 | **873** (859 HAS_SEGMENTS, 14 ZERO_ASR) | **PASS** |
| **ASR Segments** | 107,540 | **107,540** | **PASS** |
| **OCR Keyframe Coverage** | 116,767 | **116,767** | **PASS** |
| **OCR Text Items** | 676,925 | **676,925** | **PASS** |
| **OCR BGE-M3 Row Mappings**| 612,813 | **612,813** | **PASS** |
| **BTC Keyframes** | 177,321 | **177,321** | **PASS** |
| **BTC CLIP Raw Rows** | 177,321 | **177,321** | **PASS** |
| **BTC Object Coverage** | 177,321 | **177,321** | **PASS** |
| **External BTC Detections** | 17,732,100 | **17,732,100 (Registered)** | **PASS** |
| **Program Memberships** | 873 | **873** (833 VERIFIED, 39 INFERRED, 1 OUTLIER) | **PASS** |
| **L25 Subject Memberships** | 88 | **88** | **PASS** |

---

## 4. Cross-Space Delta Distributions

Associations are **derived associations** via `(video_id, timestamp_ms)` with deterministic tie-breaking (min `abs_delta_ms`, earliest `timestamp_ms`, stable `keyframe_uid`).

### 4.1 Corpus-Wide Statistics

| Traversal Direction | Count | Min (ms) | p50 (ms) | p90 (ms) | p95 (ms) | p99 (ms) | Max (ms) | Mean (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CUSTOM $\to$ Nearest BTC** | 116,767 | 0 | **520.0** | 1,600.0 | 2,120.0 | 2,700.0 | **6,960** | 765.00 |
| **BTC $\to$ Nearest CUSTOM** | 177,321 | 0 | **560.0** | 6,280.0 | 28,360.0 | 96,989.6 | **377,040** | 5,253.44 |

- **Cross-video association count:** **0** (100% strictly within same `video_id`).
- **Namespace collisions:** **0** (`BTC:` vs `CUSTOM:` strictly disjoint).

### 4.2 Per-Series Delta Summaries (CUSTOM $\to$ BTC)

| Series | Count | p50 (ms) | p95 (ms) | Max (ms) | Mean (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **L21** | 10,309 | 700.0 | 2,534.0 | 5,700 | 1,070.47 |
| **L22** | 12,410 | 700.0 | 2,533.0 | 6,167 | 1,071.67 |
| **L23** | 1,559 | 920.0 | 2,520.0 | 3,480 | 1,126.13 |
| **L24** | 5,745 | 500.0 | 2,080.0 | 5,000 | 708.97 |
| **L25** | 7,725 | 400.0 | 1,640.0 | 5,160 | 572.77 |
| **L26** | 44,980 | 500.0 | 2,000.0 | 5,000 | 678.96 |
| **L27** | 2,088 | 500.0 | 2,080.0 | 4,280 | 722.18 |
| **L28** | 9,996 | 500.0 | 2,080.0 | 6,600 | 733.91 |
| **L29** | 9,451 | 500.0 | 2,000.0 | 5,440 | 711.16 |
| **L30** | 12,504 | 560.0 | 2,240.0 | 6,960 | 845.66 |

### 4.3 Top 5 Largest Sampling Gaps (Diagnostic)

1. `L30_V005`: `CUSTOM:L30_V005:F1637` (65,480ms) $\to$ `BTC:L30_V005:KF000032` (58,520ms), delta = `-6960ms`
2. `L28_V015`: `CUSTOM:L28_V015:F28238` (1,129,520ms) $\to$ `BTC:L28_V015:KF000431` (1,122,920ms), delta = `-6600ms`
3. `L30_V002`: `CUSTOM:L30_V002:F4094` (163,760ms) $\to$ `BTC:L30_V002:KF000087` (157,560ms), delta = `-6200ms`
4. `L22_V029`: `CUSTOM:L22_V029:F31640` (1,054,667ms) $\to$ `BTC:L22_V029:KF000252` (1,048,500ms), delta = `-6167ms`
5. `L22_V009`: `CUSTOM:L22_V009:F26882` (1,075,280ms) $\to$ `BTC:L22_V009:KF000281` (1,069,200ms), delta = `-6080ms`

---

## 5. Source Video Timeline Authority Validation

- **Authority Source:** Source video files probed via `MediaResolver` (ffprobe metadata header).
- **Source Videos Verified:** **873 / 873 (100%)**
- **BTC Timestamp Out-of-Range:** **0 / 177,321**
- **CUSTOM Timestamp Out-of-Range:** **0 / 116,767**
- **Physical Frame Index Violations:** **0**

---

## 6. Stratified Evidence Samples & End-to-End Traces

### 6.1 Rich Frame Drilldown Samples
- **CUSTOM Rich Samples:** 34 frames stratified across series L21–L30, timeline positions, OCR present/absent, and special taxonomy nodes (`L30_V096`, `L30_V029`). All returned valid Qwen semantic structures, OCR items, nearby ASR, and opposite-space BTC associations.
- **BTC Rich Samples:** 34 frames stratified across all series. All returned valid CLIP row references, FAISS status `READY`, object coverage status, nearby ASR, and opposite-space CUSTOM associations.

### 6.2 Exact Source Frame Reachability
- **CUSTOM Candidates:** 20 / 20 resolved to source video with valid duration and fps.
- **BTC Candidates:** 20 / 20 resolved to source video with valid duration and fps.

### 6.3 Modality FTS Traces
- **ASR FTS:** Query `"60 giây"` $\to$ Segment `ASR:L22_V019:L22_V019:000142` $\to$ Video `L22_V019` $\to$ Nearest BTC `BTC:L22_V019:KF000125` $\to$ Nearest CUSTOM `CUSTOM:L22_V019:F12803` $\to$ Source Video `data_extracted/video/L22_V019.mp4`.
- **OCR FTS:** Query `"BỆNH VIỆN"` $\to$ OCR `OCR:CUSTOM:L22_V002:F1664:T0` $\to$ CUSTOM `CUSTOM:L22_V002:F1664` $\to$ Nearest BTC `BTC:L22_V002:KF000016` $\to$ Source Video `data_extracted/video/L22_V002.mp4`.
- **Qwen Caption FTS:** Query `"xe đạp"` $\to$ CUSTOM `CUSTOM:L27_V015:F4606` $\to$ Nearest BTC `BTC:L27_V015:KF000041` $\to$ Source Video `data_extracted/video/L27_V015.mp4`.
- **Media FTS:** Query `"HTV"` $\to$ Video `L24_V017` $\to$ Full Video Drilldown $\to$ Source Video `data_extracted/video/L24_V017.mp4`.

### 6.4 Vector Row Traces
- **SigLIP (10 rows):** Row $\to$ `custom_keyframes` $\to$ Qwen / OCR $\to$ Nearest BTC $\to$ Source Video.
- **BTC CLIP (10 rows):** Row $\to$ `btc_clip_rows` $\to$ `btc_keyframes` $\to$ Object coverage $\to$ Nearest CUSTOM $\to$ Source Video.
- **OCR BGE (10 rows):** `(shard_id, row_in_shard)` $\to$ `ocr_bge_rowmap` $\to$ `ocr_items` $\to$ `custom_keyframes` $\to$ Nearest BTC $\to$ Source Video.

---

## 7. Special Status Preservation Verification

- **`ZERO_ASR_SEGMENTS` (14 videos):** Correctly retained in `asr_video_coverage` and video drilldown without false rejection (`actual_segment_count = 0`, status `ZERO_ASR_SEGMENTS`).
- **`OUTLIER` Taxonomy (`L30_V096`):** Preserved with `status = "OUTLIER"` and `confidence = 0.50` (promotional meta-clip). Visible and traversable.
- **`INFERRED` Taxonomy (`L30_V029` + 38 L24 videos):** Preserved with explicit evidence strings.
- **Low-Confidence OCR:** Preserved with original confidence scores (e.g. `0.45`).
- **Raw OCR Without Dense Embeddings (64,112 items):** Fully indexed and searchable in `ocr_fts` and accessible via `get_ocr_for_keyframe`.

---

## 8. API Lookup Latencies

| Operation | Latency | Description |
| :--- | :--- | :--- |
| `nearest_keyframe (BTC)` | **0.051 ms / lookup** | Indexed predecessor/successor query |
| `nearest_keyframe (CUSTOM)` | **0.048 ms / lookup** | Indexed predecessor/successor query |
| `compare_keyframe_spaces` | **0.089 ms / lookup** | Dual-space neighbor retrieval |
| `get_video_drilldown` | **0.220 ms / lookup** | Multi-table structural aggregation |
| `get_frame_drilldown` | **0.180 ms / lookup** | Rich multimodal frame context |

---

## 9. Final M1F Verification Signature

```text
======================================================================
M1F CROSS-SPACE + DRILLDOWN VALIDATION COMPLETE

Starting HEAD: 7521c8a0484edae03ab1440b39e806f438134097
Final HEAD: 2f03bd71e11eb637d6949eec613b3c1c79535999
Commit: feat(data-hub): validate cross-space timeline and drilldown

Runtime build ID: m1e_20260819_090208_347742

Videos drilldown: 873 passed / 0 failed (100% canonical totals reproduced)
CUSTOM keyframes: 116767
BTC keyframes: 177321

CUSTOM->BTC mappings: 116767
CUSTOM->BTC delta p50: 520.0 ms
CUSTOM->BTC delta p95: 2120.0 ms
CUSTOM->BTC delta p99: 2700.0 ms
CUSTOM->BTC max delta: 6960 ms

BTC->CUSTOM mappings: 177321
BTC->CUSTOM delta p50: 560.0 ms
BTC->CUSTOM delta p95: 28360.0 ms
BTC->CUSTOM delta p99: 96989.6 ms
BTC->CUSTOM max delta: 377040 ms

Source videos resolved: 873 / 873
BTC timestamp out-of-range: 0
CUSTOM timestamp out-of-range: 0
Physical-frame validation violations: 0

CUSTOM rich drilldowns: 34
BTC rich drilldowns: 34
Exact-frame CUSTOM samples: 20
Exact-frame BTC samples: 20

ASR FTS traces: 3 passed
OCR FTS traces: 3 passed
Qwen FTS traces: 3 passed
Media FTS traces: 3 passed

SigLIP row traces: 10 passed
BTC CLIP row traces: 10 passed
OCR BGE row traces: 10 passed

ZERO_ASR status: PRESERVED (14 videos)
Low-confidence OCR status: PRESERVED
Raw-without-dense OCR status: PRESERVED (64112 items)
OUTLIER taxonomy status: PRESERVED (L30_V096)

SQLite integrity_check: ok
SQLite foreign_key_check: clean (0 violations)
Raw/canonical mutations: 0
Inference/embedding/FAISS rebuild: 0

Targeted tests: 9 passed
Full tests: 245 passed in 10.01s

M1F_ACCEPTANCE: PASS
M1_DATA_HUB_CLOSED: YES
M2_RETRIEVAL_LANES_READY: YES
Files changed outside scope: NONE
Known limitations: Source video decoding in M1F is metadata/header verified; pixel decoding for visual search deferred to M2/M3.
Rollback: git reset --hard 7521c8a0484edae03ab1440b39e806f438134097

NEXT:
M2 — Independent Retrieval Lanes
======================================================================
```
