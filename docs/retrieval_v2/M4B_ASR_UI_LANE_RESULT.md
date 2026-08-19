# Milestone M4B Result — ASR BM25 + BGE Standalone UI & ASR Operational Closure

## 1. Executive Summary & Acceptance State

Milestone M4B exposes both M4A ASR retrieval legs (`asr_bm25` and `asr_bge`) as independent Single Lane modes in the frontend retrieval workspace (`F:/aic-video-search-demo`). The ASR subsystem is now operationally closed.

```yaml
ASR_IMPLEMENTATION_ACCEPTANCE: PASS
ASR_OPERATIONAL_ACCEPTANCE: PASS
ASR_QUALITY_EVAL_STATUS: BLOCKED_BY_GROUND_TRUTH
M4_ASR_SUBSYSTEM_CLOSED: YES
M4C_READY: YES
M4_LANE_CLOSED: NO # OCR and Metadata legs remain open
```

---

## 2. Multi-Repository Manifest

| Repository | Path | Baseline Commit | Final M4B Commit |
| :--- | :--- | :--- | :--- |
| **Frontend UI** | `F:/aic-video-search-demo` | `cead8c54618fb5f8575eddb09e30336ccf0e3b6b` | `92d254e5cb300929fefb2aef176f3bf7d254ff96` |
| **Core Backend** | `F:/AIC_DEV/aic2026` | `00b8ad45819ed9a1141a7b03824541d2b854f822` | *Current HEAD* |

---

## 3. ASR Single-Lane Architecture & Invariants

### 3.1 Retrieval Legs

1. **ASR BM25 (`asr_bm25`)**:
   - Runtime: SQLite FTS5 (`asr_fts`) with `unicode61` tokenizer.
   - Canonical Corpus: 107,540 Whisper-medium Vietnamese segments across 859 videos (14 `ZERO_ASR_SEGMENTS` videos).
   - Score Semantics: BM25 raw negative float (`bm25_lower_is_better`). UI clearly labels `BM25 raw score` with note `Lower is better` (never labeled confidence/similarity).

2. **ASR BGE (`asr_bge`)**:
   - Model: `BAAI/bge-m3` (1024D, CLS pooling, L2-normalized embeddings).
   - FAISS Index: `IndexFlatIP(1024)` over 107,540 rows (SHA256: `b084d12764697e7c23b25ec70f02c67a1d7b6a9c461b8c0ca629626edeabc8ff`).
   - Score Semantics: Cosine inner product (`cosine_ip_higher_is_better`). UI clearly labels `Similarity` with note `Higher is better` (never labeled confidence/probability).

### 3.2 Key Invariants & UI Flow

- **Strict Independence**: Each mode triggers ONLY its single backend endpoint (`POST /api/v1/lanes/asr-bm25/search` or `POST /api/v1/lanes/asr-bge/search`). No cross-calling, no dual execution behind one click, no score fusion.
- **Untouched Query**: Queries are sent 100% unchanged. No translation, LLM rewrite, synonym injection, or client-side text manipulation.
- **Timeline SEGMENT Evidence**: Identity is `ASR_SEGMENT` / `temporal_anchor`. Result cards display verbatim transcript snippet text, start/end timecode, duration, and segment UID. No fabricated keyframe IDs or visual frame spaces.
- **Physical Video Refinement**: Selecting an ASR segment card opens `EvidenceInspector`, seeks source video to speech anchor timecode, and enables manual frame stepping and Candidate Builder. Exact physical video remains the frame authority.

---

## 4. Verification & Smoke Results

### 4.1 Automated Test Suites

- **Frontend Vitest**: **34 passed (8 test files)** in 1.61s (including 6 new unit tests in `AsrLanes.test.tsx`).
- **Frontend Typecheck**: `tsc --noEmit` $\rightarrow$ **0 errors**.
- **Frontend Production Build**: `vite build` + `esbuild` $\rightarrow$ **PASS** (10.72s).
- **Core Pytest**: **286 passed** in 103.87s.

### 4.2 Live Retrieval Smoke Execution

Live queries executed against running backend services on both legs:

#### Query 1: `"thành phố Hồ Chí Minh"`
- **ASR BM25** (17.4ms, 5 hits):
  - `#1` `[L22_V020 497.41s–499.41s]` score=`-30.1054` (bm25_lower_is_better): *"thành phố Hồ Chí Minh."*
  - `#2` `[L22_V020 502.41s–504.41s]` score=`-29.4338` (bm25_lower_is_better): *"tại thành phố Hồ Chí Minh."*
  - `#3` `[L25_V001 1586.08s–1588.08s]` score=`-28.9897` (bm25_lower_is_better): *"Cho thành phố Thủ Đức, thành phố Hồ Chí Minh"*
- **ASR BGE** (776.3ms, 5 hits):
  - `#1` `[L22_V020 497.41s–499.41s]` score=`0.8287` (cosine_ip_higher_is_better): *"thành phố Hồ Chí Minh."*
  - `#2` `[L21_V026 156.86s–158.86s]` score=`0.7836` (cosine_ip_higher_is_better): *"thành phố Chí Minh."*
  - `#3` `[L22_V020 502.41s–504.41s]` score=`0.7821` (cosine_ip_higher_is_better): *"tại thành phố Hồ Chí Minh."*
- *Video Overlap Jaccard*: `0.143`

#### Query 2: `"sông Mê Kông"`
- **ASR BM25** (63.2ms, 5 hits):
  - `#1` `[L21_V016 766.42s–769.42s]` score=`-16.3437`: *"Nhiệt ở Hồng Kông do đó lớn hơn những nơi khác."*
  - `#2` `[L21_V016 742.82s–746.82s]` score=`-15.0481`: *"Khi hậu ẩm ước của Hồng Kông khiến cái nóng mùa hè trở nên khó chịu."*
  - `#3` `[L29_V011 99.89s–101.89s]` score=`-13.9555`: *"hạ lưu châu thổ sông Mê Công."*
- **ASR BGE** (324.7ms, 5 hits):
  - `#1` `[L29_V005 256.02s–258.02s]` score=`0.7667`: *"sông Mekong."*
  - `#2` `[L29_V005 1044.50s–1046.50s]` score=`0.7614`: *"dọc sông Mekong"*
  - `#3` `[L29_V005 272.02s–274.02s]` score=`0.6873`: *"sông nước"*
- *Video Overlap Jaccard*: `0.000` (Dense semantic successfully retrieves alternate spelling *"Mekong"*).

#### Query 3: `"giá xăng"`
- **ASR BM25** (3.6ms, 5 hits):
  - `#1` `[L26_V464 176.66s–177.82s]` score=`-17.4928`: *"Xăng và thấm gia vị."*
  - `#2` `[L26_V402 138.27s–142.27s]` score=`-15.9603`: *"Cá xăng lại thấm gia vị thơm mùi xả nữa"*
  - `#3` `[L22_V008 284.02s–287.02s]` score=`-15.6854`: *"giá các mặt hàng xăng dầu trong nước cùng giảm mạnh"*
- **ASR BGE** (291.6ms, 5 hits):
  - `#1` `[L26_V335 189.00s–190.00s]` score=`0.7127`: *"Giá nè"*
  - `#2` `[L26_V467 277.42s–278.42s]` score=`0.6952`: *"xăng ngọt"*
  - `#3` `[L26_V393 176.13s–178.13s]` score=`0.6947`: *"Xào xăng đi"*
- *Video Overlap Jaccard*: `0.000`

#### Query 4: `"kỳ thi tốt nghiệp trung học phổ thông"`
- **ASR BM25** (23.0ms, 5 hits):
  - `#1` `[L25_V036 24.70s–28.70s]` score=`-48.6660`: *"Kỷ thi tốt nghiệp trung học phổ thông quốc gia năm 2024"*
  - `#2` `[L22_V008 83.24s–89.04s]` score=`-42.2875`: *"Từ kỳ thi tốt nghiệp trung học phổ thông 2025..."*
  - `#3` `[L22_V008 72.18s–76.28s]` score=`-40.1626`: *"Theo dự kiến của Bộ giáo dục đào tạo, thời gian tổ chức kỳ thi..."*
- **ASR BGE** (366.7ms, 5 hits):
  - `#1` `[L25_V049 1824.76s–1827.76s]` score=`0.8976`: *"kỳ thi trung học phổ thống quốc gia"*
  - `#2` `[L25_V074 1906.18s–1908.18s]` score=`0.7279`: *"trong đề thi trung học phổ thông quốc gia"*
  - `#3` `[L25_V001 1497.62s–1499.62s]` score=`0.7173`: *"Trong mùa thi Tốt nghiệp trung học của thông quốc gia"*
- *Video Overlap Jaccard*: `0.167`

---

## 5. Milestone Status & Operational Closure

1. **Subsystem Closure**: `M4_ASR_SUBSYSTEM_CLOSED = YES`.
2. **Quality Evaluation**: `M4_ASR_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH` (15 DEV queries, scored = 0, unscored = 15). Candidate diversity (~10% Jaccard) is documented honestly as distinct retrieval behavior rather than unverified quality complementarity.
3. **Next Milestone**: Milestone M4C — OCR Core Retrieval Leg.
