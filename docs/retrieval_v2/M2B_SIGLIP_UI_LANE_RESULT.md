# Milestone M2B — SigLIP Standalone UI + Operational Lane Closure Acceptance Report

## 1. Executive Summary & Verification Verdict

**M2B_ACCEPTANCE = PASS**  
**M2_LANE_OPERATIONAL_STATUS = CLOSED_OPERATIONALLY**  
**SIGLIP_QUALITY_BENCHMARK_STATUS = BLOCKED_BY_GROUND_TRUTH**

The M2A SigLIP2 visual retrieval backend is now fully exposed as a first-class, standalone **Single Lane** mode in the React retrieval workspace (`aic-video-search-demo`). The complete operator workflow (query input → raw SigLIP search → CUSTOM candidate cards → source video seek → exact-frame verification → candidate building) is operational and verified end-to-end.

> [!IMPORTANT]
> **Quality Benchmark Invariant:** M2 closes the SigLIP lane **OPERATIONALLY**. In M2A benchmark, 15 DEV queries executed with 0 scored / 15 unscored due to pending human ground truth. No claim of Recall/precision quality validation is made; operational readiness is 100% verified.

- **Standalone Mode Selection:** The operator can explicitly switch between `Auto`, `Manual`, and `SigLIP` (Single Lane).
- **Verbatim Query Transmission:** Query text is transmitted 100% unchanged to `POST /api/v1/lanes/siglip/search` (no client-side rewrite, translation, prompt injection, or hidden synonyms).
- **Clear Badging & Labeling:** Result cards prominently show `SIGLIP` and `CUSTOM` space badges. Scores are strictly labeled **`Raw score`** / **`Similarity`** (e.g., `0.1885`), never misrepresented as "confidence".
- **Exact-Frame Authority:** Clicking any SigLIP candidate seamlessly populates the `EvidenceInspector`. The real source video player seeks to the candidate timestamp, and physical stepping (`±1f`, `±10f`) operates on the authoritative source video stream.
- **Candidate Builder & Workspace Panel:** Operators can confirm and create KIS/QA/TRAKE candidates directly from inspected SigLIP hits with zero namespace leakage.
- **Frontend & Backend Test Pass Rate:**
  - Frontend (`vitest`): **24 / 24 passed** (6 test suites).
  - Frontend (`tsc --noEmit`): **Clean (0 errors)**.
  - Frontend (`vite build`): **Production bundle compiled successfully**.
  - Backend (`pytest`): **258 / 258 passed in 43.74s**.

---

## 2. Git Identity & Audit Provenance

| Parameter | Value |
| :--- | :--- |
| **Repository (Core)** | AIC 2026 (`F:\AIC_DEV\aic2026`) |
| **Repository (Frontend)** | AIC Video Search Demo (`F:\aic-video-search-demo`) |
| **Milestone** | M2 — Custom SigLIP2 Lane |
| **Slice** | M2B — SigLIP Standalone UI + Operational Lane Closure |
| **Backend Starting HEAD** | `a60d6a698ca97032b96b4743f5bc1fd620b28e73` |
| **Backend Commit** | `feat(ui): add siglip single-lane search` |
| **Frontend Commit** | `2719fd691fed02b86a4cec50cc1247e454cba167` |
| **M2A Core Report Ref** | `docs/retrieval_v2/M2A_SIGLIP_CORE_LANE_RESULT.md` |
| **Index Artifact** | `F:\AIC_WORK\artifacts\retrieval_v2\siglip_custom_v1\` (116,767 vectors, 768D) |

---

## 3. UI Architecture & Operational Invariants

### 3.1 Mode Selection & Control Rail (`LaneControls.tsx`)
- **Strategy Selector:** Provides three distinct operational modes: `Auto`, `Manual`, and `SigLIP`.
- **SigLIP Active Card:** When `SigLIP` mode is selected:
  - Multi-lane checkboxes are replaced with a dedicated `SigLIP · CUSTOM` card.
  - Displays live health status (`OK` / `UNAVAILABLE` / `ERROR`).
  - Displays engine metadata: Model `google/siglip2-base-patch16-224`, FAISS `IndexFlatIP (116,767 rows)`, Metric `INNER_PRODUCT`.
  - Explains lane isolation: Only SigLIP2 runs; no visual/ASR fusion or secondary lanes are invoked.

### 3.2 Result Cards (`EvidenceResults.tsx`)
- **Visual Badges:** Each card displays `SIGLIP` and `CUSTOM` badges to indicate model and keyframe space provenance.
- **Score Representation:** Displays `Raw score: <value>` (e.g. `0.1885`), explicitly formatted with 4 decimal places. Never displayed as percentage or "confidence".
- **Metadata Display:** Shows `video_id`, timecode range (`start_sec`–`end_sec`), anchor time, and `frame_idx`.
- **Card Selection:** Clicking any card selects the candidate window and automatically focuses the Evidence Inspector.

### 3.3 Exact-Frame Inspection (`EvidenceInspector.tsx`)
- **Video Player Seek:** Automatically initializes and seeks the HTML5 video element (`/api/v1/media/<video_id>/stream`) to the candidate timestamp (`anchor_sec`).
- **Exact-Frame Stepping:** `FrameControls` query `/api/v1/media/<video_id>/resolve-frame` with `±1` / `±10` frame offsets. The decoded competition frame ID is displayed for submission verification.
- **Submission Gate:** Checks that media is loaded and verified before allowing candidate submission.

---

## 4. End-to-End Smoke Query Verification

All smoke queries were executed through the real API flow against the 116,767 CUSTOM keyframes index:

| # | Query Text | Query Type | Latency (ms) | Top-1 Matched Video | Keyframe UID & Space | Score / Similarity | Exact Seek Verification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `múa lân` | Cultural event / visual | 436.4 | `L24_V037` | `CUSTOM:L24_V037:F6425` | `0.1885` | Seeks to `214.17s`, Frame `6425` |
| 2 | `người đi xe đạp trên đường` | Action + object scene | 436.4 | `L27_V015` | `CUSTOM:L27_V015:F5078` | `0.1627` | Seeks to `203.12s`, Frame `5078` |
| 3 | `một món ăn trong tô hoặc đĩa` | Object / food scene | 429.7 | `L26_V420` | `CUSTOM:L26_V420:F7128` | `0.1424` | Seeks to `285.12s`, Frame `7128` |
| 4 | `L99_V999` (Invalid scope) | Scope isolation test | 0.8 | `None` | `None` | `N/A` | Returned `0` hits cleanly |
| 5 | Non-existent path | Error state test | 0.5 | `None` | `None` | `N/A` | Status reported as `UNAVAILABLE` |

---

## 5. Verification Test Suite Summary

### 5.1 Frontend Unit & Integration Tests (`F:\aic-video-search-demo`)
```
 RUN  v2.1.9 F:/aic-video-search-demo

 ✓ client/src/retrieval/session.test.ts (5 tests)
 ✓ client/src/retrieval/api.test.ts (4 tests)
 ✓ client/src/retrieval/components/EvidenceInspector.test.tsx (7 tests)
 ✓ client/src/retrieval/components/EvidenceResults.test.tsx (1 test)
 ✓ client/src/retrieval/components/SiglipLane.test.tsx (4 tests)
 ✓ client/src/retrieval/components/rendering.test.tsx (3 tests)

 Test Files  6 passed (6)
      Tests  24 passed (24)
```

### 5.2 Frontend TypeScript Check (`tsc --noEmit`)
```
> tsc --noEmit
(Clean — 0 type errors)
```

### 5.3 Frontend Production Build (`vite build`)
```
✓ 1637 modules transformed.
../dist/public/index.html                 367.78 kB │ gzip: 105.59 kB
../dist/public/assets/index-B2EIzdPC.css  171.99 kB │ gzip:  31.16 kB
../dist/public/assets/index-DqP2veMv.js   401.10 kB │ gzip: 117.50 kB
✓ built in 11.02s
```

### 5.4 Backend Test Suite (`F:\AIC_DEV\aic2026`)
```
.......................................... [100%]
258 passed in 43.74s
```

---

## 6. Milestone Conclusion & Next Step Gate

With the completion of M2B:
1. **The Custom SigLIP2 Lane is OPERATIONALLY CLOSED.**
2. The operator has full visibility into SigLIP retrieval, score provenance, and source video frame inspection.
3. The codebase is fully prepared for future milestone lanes (BTC CLIP, ASR expansion, OCR, Qwen, Compare, and Query Brain fusion).

**M2_LANE_STATUS = CLOSED_OPERATIONALLY**  
**M3_MULTIMODAL_EXPANSION_READY = YES**
