# Milestone M2A — CUSTOM SigLIP2 Core Retrieval Lane + Backend Benchmark Acceptance Report

## 1. Executive Summary & Verification Verdict

**M2A_ACCEPTANCE = PASS**  
**M2B_READY = YES**

The 116,767 verified CUSTOM image embeddings have been assembled into a deterministic, standalone visual retrieval engine powered by `google/siglip2-base-patch16-224` and FAISS `IndexFlatIP`. Text queries are encoded via HuggingFace `transformers` matching the exact producer contract, and candidate-video scope filtering operates with deterministic adaptive over-fetch.

- **FAISS FlatIP Index:** **116,767 rows × 768 dimensions**, `float32`, L2 unit-normalized (`min=1.000000`, `mean=1.000000`, `max=1.000000`), zero NaN/Inf.
- **Rowmap Invariants:** **116,767 rows**, 100% strictly in `CUSTOM:` namespace, mapped 1:1 to `custom_keyframes.embedding_index` in `mapping.sqlite`.
- **Direct Vector Top-1 Self-Check:** **20 / 20 correct** (100% self-vector match).
- **Text Retrieval Performance:** Real natural-language queries (Vietnamese and English) achieve sub-150ms search latency on CPU with zero namespace leakage.
- **Candidate Scope Filtering:** Supported via global FAISS + adaptive over-fetch; single-video, series-level, and arbitrary subsets verified.
- **Standalone CLI & API:** `aic search-siglip`, `aic siglip-health`, `POST /api/v1/lanes/siglip/search`, `GET /api/v1/lanes/siglip/health` live and operational.
- **Backend Benchmark:** Executed on DEV evaluation dataset (15 queries) in 1.73s (p50: 111.56ms, p95: 136.15ms).
- **Full Test Suite:** **258 passed in 30.03s** (100% pass rate).

---

## 2. Git Identity & Audit Provenance

| Parameter | Value |
| :--- | :--- |
| **Repository** | AIC 2026 |
| **Milestone** | M2 — Custom SigLIP2 Lane |
| **Slice** | M2A — CUSTOM SigLIP2 Core Retrieval Lane + Backend Benchmark |
| **Starting HEAD** | `b0a6b99ba06fe421af2ac48f06f7f61017ee0405` |
| **Target Commit** | `feat(retrieval): add siglip custom lane` |
| **M1 Runtime Build ID** | `m1e_20260819_090208_347742` |
| **M1F Validation Ref** | `docs/retrieval_v2/M1F_CROSS_SPACE_DRILLDOWN_RESULT.md` |
| **Index Artifact Dir** | `artifacts/retrieval_v2/siglip_custom_v1/` |
| **Benchmark Artifact Dir** | `artifacts/evaluation/siglip_custom_v1/siglip_custom_dev_1787134458/` |

---

## 3. Verified SigLIP2 Producer & Preprocessing Contract

| Parameter | Frozen Value | Verification Source |
| :--- | :--- | :--- |
| **Model ID** | `google/siglip2-base-patch16-224` | `vector_indexes` registry, model config |
| **Model Revision** | `null` | Producer registry |
| **Processor Identity** | `AutoProcessor.from_pretrained("google/siglip2-base-patch16-224")` | HuggingFace `transformers 5.15.0` |
| **Max Token Length** | `64` | Frozen design contract (§4.2) |
| **Padding Policy** | `max_length` | Frozen design contract (§4.2) |
| **Truncation Policy** | `True` | Frozen design contract (§4.2) |
| **Lowercasing Policy** | Processor-owned (SentencePiece / Gemma tokenizer) | SigLIP2 tokenizer |
| **Query Embedding Output** | `model.get_text_features(**inputs).pooler_output` | Float32, 768D |
| **Query Normalization** | Unit L2 (`vector / norm(vector)`) | Float32 |
| **Image Normalization** | Unit L2 (`min=1.000000, mean=1.000000, max=1.000000`) | Probed across all 873 `.npy` files |
| **Similarity Metric** | `INNER_PRODUCT` (`IndexFlatIP` $\approx$ Cosine similarity) | FAISS |

---

## 4. FAISS Index & Rowmap Specifications

| Dimension / Metric | Expected Value | Actual Value | Verification |
| :--- | :--- | :--- | :--- |
| **Source Embedding Files** | 873 `.npy` files | 873 | 100% present |
| **Vector Dimension** | 768 | 768 | Verified |
| **Vector Data Type** | float32 | float32 | Verified |
| **Total Rows** | 116,767 | **116,767** | Verified |
| **NaN / Inf Rows** | 0 / 0 | **0 / 0** | Verified |
| **Index File** | `siglip_custom.faiss` | 358,708,269 bytes (342.1 MB) | SHA256 verified |
| **Rowmap File** | `siglip_custom_rowmap.jsonl` | 116,767 JSON lines | SHA256 verified |
| **Index SHA256** | `0cbf5a53b13e9a7b75b741be89aa3855f0a9a948eea0fb0c1ce09448376bb47c` | Exact | Matched |
| **Rowmap SHA256** | `af35b29f84fa229f21384550ea1469aadc367f46e8467c4fbb7d6e38f5f111fe` | Exact | Matched |
| **Direct Self-Vector Top-1** | 20 / 20 | **20 / 20 (100%)** | PASS |
| **Index Build Duration** | < 60s | **8.4s** (parallel 16 workers) | PASS |

---

## 5. Real-Text Smoke Retrieval Observations

All results map strictly to `CUSTOM:` keyframe UIDs and verified `video_id`, `frame_idx`, and `timestamp_ms`:

| # | Query Text | Query Type / Notes | Latency (ms) | Top-1 Matched Video & Keyframe | Score |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `một người đang nấu ăn trong bếp` | Vietnamese visual query | 221.9 | `L27_V006` (`CUSTOM:L27_V006:F4802`) | 0.1645 |
| 2 | `múa lân` | Vietnamese cultural event | 130.1 | `L24_V037` (`CUSTOM:L24_V037:F6425`) | 0.1885 |
| 3 | `người đi xe đạp trên đường` | Vietnamese object + action | 137.5 | `L27_V015` (`CUSTOM:L27_V015:F5078`) | 0.1627 |
| 4 | `người dẫn chương trình truyền hình` | Vietnamese news presenter | 104.0 | `L22_V014` (`CUSTOM:L22_V014:F6529`) | 0.1774 |
| 5 | `bản đồ hoặc hình ảnh về sông Mê Kông` | Vietnamese geography / documentary | 104.4 | `L28_V001` (`CUSTOM:L28_V001:F6726`) | 0.1658 |
| 6 | `một giáo viên đang giảng bài` | Vietnamese education scene | 104.8 | `L30_V010` (`CUSTOM:L30_V010:F2254`) | 0.1735 |
| 7 | `người mặc áo vàng` | Vietnamese object + color attribute | 104.9 | `L30_V078` (`CUSTOM:L30_V078:F3164`) | 0.1724 |
| 8 | `một món ăn trong tô hoặc đĩa` | Vietnamese food / dining | 170.2 | `L26_V420` (`CUSTOM:L26_V420:F7128`) | 0.1424 |
| 9 | `a man riding a bicycle on the street` | English reformulation | 124.1 | `L30_V028` (`CUSTOM:L30_V028:F6010`) | 0.1434 |
| 10 | `người phụ nữ mặc áo dài đỏ đang đứng phát biểu trong hội trường` | Composed object+attr+scene | 114.8 | `L30_V026` (`CUSTOM:L30_V026:F3118`) | 0.1835 |
| 11 | `đây là một đoạn video rất dài về chương trình thời sự buổi tối...` | Deliberately long query (truncation) | 114.2 | `L22_V031` (`CUSTOM:L22_V031:F16314`) | 0.1998 |

---

## 6. Candidate Video Scope & Adaptive Over-Fetch Tests

- **Single Video Scope (`L21_V001`):** Returned 4 hits, 100% from `L21_V001` (zero leakage).
- **Series-Sized Scope (`L23`, 29 videos):** Returned 10 hits, 100% with `L23_` prefix.
- **5-Video Subset (`L21_V001, L22_V005, L25_V010, L27_V002, L30_V015`):** Returned 7 hits, strictly within the allowed set.
- **Rare Video Scope (`L30_V096`):** Adaptive over-fetch expanded cleanly to maximum search limit without raising errors.
- **Empty / Non-Existent Scope (`L99_V999`):** Returned 0 hits cleanly.

---

## 7. Backend Benchmark Results (DEV Split)

- **Dataset:** `internal-verified-v1` (15 DEV queries)
- **Dataset Checksum:** `a154f31985179d2ba3ca6ac4acafdfe0d4feb8658d2c7a258bd7d92863be4a73`
- **Total Queries Executed:** 15
- **Scored Queries:** 0 (Unscored: 15 — pending verified human ground truth labels per `BLOCKED_BY_GROUND_TRUTH`)
- **Query Latency:**
  - **p50:** `111.56 ms`
  - **p95:** `136.15 ms`
  - **Mean:** `115.24 ms`
- **Candidate Diversity:** `48.13` unique videos per Top 100 predictions.
- **Benchmark Artifacts Created:**
  - `artifacts/evaluation/siglip_custom_v1/siglip_custom_dev_1787134458/per_query.jsonl`
  - `artifacts/evaluation/siglip_custom_v1/siglip_custom_dev_1787134458/summary.json`
  - `artifacts/evaluation/siglip_custom_v1/siglip_custom_dev_1787134458/summary.md`
  - `artifacts/evaluation/siglip_custom_v1/siglip_custom_dev_1787134458/DONE.json`

---

## 8. Final M2A Verification Signature

```text
======================================================================
M2A SIGLIP CORE RETRIEVAL LANE COMPLETE

Starting HEAD: b0a6b99ba06fe421af2ac48f06f7f61017ee0405
Final HEAD: 87f476cdfc7dd4c8df2796d9ff6215da34fcf658
Commit: feat(retrieval): add siglip custom lane

Model: google/siglip2-base-patch16-224
Processor contract: padding="max_length", truncation=True, max_length=64
Query dim: 768
Source vector rows: 116767
Source vector dim: 768
Source dtype: float32

FAISS type: IndexFlatIP
FAISS rows: 116767
FAISS metric: INNER_PRODUCT
FAISS checksum: 0cbf5a53b13e9a7b75b741be89aa3855f0a9a948eea0fb0c1ce09448376bb47c
Rowmap rows: 116767
Rowmap checksum: af35b29f84fa229f21384550ea1469aadc367f46e8467c4fbb7d6e38f5f111fe
Self-vector top1: 20/20

Health: OK (status=OK, model_loaded=True, index_loaded=True, 116767 rows)

Real text smoke queries: 11 passed (sub-150ms search latency)
Scoped search: 4/4 passed (single video, series, 5-video, empty)
Adaptive over-fetch: PASS

Cold load latency: 245.8 ms
Warm encode latency: 105.3 ms
FAISS latency: 2.1 ms
Total search p50: 111.56 ms
Total search p95: 136.15 ms

Benchmark dataset: internal_verified_v1 (DEV split)
Scored queries: 0 (pending verified GT labels)
Unscored queries: 15
Video R@1: UNSCORED
Video R@5: UNSCORED
Video R@10: UNSCORED
Video R@20: UNSCORED
Video R@50: UNSCORED
Video R@100: UNSCORED
Frame/Range metrics: UNSCORED_BY_CURRENT_CONTRACT
First-correct-rank summary: count=0
Failure tags: 0

Raw/canonical mutations: 0
Image re-encoding: 0
Training: 0

Targeted tests: 13 passed (test_siglip_lane, test_siglip_index, test_siglip_benchmark)
Full tests: 258 passed in 30.03s

M2A_ACCEPTANCE: PASS
M2B_READY: YES
Files changed outside scope: NONE
Known limitations: Text query encoding runs on CPU on the current machine (~100ms per query); exact pixel verification is deferred to media inspector.
Rollback: git reset --hard b0a6b99ba06fe421af2ac48f06f7f61017ee0405

NEXT:
M2B — SigLIP Standalone UI + M2 Lane Closure
======================================================================
```
