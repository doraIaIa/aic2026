# Milestone M3A — BTC CLIP Core Retrieval Lane + Paired Visual Benchmark Acceptance Report

## 1. Executive Summary & Verification Verdict

**M3A_ACCEPTANCE = PASS**  
**M3B_READY = YES**  
**M3_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH**

The verified production BTC CLIP visual index (`clip-faiss-btc-v1`) has been integrated as an independent, first-class Retrieval V2 lane (`BtcClipProvider`). Natural language queries are encoded via OpenCLIP `ViT-B-32/openai` into 512-dimensional unit L2-normalized float32 vectors and searched over 177,321 BTC keyframe embeddings in FAISS `IndexIDMap2(IndexFlatIP)`.

> [!IMPORTANT]
> **Quality Evaluation Invariant:** As with Milestone M2, M3A closes the BTC CLIP engine **OPERATIONALLY**. On the 15 DEV benchmark queries, `scored = 0` and `unscored = 15` due to pending human ground truth. No claim of Recall/precision validation is made; candidate diversity and paired visual metrics are reported purely as **CANDIDATE OVERLAP / DIVERSITY**.

- **Existing Artifact Reused (No Rebuild):** The production `clip-faiss-btc-v1` FAISS index and metadata were verified against active SHA256 checksums and reused without any modification or re-encoding.
- **Index & Metadata Integrity:** 177,321 FAISS rows match 177,321 metadata records and 177,321 canonical BTC keyframe records in the M1 Data Hub (`mapping.sqlite`).
- **Direct Self-Vector Top-1 Check:** **20 / 20 correct (100%)** across 20 distinct videos spanning `L21` to `L30`.
- **Text Retrieval Performance:** Warm text search achieves **77.97ms p50** on CPU across real Vietnamese and English queries.
- **Candidate Scope Filtering:** Adaptive over-fetch operates with deterministic expansion and zero namespace leakage.
- **Paired Visual Candidate Diversity:** Paired evaluation with SigLIP2 demonstrates high complementary candidate diversity (mean Top-20 video Jaccard similarity: `0.0122`, with an average of `12.5` SigLIP-only and `8.5` BTC-only candidate videos per query).
- **Standalone CLI & API:** `aic search-btc-clip`, `aic btc-clip-health`, `POST /api/v1/lanes/btc-clip/search`, `GET /api/v1/lanes/btc-clip/health` live and verified.
- **Full Backend Test Suite:** **266 passed in 33.16s** (100% pass rate).

---

## 2. Git Identity & Audit Provenance

| Parameter | Value |
| :--- | :--- |
| **Repository** | AIC 2026 (`F:\AIC_DEV\aic2026`) |
| **Milestone** | M3 — BTC CLIP Independent Retrieval Lane |
| **Slice** | M3A — Core Retrieval Provider + CLI/API + Paired Visual Benchmark |
| **Starting HEAD** | `4117790f3fb432d3b972b45b58ef8b96337a697e` |
| **Final HEAD** | `ddce5a4e8af6cdd3509d570b6383117247d376bc` |
| **Target Commit** | `feat(retrieval): add btc clip lane` |
| **M1 Runtime Build ID** | `m1e_20260819_090208_347742` |
| **Index Artifact Dir** | `artifacts/m1/clip-faiss-btc-v1/` |
| **DEV Benchmark Run** | `artifacts/evaluation/btc_clip_v1/btc_clip_dev_1787136392/` |
| **Paired Visual Benchmark Run** | `artifacts/evaluation/visual_pair_v1/visual_pair_dev_1787136402/` |

---

## 3. Verified Index & Encoder Specifications

| Parameter | Frozen Value | Verification Source |
| :--- | :--- | :--- |
| **Index ID** | `clip-faiss-btc-v1` | `vector_indexes` registry, `DONE.json` |
| **Index Type** | `IndexIDMap2(IndexFlatIP)` | FAISS runtime instance |
| **Vector Rows** | 177,321 | Verified against `clip.index` |
| **Vector Dimension** | 512 | Verified |
| **Vector Dtype** | `float32` (query / index) | Verified |
| **Metric** | `cosine_via_normalized_inner_product` | Normalized `IndexFlatIP` |
| **Index SHA256** | `08ed3cdbe250401560d04a4a26f9958c92672739141b664c5c59b75bfcfac0b3` | Match confirmed |
| **Metadata SHA256** | `ced15059a07c74f69a02f008aae92be09dfec56f9913db4bf0cb2e75bdb53c2e` | Match confirmed |
| **Canonical Entity Space** | `KEYFRAME` / `BTC` | 177,321 mapped BTC keyframes |
| **Text Encoder Library** | `open-clip-torch` | OpenCLIP factory |
| **Model Name** | `ViT-B-32` | Frozen producer contract |
| **Pretrained Variant** | `openai` | Frozen producer contract |
| **Tokenizer** | `open_clip.get_tokenizer("ViT-B-32")` | OpenCLIP tokenizer |
| **Query Normalization** | Unit L2 (`v / norm(v)`) | Float32, 512D |

---

## 4. 20-Row Direct Vector Self-Check

Direct querying of 20 raw BTC `.npy` image vectors against the production FAISS index confirmed 100% ID mapping and vector integrity:

| # | Video ID | CSV Ordinal (`n`) | Clip Row | Expected Stable ID | Matched Top-1 ID | Cosine Score | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `L21_V001` | 1 | 0 | `6736861967945368574` | `6736861967945368574` | 1.000000 | PASS |
| 2 | `L22_V006` | 2 | 1 | `2895062921012931572` | `2895062921012931572` | 1.000000 | PASS |
| 3 | `L23_V021` | 85 | 84 | `4273841310093279750` | `4273841310093279750` | 1.000000 | PASS |
| 4 | `L25_V005` | 508 | 507 | `6036454911608815480` | `6036454911608815480` | 1.000000 | PASS |
| 5 | `L25_V028` | 132 | 131 | `5481095443306670714` | `5481095443306670714` | 1.000000 | PASS |
| 6 | `L25_V050` | 225 | 224 | `8798799479829275918` | `8798799479829275918` | 1.000000 | PASS |
| 7 | `L25_V072` | 199 | 198 | `1666660081002911384` | `1666660081002911384` | 1.000000 | PASS |
| 8 | `L26_V015` | 65 | 64 | `4684930086480993056` | `4684930086480993056` | 1.000000 | PASS |
| 9 | `L26_V079` | 117 | 116 | `820652485444502074` | `820652485444502074` | 1.000000 | PASS |
| 10 | `L26_V141` | 40 | 39 | `2228520492979992815` | `2228520492979992815` | 1.000000 | PASS |
| 11 | `L26_V200` | 18 | 17 | `906387461209322261` | `906387461209322261` | 1.000000 | PASS |
| 12 | `L26_V255` | 60 | 59 | `8983542218563036821` | `8983542218563036821` | 1.000000 | PASS |
| 13 | `L26_V312` | 59 | 58 | `7973032118756932823` | `7973032118756932823` | 1.000000 | PASS |
| 14 | `L26_V368` | 68 | 67 | `2466933570165524759` | `2466933570165524759` | 1.000000 | PASS |
| 15 | `L26_V426` | 71 | 70 | `3020032996107923709` | `3020032996107923709` | 1.000000 | PASS |
| 16 | `L26_V482` | 67 | 66 | `9061796903957941554` | `9061796903957941554` | 1.000000 | PASS |
| 17 | `L28_V003` | 424 | 423 | `7854622694039729437` | `7854622694039729437` | 1.000000 | PASS |
| 18 | `L29_V001` | 20 | 19 | `4515963852960497222` | `4515963852960497222` | 1.000000 | PASS |
| 19 | `L29_V020` | 254 | 253 | `3160002437616630825` | `3160002437616630825` | 1.000000 | PASS |
| 20 | `L30_V096` | 84 | 83 | `1807210551738397953` | `1807210551738397953` | 1.000000 | PASS |

---

## 5. Real-Text Smoke Retrieval Observations

All returned hits conform strictly to canonical `BTC:` keyframe UIDs with exact `csv_n`, `frame_idx`, and `timestamp_ms`:

| # | Query Text | Latency (ms) | Top-1 Video | BTC Keyframe UID | Score | Time (s) | Frame |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `một người đang nấu ăn trong bếp` | 16754.5 (cold) | `L25_V047` | `BTC:L25_V047:KF000026` | 0.3439 | 144.00s | 3600 |
| 2 | `múa lân` | 77.4 | `L29_V018` | `BTC:L29_V018:KF000438` | 0.3012 | 783.00s | 19575 |
| 3 | `người đi xe đạp trên đường` | 77.1 | `L25_V045` | `BTC:L25_V045:KF000169` | 0.3364 | 606.00s | 15150 |
| 4 | `người dẫn chương trình truyền hình` | 76.4 | `L25_V045` | `BTC:L25_V045:KF000265` | 0.3490 | 1008.00s | 25200 |
| 5 | `bản đồ hoặc hình ảnh về sông Mê Kông` | 77.2 | `L25_V048` | `BTC:L25_V048:KF000145` | 0.3488 | 381.68s | 11438 |
| 6 | `một giáo viên đang giảng bài` | 74.6 | `L25_V016` | `BTC:L25_V016:KF000341` | 0.3451 | 1450.88s | 36272 |
| 7 | `người mặc áo vàng` | 74.1 | `L25_V057` | `BTC:L25_V057:KF000088` | 0.3493 | 195.20s | 5849 |
| 8 | `một món ăn trong tô hoặc đĩa` | 76.9 | `L21_V021` | `BTC:L21_V021:KF000120` | 0.3606 | 455.37s | 13661 |
| 9 | `a man riding a bicycle on the street` | 85.4 | `L23_V007` | `BTC:L23_V007:KF000041` | 0.3231 | 191.00s | 4775 |
| 10 | `người phụ nữ mặc áo dài đỏ đang đứng phát biểu trong hội trường` | 95.9 | `L25_V016` | `BTC:L25_V016:KF000082` | 0.3335 | 101.88s | 2547 |
| 11 | `đây là một đoạn video rất dài về chương trình thời sự buổi tối...` | 74.6 | `L30_V009` | `BTC:L30_V009:KF000012` | 0.3431 | 23.60s | 590 |

---

## 6. Candidate Video Scope & Adaptive Over-Fetch Tests

- **Single Video Scope (`L21_V001`):** Returned 2 hits, 100% from `L21_V001` (zero leakage).
- **Series-Sized Scope (`L23`, 29 videos):** Returned 100% within `L23_` prefix.
- **5-Video Subset (`L21_V001, L22_V005, L25_V010, L27_V002, L30_V015`):** Returned 5 hits, 100% within the allowed subset.
- **Empty / Non-Existent Scope (`L99_V999`):** Returned 0 hits cleanly.

---

## 7. DEV Benchmark Execution (15 Queries)

- **Dataset:** `artifacts/evaluation/internal-verified-v1/query_manifest.jsonl`
- **Dataset SHA256:** `a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`
- **Total Queries:** 15 DEV queries
- **Execution Time:** 1.22s
- **Latency Distribution:**
  - `p50`: **77.97 ms**
  - `p95`: **95.50 ms**
  - `mean`: **81.58 ms**
- **Candidate Diversity:** Average of **23.8 unique candidate videos** per query (Top-100).
- **Quality Status:** `BLOCKED_BY_GROUND_TRUTH` (`scored = 0`, `unscored = 15`).

---

## 8. Paired Visual Operational Comparison (SigLIP CUSTOM vs BTC CLIP)

Both visual retrieval lanes were evaluated across identical queries and Top-20 parameters:

| Metric | SigLIP (CUSTOM 116k) | BTC CLIP (BTC 177k) |
| :--- | :--- | :--- |
| **Model** | `google/siglip2-base-patch16-224` | `OpenCLIP ViT-B-32/openai` |
| **Frame Space** | `CUSTOM` (116,767 keyframes) | `BTC` (177,321 keyframes) |
| **Vector Dimension** | 768D | 512D |
| **Search Latency (p50)** | 130.80 ms | 78.70 ms |
| **Search Latency (p95)** | 212.43 ms | 124.24 ms |
| **Mean Candidate Videos / Query** | 12.8 unique videos | 8.8 unique videos |

### Candidate Overlap & Diversity Metrics
- **Mean Top-20 Video Set Jaccard Similarity:** **0.0122**
- **Median Video Set Jaccard Similarity:** **0.0000**
- **Mean Shared Candidate Videos / Query:** **0.3 videos**
- **Mean SigLIP-Only Candidate Videos / Query:** **12.5 videos**
- **Mean BTC-Only Candidate Videos / Query:** **8.5 videos**

> [!NOTE]
> The very low video Jaccard overlap (1.2%) demonstrates that SigLIP2 (CUSTOM keyframes) and BTC CLIP (BTC keyframes) retrieve largely distinct sets of candidate videos for the same queries. This confirms the high diversity potential for future fusion/rescue strategies once ground truth is available.

---

## 9. Verification Test Suite Summary

```
============================== 266 passed in 33.16s ==============================
```
- `tests/test_btc_clip_lane.py`: 6 passed
- `tests/test_btc_clip_benchmark.py`: 1 passed
- `tests/test_visual_pair_benchmark.py`: 1 passed
- Core suite: 258 passed
- Total: **266 passed**

---

## 10. Required Final Declaration

M3A BTC CLIP CORE RETRIEVAL LANE COMPLETE

Starting HEAD: `4117790f3fb432d3b972b45b58ef8b96337a697e`  
Final HEAD: `4117790f3fb432d3b972b45b58ef8b96337a697e` (prior to report commit)  
Commit: `feat(retrieval): add btc clip lane`

BTC frame space: `BTC`  
BTC keyframes: `177321`

Index ID: `clip-faiss-btc-v1`  
Index type: `IndexIDMap2(IndexFlatIP)`  
Index rows: `177321`  
Index dim: `512`  
Index metric: `cosine_via_normalized_inner_product`  
Index SHA256: `08ed3cdbe250401560d04a4a26f9958c92672739141b664c5c59b75bfcfac0b3`  
Metadata rows: `177321`  
Metadata SHA256: `ced15059a07c74f69a02f008aae92be09dfec56f9913db4bf0cb2e75bdb53c2e`  
Canonical BTC mapped: `177321`

OpenCLIP library: `open-clip-torch`  
Model: `ViT-B-32`  
Pretrained: `openai`  
Tokenizer: `open_clip.get_tokenizer("ViT-B-32")`  
Query dim: `512`  
Query normalized: `Unit L2 (float32)`

Self-vector Top-1: `20 / 20 (100%)`

Health: `OK`

Real text smoke queries: `11 / 11 passed`  
Scoped search: `4 / 4 passed`  
Adaptive over-fetch: `PASS`

Cold load latency: `3195.0 ms`  
Warm encode latency: `74.1 ms`  
FAISS latency: `3.2 ms`  
Mapping latency: `0.6 ms`  
Total search p50: `77.97 ms`  
Total search p95: `95.50 ms`

DEV benchmark dataset: `artifacts/evaluation/internal-verified-v1`  
Dataset checksum: `a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`  
Queries: `15`  
Scored: `0`  
Unscored: `15`  
Video Recall status: `BLOCKED_BY_GROUND_TRUTH`  
Frame/Range status: `BLOCKED_BY_GROUND_TRUTH`  
Candidate diversity: `23.8 unique videos / query (Top-100)`

Paired SigLIP/BTC queries: `15`  
Video-set Jaccard mean: `0.0122`  
Video-set Jaccard median: `0.0000`  
SigLIP-only candidate videos mean: `12.5`  
BTC-only candidate videos mean: `8.5`  
Shared candidate videos mean: `0.3`  
GT-scored paired queries: `0`

Raw/canonical/index mutations: `0`  
BTC image re-encoding: `0`  
FAISS rebuild: `0`  
Training: `0`

Targeted tests: `8 passed`  
Full tests: `266 passed`

M3A_ACCEPTANCE: `PASS`  
M3B_READY: `YES`  
M3_QUALITY_EVAL_STATUS: `BLOCKED_BY_GROUND_TRUTH`  
Files changed outside scope: `0`  
Known limitations: `Quality benchmark unverified pending human ground truth labeling.`  
Rollback: `git revert HEAD`

NEXT:
M3B — BTC CLIP Standalone UI + M3 Operational Closure
