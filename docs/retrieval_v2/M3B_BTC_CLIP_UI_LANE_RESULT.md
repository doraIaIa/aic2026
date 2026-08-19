# Milestone M3B — BTC CLIP Standalone UI + M3 Operational Closure Acceptance Report

## 1. Executive Summary & Final Verdict

**M3_IMPLEMENTATION_ACCEPTANCE = PASS**  
**M3_OPERATIONAL_ACCEPTANCE = PASS**  
**M3_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH**  
**M3_LANE_CLOSED = YES**  
**M4_READY = YES**

Milestone M3 (BTC CLIP Independent Retrieval Lane) is hereby **OPERATIONALLY CLOSED**. The BTC CLIP visual retrieval provider is fully integrated both in the core retrieval engine (M3A) and in the Signal Room operator UI (M3B).

> [!IMPORTANT]
> **Quality Evaluation Invariant:** Milestone M3 is closed **OPERATIONALLY**. Quality evaluation on the 15 DEV benchmark queries remains `scored = 0` and `unscored = 15` pending human ground truth labeling. No fabricated precision/recall claims are made; candidate diversity metrics are reported strictly as **CANDIDATE OVERLAP / DIVERSITY**.

---

## 2. Authoritative Git Identity & Lineage

| Parameter | Core / Backend Repository | Frontend Repository |
| :--- | :--- | :--- |
| **Path** | `F:\AIC_DEV\aic2026` | `F:\aic-video-search-demo` |
| **Target Milestone** | M3A (Engine + Benchmarks) & M3B (Closure) | M3B (Standalone UI Mode) |
| **Active Branch** | `main` | `main` |
| **M3A Backend HEAD** | `fefa758af9608dc0e51a8e221083b72f13de6289` | — |
| **M3B Frontend Commit** | — | `cead8c54618fb5f8575eddb09e30336ccf0e3b6b` |
| **Frontend Commit Msg** | — | `feat(ui): add btc clip single-lane search` |
| **M3 Final Backend Commit**| `53943052d2860a2aef38f6779b44e07d909e0c9c` | — |

---

## 3. UI Capabilities & Single-Lane Mode Features

### 3.1 Four-Way Strategy Control
The operator panel provides an explicit strategy selector:
- **`Auto`**: Multi-lane retrieval executed via rule planner v1.
- **`Manual`**: Selective multi-lane retrieval.
- **`SigLIP`**: Standalone SigLIP2 single lane search (116,767 CUSTOM keyframes).
- **`BTC CLIP`**: Standalone OpenCLIP ViT-B-32 single lane search (177,321 BTC keyframes).

### 3.2 BTC CLIP Single-Lane Panel
When `BTC CLIP` mode is active:
- **Badge Group**: Displays `BTC CLIP` brand badge, `BTC` space pill, and live health status dot.
- **Model Metadata**: Explicitly surfaces `OpenCLIP ViT-B-32/openai`, `FAISS IndexIDMap2(IndexFlatIP) (177,321 rows)`, and `INNER_PRODUCT / Cosine`.
- **Query Integrity**: Natural language queries are passed untouched to `POST /api/v1/lanes/btc-clip/search` without rewriting or translation.
- **Scope Control**: Operators can restrict search to all videos or an explicit candidate video set.

### 3.3 Evidence Result Cards & Inspector Drilldown
- **Canonical Badges**: Results display `#Rank`, `BTC CLIP` badge, `BTC` space pill, `video_id`, and `timecode`.
- **Keyframe Thumbnails**: Loaded dynamically from canonical BTC keyframe paths via `keyframeUrl(video_id, csv_n)`.
- **Exact Frame Authority**: Displays `BTC KEYFRAME CANDIDATE`, timestamp, `frame_idx`, and ordinal `n`.
- **Score Integrity**: Score is explicitly labeled **`Raw score`** (never "confidence").
- **Exact Frame Inspector**: Clicking any result opens the MediaResolver inspector, loads video playback, and allows exact frame verification.

---

## 4. End-to-End Verification & Health Summary

### 4.1 Live API Verification
```json
{
  "lane_id": "btc_clip",
  "status": "OK",
  "model_loaded": true,
  "tokenizer_loaded": true,
  "index_loaded": true,
  "index_id": "clip-faiss-btc-v1",
  "index_rows": 177321,
  "metadata_rows": 177321,
  "dimension": 512,
  "frame_space": "BTC",
  "model_name": "ViT-B-32",
  "pretrained": "openai",
  "device": "cpu",
  "index_checksum": "08ed3cdbe250401560d04a4a26f9958c92672739141b664c5c59b75bfcfac0b3",
  "metadata_checksum": "ced15059a07c74f69a02f008aae92be09dfec56f9913db4bf0cb2e75bdb53c2e",
  "metric": "cosine_via_normalized_inner_product"
}
```

### 4.2 Query Verification
Query: `"múa lân"`
- Status: `OK`
- Elapsed: `806.29 ms`
- Count: `5` hits
- Top-1: `L29_V018` (`BTC:L29_V018:KF000438`), Raw Score: `0.3012`, Timestamp: `783.0s`, Frame: `19575`, Ordinal `n`: `438`.

---

## 5. Test Suite Verification

### 5.1 Frontend Test Suite (`F:\aic-video-search-demo`)
- **Vitest**: **28 passed in 1.01s** (7 test suites, including `BtcClipLane.test.tsx` and `SiglipLane.test.tsx`).
- **Typecheck**: `tsc --noEmit` clean (0 errors).
- **Production Build**: `vite build && esbuild` passed with 0 errors.

### 5.2 Backend Test Suite (`F:\AIC_DEV\aic2026`)
- **Pytest**: **266 passed in 64.84s** (100% pass rate).

---

## 6. Milestone Closure Declaration

```
M3 BTC CLIP RETRIEVAL LANE OPERATIONALLY CLOSED

M3_IMPLEMENTATION_ACCEPTANCE: PASS
M3_OPERATIONAL_ACCEPTANCE: PASS
M3_QUALITY_EVAL_STATUS: BLOCKED_BY_GROUND_TRUTH
M3_LANE_CLOSED: YES
M4_READY: YES

Backend HEAD: fefa758af9608dc0e51a8e221083b72f13de6289
Frontend HEAD: cead8c54618fb5f8575eddb09e30336ccf0e3b6b

NEXT MILESTONE:
M4 — ASR Semantic & Transcript Retrieval Lane
```
