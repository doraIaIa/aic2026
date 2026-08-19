# M1D — BTC Keyframe, Map, CLIP, Object, and Media Mapping Acceptance Report

**Milestone:** M1 — Data Hub & Unified Mapping  
**Slice:** M1D — BTC Keyframe + Map + CLIP + Object + Media Mapping  
**Date:** 2026-08-19  
**Status:** **ACCEPTANCE PASS** (100% Deterministic, Fail-Closed Validated)

---

## 1. Executive Summary & Coordinate Space Invariant

Milestone 1 Slice M1D materializes the complete, authoritative **BTC frame space** and establishes deterministic, fail-closed bindings to map-keyframes, JPEGs, dense raw CLIP feature rows, OpenImages object detections, YouTube media-info metadata priors, M1A video identity, and source-video timeline.

### Invariant: BTC vs CUSTOM Frame Space Independence

The BTC and CUSTOM frame coordinate spaces are distinct and strictly decoupled:

| Dimension | BTC Frame Space (M1D) | CUSTOM Frame Space (M1B) |
| :--- | :--- | :--- |
| **Origin** | BTC Competition Organizer Extraction | AIC 2026 In-house Custom Extraction |
| **Keyframe Count** | **177,321** keyframes | **116,767** keyframes |
| **Videos Covered** | **873 / 873** canonical videos | **873 / 873** canonical videos |
| **Canonical UID Format** | `BTC:{video_id}:KF{n:06d}` (e.g. `BTC:L21_V001:KF000001`) | `CUSTOM:{video_id}:F{frame_idx}` (e.g. `CUSTOM:L21_V001:F0`) |
| **Local Frame Key** | Local keyframe number `n` ($1 \le n \le N_V$) from map CSV | Physical `frame_idx` derived from video timeline |
| **Image Storage** | `data_extracted/keyframes/{video_id}/{n:03d|n:04d}.jpg` | `data_extracted/custom_keyframes/{video_id}/{frame_idx:06d}.jpg` |
| **CLIP Representation** | 873 dense `.npy` arrays ($177,321 \times 512$, `float16`, unit L2 norm) | Future derived / unified lane |
| **Object Detections** | 177,321 OpenImages JSONs ($17,732,100$ detections, 100/frame) | N/A |
| **Media Prior** | Video-level metadata JSONs (873 videos) | N/A |
| **Submission Authority** | **Source Video Timeline** (`MediaResolver` / `ffmpeg`) | **Source Video Timeline** (`MediaResolver` / `ffmpeg`) |

> [!IMPORTANT]
> BTC and CUSTOM coordinate spaces are strictly namespaced. Under no circumstances is `BTC keyframe #n` conflated with `CUSTOM keyframe #n`. Exact-frame competition submission authority always resolves against the **source video timeline**.

---

## 2. Empirical Verification & Authoritative Metric Proofs

All 873 canonical videos were processed across the entire real dataset without approximation:

| Component | Target Metric | Measured Value | Validation Status |
| :--- | :--- | :--- | :--- |
| **Video Manifest Coverage** | 873 canonical videos | **873 / 873** (100.00%) | **PASS** |
| **BTC Map CSV Files** | 873 CSV files in `data_extracted/map-keyframes` | **873 / 873** (100.00%) | **PASS** |
| **BTC Keyframe Rows** | Exact row sum across 873 CSVs | **177,321 rows** | **PASS** |
| **BTC JPEG Files** | Exact image count in `data_extracted/keyframes` | **177,321 JPEGs** | **PASS** |
| **Raw CLIP Arrays** | 873 `.npy` files in `data_extracted/clip-features-32` | **873 / 873** (100.00%) | **PASS** |
| **Raw CLIP Rows** | Exact row sum across 873 `.npy` arrays | **177,321 vector rows** | **PASS** |
| **Raw CLIP Dimensions** | 512 dimensions, `float16` dtype, unit L2 norm | **512-D, float16, L2-norm ~ 1.000000** | **PASS** |
| **Raw CLIP Row Formula** | Row $i \leftrightarrow \text{local keyframe } n = i + 1$ | **177,321 / 177,321 mapped (0 unmapped)** | **PASS** |
| **Object Detections Archive** | 177,321 JSONs in `data/objects-aic25-b1.zip` | **177,321 / 177,321 JSONs present** | **PASS** |
| **Total Object Detections** | Detections extracted from OpenImages schema | **17,732,100 detections** (100 per frame) | **PASS** |
| **Object Keyframe Coverage** | Keyframes with `HAS_OBJECTS` status | **177,321 / 177,321 (100.00%)** | **PASS** |
| **Empty / Unavailable Objects** | Missing or zero-detection keyframes | **0 empty, 0 unavailable** | **PASS** |
| **Media-Info Archive** | 873 JSONs in `data/media-info-aic25-b1.zip` | **873 / 873 JSONs present** | **PASS** |
| **Existing FAISS Index** | `clip-faiss-btc-v1` metadata mapping | **177,321 / 177,321 vectors mapped (0 gap)** | **PASS** |
| **Raw Source Mutations** | Shared `AIC_2026` drive immutability | **0 raw mutations, 0 inference reruns** | **PASS** |

---

## 3. Cryptographic Provenance & Deterministic Checksums

All materialized artifacts in `F:\AIC_WORK\artifacts\canonical_btc_v1` carry cryptographic SHA-256 signatures:

```json
{
  "btc_space_id": "btc_keyframes_v1",
  "video_count": 873,
  "btc_keyframe_count": 177321,
  "btc_catalog_checksum": "70332506a7d7f5bf2ce5f4ec72cd91a4bffe3c551a7aeeed3a7d7b0c1056cd12",
  "raw_clip_file_count": 873,
  "raw_clip_row_count": 177321,
  "raw_clip_rowmap_checksum": "08921ac7c016e22030bcfe03928a5306da69cbc8bb79ce79f536c2bf4439075f",
  "object_canonical_checksum": "78f087b931d94e2efd0c69c8e6dd4072abdb23ccf55c9b3ea253aea85aeaf24c",
  "media_info_checksum": "7b16a48ff935d5a690980e1b02391b15b09c3cd010844eea83ea6725d225999d",
  "existing_faiss_checksum": "08ed3cdbe250401560d04a4a26f9958c92672739141b664c5c59b75bfcfac0b3"
}
```

### Materialized Artifact Manifest (`F:\AIC_WORK\artifacts\canonical_btc_v1`)

| Artifact File | Size | Description |
| :--- | :--- | :--- |
| `btc_keyframes.jsonl` | 87.4 MB | 177,321 canonical BTC keyframe entities with derived timestamps and relative image paths |
| `btc_clip_raw_rowmap.jsonl` | 74.3 MB | 177,321 1:1 deterministic bindings from raw CLIP arrays to BTC keyframe UIDs |
| `btc_objects.jsonl` | 8.54 GB | 17,732,100 OpenImages object detection entities (scores, class names/entities/labels, bboxes) |
| `btc_object_coverage.jsonl` | 55.9 MB | 177,321 keyframe coverage status records (`HAS_OBJECTS`, detection count, source ref) |
| `media_info.jsonl` | 1.91 MB | 873 YouTube video-level metadata records (title, author, duration, keywords, URLs) |
| `btc_space.json` | 354 B | Coordinate space definition, ordering rule, and catalog checksum |
| `btc_clip_raw_passport.json` | 404 B | OpenAI CLIP ViT-B/32 dense feature passport and schema validation |
| `btc_clip_existing_index_passport.json` | 384 B | FAISS vector index provenance, metric, and 1:1 BTC coverage confirmation |
| `btc_object_space.json` | 362 B | Object detection coordinate space metadata and archive provenance |
| `source_registry.jsonl` | 1.90 KB | Provenance entries establishing immutability and lineage of raw source archives |
| `build_manifest_m1d.json` | 1.41 KB | Complete build execution manifest and validation summary |

---

## 4. 5-Video Candidate Drilldown & Media Resolver Verification

To verify candidate reachability and end-to-end alignment, 5 canonical videos with diverse characteristics across multiple series were deeply inspected:

### Video Characteristics & Mappings

| Video ID | Ordinal | Series | Video Meta Duration | BTC Keyframes | Raw CLIP Shape | Raw CLIP Norm | Media-Info Title |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`L21_V001`** | 0 | L21 | 1244.54s | 307 | (307, 512) `float16` | 0.999747 | *60 Giây Sáng - Ngày 01082024 - HTV Tin Tức Mới Nhất* |
| **`L24_V008`** | 91 | L24 | 562.11s | 165 | (165, 512) `float16` | 1.000278 | *Kim Sư Du Hí Giúp Tiểu Kê  Đoàn Lân Huỳnh Lân Đường* |
| **`L25_V002`** | 129 | L25 | 1122.38s | 352 | (352, 512) `float16` | 0.999737 | *BÍ QUYẾT ÔN THI THPT 2024  Môn Lịch sử  Chuyên đề 1* |
| **`L26_V361`** | 576 | L26 | 291.63s | 164 | (164, 512) `float16` | 1.000200 | *CHÂN GIÒ OM SẤU_NẤU LÀ NGON ĂN LÀ MÊ  MÓN NGON MỖI NGÀY* |
| **`L30_V041`** | 817 | L30 | 80.58s | 24 | (24, 512) `float16` | 0.999822 | *Lan tỏa năng lượng tích cực 2024 Tìm về hồi ức tuổi thơ* |

### Sample Keyframe ($n=10$) End-to-End Traceability

| Video ID | Sample Keyframe UID | Map `n` | Map `pts_time` (`ms`) | Map `frame_idx` | CLIP Row Index | Top Object Detections (Class, Score, BBox) | Media Resolver Source Video |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`L21_V001`** | `BTC:L21_V001:KF000010` | 10 | 37.70s (37,700ms) | 1131 | `i = 9` | `/m/0dzct` (0.93, `[0.26,0.66,0.42,0.72]`); `/m/04yx4` (0.86, `[0.15,0.20,0.93,0.48]`) | 1261.73s @ 30.0 fps (37,849 frames) |
| **`L24_V008`** | `BTC:L24_V008:KF000010` | 10 | 34.72s (34,720ms) | 868 | `i = 9` | `/m/0138tl` (0.78, `[0.27,0.36,0.88,0.62]`); `/m/0138tl` (0.66, `[0.28,0.60,0.46,0.75]`) | 562.11s @ 25.0 fps (14,051 frames) |
| **`L25_V002`** | `BTC:L25_V002:KF000010` | 10 | 42.00s (42,000ms) | 1050 | `i = 9` | `/m/050k8` (0.61, `[0.00,0.00,1.00,1.00]`); `/m/03120` (0.55, `[0.00,0.00,1.00,1.00]`) | 1139.89s @ 25.0 fps (28,496 frames) |
| **`L26_V361`** | `BTC:L26_V361:KF000010` | 10 | 8.96s (8,960ms) | 224 | `i = 9` | `/m/0frqm` (0.22, `[0.10,0.00,1.00,1.00]`); `/m/0frqm` (0.15, `[0.12,0.00,0.97,0.58]`) | 305.13s @ 25.0 fps (7,627 frames) |
| **`L30_V041`** | `BTC:L30_V041:KF000010` | 10 | 33.20s (33,200ms) | 830 | `i = 9` | `/m/0c9ph5` (0.93, `[0.35,0.26,0.79,0.58]`); `/m/0c9ph5` (0.92, `[0.02,0.31,0.53,0.63]`) | 84.20s @ 25.0 fps (2,103 frames) |

---

## 5. Architectural Contracts & Safety Guarantees

1. **Deterministic Identity:** Every BTC keyframe is uniquely addressable via `BTC:{video_id}:KF{n:06d}`.
2. **Dense CLIP ViT-B/32 Row Formula:** For any video $V$, row $i$ in `data_extracted/clip-features-32/{video_id}.npy` corresponds exactly to local keyframe $n = i + 1$.
3. **OpenImages Object Space:** Object detections are keyed by `BTC_OBJECT:{keyframe_uid}:D{local_index}` with normalized bounding boxes `[ymin, xmin, ymax, xmax]` in $[0, 1]$.
4. **Media Prior Distinction:** Media-info is stored strictly as a video-level prior in `media_info.jsonl`, keeping frame-level evidence clean and preventing artificial duplication.
5. **Fail-Closed Validation:** `BtcValidator` enforces video foreign keys, strictly positive FPS, non-negative timestamps, path safety, and array dimensions across all 177,321 keyframes.

---

## 6. Verification & Test Suite Summary

- **Total Test Count:** **228 / 228 tests passing** (100% pass rate).
- **BTC Mapping Tests:** 10 comprehensive unit/integration tests in `tests/test_btc_mapping.py` covering UID format, timestamp derivation, raw CLIP formula, OpenImages detection validation, media-info mapping, Data Hub registry querying, and mock materialization.

---

## 7. Acceptance Gate & Transition

```text
======================================================================
M1D BTC MAPPING COMPLETE
M1D_ACCEPTANCE: PASS
M1E_READY: YES
======================================================================
```
