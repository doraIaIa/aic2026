# AIC 2026 Competition Operator Runbook
<!-- docs/OPERATOR_RUNBOOK.md — frozen 2026-08-20 M13-lite -->

> **This document is the single reference for all competition-day operation.**
> Read once before competition. Print if needed. No code changes during competition.

---

## Quick-Start (3 commands)

```powershell
# Terminal 1 — Backend
cd F:\AIC_DEV\aic2026
.venv\Scripts\python -m aic2026.search.api --host 127.0.0.1 --port 8765

# Terminal 2 — Frontend
cd F:\aic-video-search-demo
npm run dev

# Browser
http://localhost:3000
```

> **⚠ Cold-start warning:** First query after `python -m aic2026.search.api` starts loads GPU models.
> SigLIP + BTC CLIP take ~**49 s** on RTX 3050. The health endpoint responds immediately; only search queries trigger model load.
> **Run a warm-up query before the competition starts.**

---

## 1. Environment Reference

| Item | Value |
|---|---|
| Python | 3.11.9 |
| CUDA | 12.1 |
| GPU | RTX 3050 6GB Laptop |
| ffmpeg | 8.1.1-full_build |
| Backend port | `127.0.0.1:8765` |
| Frontend port | `localhost:3000` |
| Media root | `F:\KTLT\data_extracted\video` |
| Artifact root | `F:\AIC_WORK\artifacts` |
| Backend health | `GET /api/health` → `{"status":"OK"}` |
| Capabilities | `GET /api/v1/capabilities` (slow — triggers model load) |

---

## 2. Preflight (run before each session)

```powershell
cd F:\AIC_DEV\aic2026
$env:PYTHONUTF8=1
.venv\Scripts\python "F:\AIC_WORK\artifacts\retrieval_v2\m13_preflight.py"
```

Expected: `Overall: PASS  FAIL: 0  WARN: 0  PASS: 25`

If any check FAILs, see §8 Troubleshooting before starting.

---

## 3. Lane Reference

### 3.1 Visual Lanes

| Lane ID | Model | Frame Space | Query Type |
|---|---|---|---|
| `siglip_custom` | SigLIP2-base-patch16-224 | CUSTOM (116,767 kf) | Natural language / visual description |
| `btc_clip` | ViT-B-32 (open-clip) | BTC (177,321 kf) | Natural language / visual description |

**Use for:** Any query describing what is visible on screen.

### 3.2 Speech (ASR) Lanes

| Lane ID | Model | Frame Space | Query Type |
|---|---|---|---|
| `asr_bge` | BAAI/bge-m3 | SOURCE (segments) | Spoken words / speech content |
| `asr_bm25` | BM25 | SOURCE | Exact spoken keywords (**DEGRADED** on dev machine) |

**Use for:** Queries about what is being said, spoken announcements, names mentioned.

### 3.3 OCR Lanes

| Lane ID | Model | Frame Space | Query Type |
|---|---|---|---|
| `ocr_trigram` | Trigram FTS | CUSTOM | On-screen text (brand, sign, label) |
| `ocr_bge` | BAAI/bge-m3 | CUSTOM | On-screen text — semantic |
| `ocr_bm25` | BM25 | CUSTOM | Exact on-screen keywords (**DEGRADED** on dev machine) |

**Use for:** Queries about visible text (signs, banners, titles, subtitles).

> **Note:** `ocr_trigram` may return EMPTY for very short queries (1–2 chars). This is expected.

### 3.4 Qwen Caption Lanes

| Lane ID | Model | Frame Space | Query Type |
|---|---|---|---|
| `qwen_structured` | Structured rank | CUSTOM | JSON config: `objects`, `scene`, `activity`, `setting` |
| `qwen_bge` | BAAI/bge-large-en-v1.5 | CUSTOM | Dense semantic over VL captions |
| `qwen_bm25` | BM25 | CUSTOM | Keyword match over VL captions (**may return EMPTY** for natural language) |

**Use for:** Compositional queries, queries about scene understanding, activity, setting.

**Qwen Structured config example:**
```json
{
  "objects": ["person", "microphone"],
  "scene": "press conference",
  "activity": "speaking",
  "setting": "indoor"
}
```

### 3.5 Object Detection Lane

| Lane ID | Frame Space | Query Type |
|---|---|---|
| `btc_objects` | BTC | Structured: `classes` list + confidence threshold |

**BTC Object classes** (examples): `person`, `car`, `motorcycle`, `truck`, `bus`, `bicycle`, `traffic light`, `fire hydrant`, `stop sign`, `chair`, `tv`, `laptop`, `cell phone`, `book`, `bottle`.

**Config example:**
```json
{"classes": ["person", "car"], "threshold": 0.5}
```

---

## 4. Query Strategies

### 4.1 Single Mode — Decision Tree

```
Query type?
├── Visual description ("người đứng trước biển hiệu", "fire truck on road")
│   ├── → siglip_custom  (best for natural language)
│   └── → btc_clip       (use if siglip gives poor results)
├── Spoken content ("ông ấy nói về kinh tế", "emergency broadcast")
│   └── → asr_bge
├── On-screen text ("VNPT", "Thủ tướng", "Brand logo")
│   ├── → ocr_trigram    (fast, exact)
│   └── → ocr_bge        (semantic)
├── Scene/Activity ("press conference", "outdoor market at night")
│   └── → qwen_bge  or  qwen_structured
└── Object detection ("find frames with person + car")
    └── → btc_objects
```

### 4.2 Compare Mode — Recommended Pairs

| Scenario | Lanes to compare |
|---|---|
| Visual query, want confidence | `siglip_custom` vs `btc_clip` |
| Text on screen + visual | `ocr_trigram` vs `siglip_custom` |
| ASR + visual | `asr_bge` vs `siglip_custom` |
| Full evidence sweep | `siglip_custom` + `btc_clip` + `asr_bge` + `ocr_bge` + `qwen_bge` |

### 4.3 Sequence Mode — Key Rules

1. Each step is **one lane + one query**.
2. `strict_order = ON` → steps must occur in temporal order in the same video.
3. `strict_order = OFF` → steps just need to co-occur in same video within gap window.
4. `min_gap_sec` / `max_gap_sec` controls the time window between steps.
5. Result types: `FULL` (all steps matched), `PARTIAL` (some steps matched), `STEP_ONLY` (only 1 step matched, other lane DEGRADED).
6. Click any result to open Inspector and verify exact frames.

**Typical 2-step sequence config:**
- Step 1: `siglip_custom`, query = visual anchor
- Step 2: `siglip_custom` or `asr_bge`, query = temporal target
- Gap: `min=0, max=60`, `strict_order=ON`

---

## 5. Inspector Usage

The Inspector opens when you click any search result card.

### Panel layout:

| Section | Content |
|---|---|
| Top-left | Source video ID, video filename |
| Center | **Exact source frame** JPEG (physical decode from H.264) |
| Right-top | Nearest CUSTOM keyframe (SigLIP keyframe universe) |
| Right-bottom | Nearest BTC keyframe (BTC-provided keyframe universe) |

### Navigation:

| Key / Button | Action |
|---|---|
| ← → arrows | ±1 frame |
| Shift + ← → | ±10 frames |
| Alt + ← → | ±1 second |
| Click timeline | Jump to timestamp |
| Submit / QA button | Submit frame as answer |

> **Authority:** The center exact-frame JPEG is the physical source frame authority.
> Nearest-keyframe panels are for cross-reference. Always submit from the source frame.

---

## 6. Submitting Answers

**KIS (Known Item Search — Single answer):**
1. Search → find correct video/frame
2. Open Inspector
3. Verify exact frame
4. Click **Submit** button

**QA (Question Answering):**
1. Find correct video segment
2. In Inspector, navigate to the specific frame range
3. Enter text answer in the QA field
4. Click **Submit QA**

---

## 7. Warm-Up Checklist (run before competition)

```
[ ] preflight passes (25/25)
[ ] backend health: curl http://127.0.0.1:8765/api/health → {"status":"OK"}
[ ] run warm-up query: siglip_custom "người đứng" → see results appear
[ ] run warm-up query: btc_clip "person at podium" → see results appear
[ ] Inspector opens from first result, exact frame loads
[ ] Sequence mode: 2-step test query completes
[ ] Compare mode: 2-lane test query shows per-lane columns
```

---

## 8. Troubleshooting

### Backend won't start
```
Error: address already in use → kill existing python process:
  Get-Process python | Stop-Process
  .venv\Scripts\python -m aic2026.search.api --host 127.0.0.1 --port 8765
```

### No GPU detected
```
Symptom: "gpu WARN CUDA not available"
Action: Check nvidia-smi, restart GPU driver, verify CUDA 12.1 installed
Fallback: System runs on CPU (much slower ~5-10× per query)
```

### Exact frame doesn't load
```
Symptom: Inspector shows placeholder/error instead of JPEG
Check: F:\KTLT\data_extracted\video\ has the video file
Check: ffmpeg is on PATH (ffmpeg --version)
Check: video_id matches a file in media root
```

### Lane returns EMPTY
```
This is EXPECTED for:
  - ocr_trigram on very short queries
  - qwen_bm25 on natural language queries
  - asr_bm25 on this dev machine (artifact missing)
Action: switch to semantic lane (ocr_bge, qwen_bge, asr_bge)
```

### Slow first query
```
Expected: ~49s for first siglip/btc_clip query (GPU model load)
Expected: ~2-5s for first asr_bge/ocr_bge/qwen_bge query
Subsequent: <2s
Action: Run warm-up query before competition starts
```

### Compare mode — one lane blank
```
Expected if that lane is DEGRADED or returns EMPTY
Other lanes still show results independently
No action needed
```

### Sequence returns STEP_ONLY
```
Means: one step lane was DEGRADED, results from functional step shown
Action: switch degraded step to a working lane (asr_bge instead of asr_bm25)
```

---

## 9. Do NOT During Competition

- Do **NOT** restart the backend mid-query (causes active request to fail)
- Do **NOT** run `pip install`, `npm install`, or any build commands
- Do **NOT** modify any source files
- Do **NOT** rebuild any FAISS indexes
- Do **NOT** change `MEDIA_ROOT` or any config path
- Do **NOT** run the backend on a public port (keep `--host 127.0.0.1`)

---

## 10. Emergency Restart

If backend crashes:
```powershell
cd F:\AIC_DEV\aic2026
.venv\Scripts\python -m aic2026.search.api --host 127.0.0.1 --port 8765
# Wait ~3s for health endpoint to respond
# Run warm-up query to pre-load models (~49s)
```

If frontend crashes:
```powershell
cd F:\aic-video-search-demo
npm run dev
```

No state to recover — all indexes are persistent files. Restart is clean.

---

## 11. File Locations Reference

| Path | Description |
|---|---|
| `F:\AIC_DEV\aic2026\` | Core backend (Python) |
| `F:\aic-video-search-demo\` | Frontend (Svelte) |
| `F:\KTLT\data_extracted\video\` | Video files (39 local, 873 full) |
| `F:\AIC_WORK\artifacts\retrieval_v2\siglip_custom_v1\` | SigLIP FAISS index |
| `F:\AIC_WORK\artifacts\canonical_btc_v1\` | BTC CLIP FAISS index |
| `F:\AIC_WORK\artifacts\retrieval_v2\asr_bge_v1\` | ASR BGE FAISS index |
| `F:\AIC_WORK\artifacts\retrieval_v2\ocr_trigram_v1\` | OCR Trigram SQLite DB |
| `F:\AIC_WORK\artifacts\retrieval_v2\ocr_bge_v1\` | OCR BGE FAISS index |
| `F:\AIC_WORK\artifacts\retrieval_v2\qwen_structured_v1\` | Qwen structured SQLite DB |
| `F:\AIC_WORK\artifacts\retrieval_v2\qwen_bge_v1\` | Qwen BGE FAISS index |
| `F:\AIC_WORK\artifacts\retrieval_v2\btc_objects_v1\` | BTC Object detection DB |
| `F:\AIC_WORK\artifacts\retrieval_v2\release_freeze\AIC2026_CORE_RELEASE_V1.json` | Release manifest |
| `F:\AIC_WORK\artifacts\retrieval_v2\m13_preflight.py` | Preflight inspector |

---

*Document frozen at M13-lite. Do not modify without explicit milestone update.*
