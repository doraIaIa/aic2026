# M5D — BTC Objects Core Retrieval Acceptance Report

**Milestone:** M5 — Qwen + BTC Objects  
**Slice:** M5D — BTC Objects Core Retrieval  
**Date:** 2026-08-20  
**Status:** **ACCEPTANCE PASS** (100% Deterministic, Fail-Closed Validated)  
**Artifact Root:** `F:/AIC_WORK/artifacts/retrieval_v2/btc_objects_v1`  
**Benchmark Artifact:** `F:/AIC_WORK/artifacts/evaluation/btc_objects_v1/m5d_btc_obj_bench_1787199432/summary.json`  

---

## 1. Executive Summary & Coordinate Space Invariant

Milestone 5 Slice M5D delivers the **BTC Objects Standalone Retrieval Lane** (`btc_objects`), turning the pre-existing 17.7M OpenImages object detections into a first-class, deterministic, explainable structured object retrieval engine over the canonical BTC frame space.

### Core Coordinate Space & Provider Contracts

| Dimension | BTC Objects Retrieval Lane Contract | Authority / Status |
| :--- | :--- | :--- |
| **Provider ID** | `btc_objects` | Frozen |
| **Entity Type** | `FRAME` | Canonical Frame Evidence |
| **Frame Space** | `BTC` | 177,321 BTC Keyframes |
| **Score Type** | `btc_object_support` | Deterministic Max Raw Detector Score |
| **Score Direction** | `HIGHER_IS_BETTER` | Direct float comparison |
| **Class Taxonomy** | 584 OpenImages Classes | 100% 1:1 Normalization (0 Collisions) |
| **Match Modes** | `ALL` (MIN score support) / `ANY` (MAX score support) | Deterministic Boolean/Support logic |
| **Detections Covered** | **17,732,100** detections across 873 videos | 100 detections per frame |
| **Query Hot Path** | SQLite Indexed Search ($O(\log N)$ on `class_id`, `max_score`) | **NO raw 17.7M corpus scan** |
| **Quality Evaluation** | `M5_BTC_OBJECTS_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH` | No fake GT or fabricated recall |

> [!IMPORTANT]
> **Coordinate Space Decoupling:** BTC Objects evidence strictly operates in the `BTC` frame coordinate space (`BTC:{video_id}:KF{n:06d}`). It is never conflated with or mapped by ordinal to `CUSTOM` keyframes.
>
> **No Hidden Intelligence:** No LLM query decomposition, no automatic translation, no fuzzy synonym expansion, and no semantic embedding-based class mapping are used. The operator or API supplies exact detector class labels.

---

## 2. Source Authority & Universe Reconciliation

The authoritative BTC object detection corpus was verified against the accepted M1D passport and source archives:

* **Source Archive:** `F:/AIC_WORK/tmp/objects-aic25-b1.zip` (SHA-256: `982683c5421fa06a087dba25c019d69390ac83cb95e05532bfa2ad29fa290cec`)
* **Authoritative Canonical Frame Count:** **177,321** BTC keyframes across **873** canonical videos.
* **Authoritative Detections Count:** **17,732,100** OpenImages detections.
* **Detections per Frame:** Exactly 100 per frame ($177,321 \times 100 = 17,732,100$).
* **Mapping Integrity:**
  - `known mappings`: 177,321
  - `unknown`: 0
  - `ambiguous`: 0
  - `cross-video`: 0
  - `duplicate frame map`: 0
* **Raw Schema Fields:**
  - `detection_scores`: float detection scores in $[0.0, 1.0]$ (no NaN, no Inf).
  - `detection_class_names`: OpenImages MIDs (e.g. `/m/01g317`).
  - `detection_class_entities`: OpenImages entity display labels (e.g. `Person`, `Motorcycle`).
  - `detection_class_labels`: OpenImages integer labels (e.g. `84`, `150`).
  - `detection_boxes`: Normalized bounding boxes `[ymin, xmin, ymax, xmax]` in $[0.0, 1.0]$.

---

## 3. Compact Derived Index (`btc_objects_v1`)

To prevent scanning 17.7M raw JSON records at query time, a compact, aggregated SQLite postings index was materialized:

* **Index Action:** `BUILT_NEW`
* **Build ID:** `btc_obj_b20260820_041005`
* **Build Runtime:** 272.77s
* **Indexed Classes:** 584 classes
* **Aggregated Postings Rows:** 5,760,759 rows
* **Database File:** `btc_objects_postings.sqlite` (2.33 GB, SHA-256: `c9205cf70d54c985b57cfeaa54a2b0eab3e5a5008735ba5a5b9fcb7752b53a15`)
* **Classes File:** `classes.json` (155 KB, SHA-256: `86571a39560751731fe5498bdbcaf4e35e723eab57f21c348ebbd5a7d1446f7e`)
* **Passport File:** `btc_objects_passport.json`
* **Done Marker:** `DONE.json` (`status: "COMPLETED"`)

### Index Schema & Query Optimizations:
1. `class_dictionary`: 584 rows storing MID, entity name, label, normalized string, frame count, detection count, and score boundaries.
2. `object_postings`: 5,760,759 rows storing `(class_id, keyframe_uid, video_id, local_keyframe_no, frame_idx, timestamp_ms, max_score, detection_count, top_bbox_json, top_detections_json)`.
3. B-Tree Indexes:
   - `idx_postings_class_score` on `object_postings(class_id, max_score DESC)`
   - `idx_postings_class_video` on `object_postings(class_id, video_id, max_score DESC)`
   - `idx_postings_kf` on `object_postings(keyframe_uid)`
   - `idx_class_dict_norm` on `class_dictionary(class_norm)`

---

## 4. Class Vocabulary & Deterministic Normalization

* **Normalization Policy:** Unicode NFKC $\rightarrow$ strip whitespace $\rightarrow$ lowercase $\rightarrow$ collapse whitespace $\rightarrow$ Unicode NFC.
* **Collision Audit:** **0** collisions across all 584 classes. Every normalized entity name maps 1:1 to a unique OpenImages MID.
* **Top 10 Most Frequent Classes:**
  1. `Person` (`/m/01g317`): 142,987 frames, 1,020,775 detections
  2. `Clothing` (`/m/09j2d`): 139,320 frames, 965,712 detections
  3. `Man` (`/m/04yx4`): 115,596 frames, 478,539 detections
  4. `Human face` (`/m/0dzct`): 109,522 frames, 312,218 detections
  5. `Plant` (`/m/05s2s`): 106,560 frames, 634,766 detections
  6. `Tree` (`/m/07j7r`): 97,978 frames, 497,118 detections
  7. `Building` (`/m/0cgh4y`): 89,848 frames, 317,314 detections
  8. `Skyscraper` (`/m/079cl`): 88,414 frames, 303,803 detections
  9. `Land vehicle` (`/m/01prls`): 86,756 frames, 335,016 detections
  10. `Vehicle` (`/m/07yv9`): 85,917 frames, 329,664 detections

---

## 5. Structured Search Request & Ranking Contract

* **Request Contract:**
  ```json
  {
    "classes": ["person", "motorcycle"],
    "match_mode": "ALL",
    "min_detector_score": 0.25,
    "top_k": 20,
    "candidate_video_ids": ["L21_V001", "L23_V012"]
  }
  ```
* **Match Modes:**
  - `ALL`: Eligible frames must have detections for all requested classes $\ge$ `min_detector_score`.  
    $$\text{object\_support\_score} = \min_{c \in \text{classes}} (\text{max\_score}_c)$$
  - `ANY`: Eligible frames must have detections for $\ge 1$ requested classes $\ge$ `min_detector_score`.  
    $$\text{object\_support\_score} = \max_{c \in \text{matched}} (\text{max\_score}_c)$$
* **Deterministic Tie-Breaking:**
  `object_support_score DESC, video_id ASC, timestamp_ms ASC, keyframe_uid ASC`.
* **Hit Evidence Output:**
  Includes canonical keyframe UID (`BTC:{video_id}:KF{n:06d}`), frame index, timestamp, rank, raw score, matched classes, per-class detector scores, per-class counts, top bounding boxes, top 5 detections, and source file reference (`objects/{video_id}/{n:03d}.json`).

---

## 6. Real Operational Benchmark & Integrity Probes

All 7 probe categories executed against the real 177,321-frame database (`F:/AIC_WORK/artifacts/evaluation/btc_objects_v1/m5d_btc_obj_bench_1787199432/summary.json`):

| Probe Category | Count | Result | Details |
| :--- | :--- | :--- | :--- |
| **Single-Class Probes** | 35 / 35 | **PASS** (100%) | Verified frequent, medium, and rare classes; returned valid rankings in 1–3ms |
| **Multi-Class Co-occurrence** | 13 / 13 | **PASS** (100%) | ALL 2-class, ALL 3-class, and ANY 2+-class verified against exact Boolean contracts |
| **Threshold Monotonicity** | 4 / 4 | **PASS** (100%) | Monotonic filtering verified across thresholds $0.0, 0.25, 0.50, 0.75$ |
| **Candidate Scope Restriction** | 4 / 4 | **PASS** (100%) | 1-video, 5-video, empty, and invalid scopes verified with 0 out-of-scope hits |
| **Class Validation & Normalization** | 4 / 4 | **PASS** (100%) | Uppercase, mixed case, trailing whitespace, unknown classes, duplicates verified |
| **Raw BBox Evidence Checks** | 25 / 25 | **PASS** (100%) | Detections, scores, and bounding boxes verified 1:1 against raw JSON in zip archive |
| **Manual AIC Demonstrations** | 10 / 10 | **PASS** (100%) | 10 representative AIC concepts translated to detector classes; verified valid hits |

### Performance Summary:
* **Single-Class Search p50 Latency:** **1.31 ms**
* **Multi-Class Search Latency:** 2–15 ms (unconstrained multi-way SQLite joins)
* **Raw Corpus Scan in Hot Path:** **NO (0 scans)**

---

## 7. Operational Endpoints & CLI Interface

### Backend API Endpoints (`aic2026.search.api`):
* `GET /api/v1/lanes/btc-objects/health`: Health status, counts, and passport checksums.
* `GET /api/v1/lanes/btc-objects/classes`: Complete list of 584 classes and frame counts.
* `POST /api/v1/lanes/btc-objects/search`: Standalone structured object search.

### CLI Subcommands (`aic`):
* `aic btc-objects-health`
* `aic btc-objects-classes --limit 10`
* `aic search-btc-objects --class person --class motorcycle --match-mode ALL --top-k 5`

---

## 8. Quality Evaluation Status

* **Status:** `M5_BTC_OBJECTS_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH`
* **Applicability:** `OBJECT_DEV_STRUCTURED_APPLICABILITY = NOT_AVAILABLE`
* **Statement:** No ground truth relevance labels exist for detector class queries on the 15 DEV natural queries. Evaluation measures deterministic retrieval correctness, integrity, and latency only.

---

## 9. Non-Weakening & System Integrity Audit

* **Detector Inference Reruns:** 0 (immutability preserved)
* **Shared Raw Source Mutations:** 0
* **M1 Runtime Database Rebuilds:** 0
* **Other Lane Modifications:** 0 (SigLIP, BTC CLIP, ASR, OCR, Media, Qwen lanes 100% untouched)
* **Frontend Modifications:** 0 (out of scope)
* **Fusion / Pruning / RRF Changes:** 0

---

## 10. Acceptance Gate & Lineage Transition

```text
======================================================================
M5D BTC OBJECTS CORE RETRIEVAL COMPLETE
M5D_ACCEPTANCE: PASS
M5E_READY: YES
M5 overall: OPEN
======================================================================
```
