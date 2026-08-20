# AIC 2026 Competition Operator Runbook
<!-- docs/OPERATOR_RUNBOOK.md — reconciled 2026-08-20 M13R -->

> **This document is the authoritative reference for all competition-day operation.**
> Read once before competition. No code changes during competition.

---

## Quick-Start (3 commands)

```powershell
# Terminal 1 — Backend (Python / FastAPI-style HTTP server)
cd F:\AIC_DEV\aic2026
.venv\Scripts\python -m aic2026.search.api --host 127.0.0.1 --port 8765

# Terminal 2 — Frontend (React 19 + Vite 7 + Tailwind CSS)
cd F:\aic-video-search-demo
npm run dev

# Browser
http://localhost:3000
```

> **⚠ Cold-start warning:** First visual query after backend starts loads GPU models.
> SigLIP + BTC CLIP take ~**30–49 s** cold on RTX 3050. The readiness probe `GET /api/health` responds immediately.
> `GET /api/v1/capabilities` may also be slow on cold start as it probes model availability.
> **Run a warm-up query before the competition session starts.**

---

## 1. Environment Reference

| Item | Value |
|---|---|
| Python | 3.11.9 |
| CUDA | 12.1 |
| GPU | NVIDIA GeForce RTX 3050 6GB Laptop GPU |
| ffmpeg / ffprobe | 8.1.1-full_build |
| Backend port | `127.0.0.1:8765` |
| Frontend port | `localhost:3000` (Vite dev server) |
| Frontend stack | **React 19 + TypeScript + Vite 7 + Tailwind CSS** |
| Media root | `F:\KTLT\data_extracted\video` (39 local dev / 873 competition) |
| Artifact root | `F:\AIC_WORK\artifacts` |
| Health probe | `GET /api/health` → `{"status":"OK"}` (fast readiness probe) |
| Capabilities probe | `GET /api/v1/capabilities` (slow — may trigger cold provider check) |

---

## 2. Preflight (run before each session)

```powershell
cd F:\AIC_DEV\aic2026
$env:PYTHONUTF8=1
.venv\Scripts\python "F:\AIC_WORK\artifacts\retrieval_v2\m13_preflight.py"
```

Expected: `Overall: PASS  FAIL: 0  WARN: 0  PASS: 25`

If any check FAILs, see §8 Troubleshooting before starting.

> **Target machine deployment:** Ensure `m13_preflight.py` and artifact folders are copied to the target competition workstation at matching paths or configured via environment variables.

---

## 3. Lane Reference & Provider Classifications

### 3.1 Visual Lanes

| Lane ID | Model | Frame Space | Query Type | Classification |
|---|---|---|---|---|
| `siglip_custom` | SigLIP2-base-patch16-224 | CUSTOM (116,767 kf) | Natural language / visual description | **HEALTHY** |
| `btc_clip` | ViT-B-32 (open-clip) | BTC (177,321 kf) | Natural language / visual description | **HEALTHY** |

**Use for:** Any query describing visual elements visible on screen.

### 3.2 Speech (ASR) Lanes

| Lane ID | Model | Frame Space | Query Type | Classification |
|---|---|---|---|---|
| `asr_bge` | BAAI/bge-m3 | SOURCE (segments) | Spoken content / semantic speech | **HEALTHY** |
| `asr_bm25` | BM25 (SQLite FTS5) | SOURCE (segments) | Exact spoken keywords | **DEGRADED on dev** |

**Use for:** Queries about speech, announcements, spoken names.

### 3.3 OCR Lanes

| Lane ID | Model | Frame Space | Query Type | Classification |
|---|---|---|---|---|
| `ocr_trigram` | Character 3-gram FTS | CUSTOM | On-screen text (typo-tolerant) | **DEGRADED on dev** (missing `ocr_items`) |
| `ocr_bge` | BAAI/bge-m3 | CUSTOM | On-screen text — semantic | **DEGRADED on dev** (missing `ocr_items`) |
| `ocr_bm25` | BM25 (SQLite FTS5) | CUSTOM | Exact on-screen keywords | **DEGRADED on dev** |

**Use for:** On-screen text, brand names, signage, titles, subtitles.

### 3.4 Qwen Caption Lanes

| Lane ID | Model | Frame Space | Query Type | Classification |
|---|---|---|---|---|
| `qwen_structured` | Structured Facet Rank | CUSTOM | Structured JSON facets | **HEALTHY** |
| `qwen_bge` | BAAI/bge-large-en-v1.5 | CUSTOM | Dense semantic over VL captions | **HEALTHY** |
| `qwen_bm25` | BM25 (SQLite FTS5) | CUSTOM | Lexical keyword over VL captions | **DEGRADED on dev** |

**Use for:** Scene understanding, complex compositions, multi-attribute queries.

**Qwen Structured accepted schema:**
```json
{
  "objects": ["person", "microphone"],
  "attributes": ["formal suit"],
  "relations": ["standing at"],
  "scene": "press conference",
  "actions": ["speaking", "announcing"],
  "counts": ["one person"]
}
```

### 3.5 Object Detection Lane

| Lane ID | Frame Space | Query Type | Classification |
|---|---|---|---|
| `btc_objects` | BTC (177,321 kf) | Structured detector classes | **HEALTHY** |

**Accepted fields:**
- `classes`: list of class names (e.g. `["person", "car"]`)
- `match_mode`: `"ALL"` or `"ANY"` (default: `"ALL"`)
- `min_detector_score`: float 0.0 to 1.0 (default: `0.1`)
- `top_k`: integer (default: `50`)

**Config example:**
```json
{
  "classes": ["person", "car"],
  "match_mode": "ALL",
  "min_detector_score": 0.5,
  "top_k": 20
}
```

---

## 4. Query Modes & Execution Semantics

### 4.1 Single Mode

Executes a single retrieval lane independently.
- Operator selects lane and types query text or structured config.
- Results displayed as ranked candidate cards with thumbnails, timestamps, and video IDs.

### 4.2 Compare Mode

Executes multiple selected lanes for the same query.
- **Execution model:** `SEQUENTIAL` (lanes dispatched in deterministic sequence with partial-failure isolation).
- Results displayed in side-by-side per-lane columns.
- **No cross-lane fusion or score normalization** is performed.

### 4.3 Sequence Mode (Temporal Reasoning)

Executes multi-step temporal sequence retrieval across independent temporal-capable lanes.
- Each step defines one lane and query/options.
- **`strict_order = true`:**
  - Steps must appear in strictly ascending temporal order in the same video.
  - Consecutive gap must satisfy `min_gap_ms <= (start_next - end_prev) <= max_gap_ms`.
  - Total span must satisfy `total_span <= max_span_ms` (if configured).
- **`strict_order = false`:**
  - Ordered gap constraints are **bypassed**.
  - Steps must co-occur in the same video, constrained only by `max_span_ms` (if specified).
- **Result groups:** `FULL_MATCH` (all steps matched), `PARTIAL_MATCH` / `STEP_ONLY_MATCH` (subset matched or degraded step isolated).

---

## 5. Media Inspector & Physical Frame Authority

The Inspector panel opens when any result card is clicked.

### Panel layout:
- **Left / Center:** Exact source frame JPEG (decoded on-demand from physical H.264 video via ffmpeg) + HTML5 video player.
- **Right top:** Nearest CUSTOM keyframe (from SigLIP universe).
- **Right bottom:** Nearest BTC keyframe (from BTC universe).
- **Metadata:** Canonical video ID, timestamp PTS, FPS, total frame count.

### Keyboard Shortcuts (Physical Frame Navigation):

| Key | Action |
|---|---|
| `←` / `→` | **±1 SOURCE frame** (`delta: -1 / +1`) |
| `Shift + ←` / `Shift + →` | **±10 SOURCE frames** (`delta: -10 / +10`) |
| `J` / `L` | **-3 s / +3 s** time jump |
| `Shift + J` / `Shift + L` | **-10 s / +10 s** time jump |

> **Authority Statement:** The center exact-frame JPEG is the physical source frame authority (PSNR=inf against source decode). Nearest-keyframe panels provide cross-universe alignment only.

---

## 6. Scope of Release & Answer Verification

> [!IMPORTANT]
> **Scope Notice:** The current frozen core release ends at **exact frame and answer evidence verification** in the Media Inspector.
> Official competition submission API integration / automated submission export is **outside the scope** of this release.
> The Inspector provides a copy button (`Copy`) to copy the verified video ID, timecode, and evidence ID to the clipboard for manual submission.

---

## 7. Warm-Up Checklist (run before competition)

```
[ ] Preflight passes: .venv\Scripts\python F:\AIC_WORK\artifacts\retrieval_v2\m13_preflight.py
[ ] Backend health probe: curl http://127.0.0.1:8765/api/health -> {"status":"OK"}
[ ] Run warm-up visual query: siglip_custom "nguoi dung" (pre-loads GPU weights)
[ ] Run warm-up visual query: btc_clip "person at podium"
[ ] Open Inspector from first result card, confirm exact JPEG frame loads
[ ] Test frame stepping: press Right arrow (+1 frame), Shift+Right (+10 frames)
[ ] Run test sequence query (2 steps)
[ ] Run test compare query (2 lanes)
```

---

## 8. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Backend fails to start (port in use) | Previous python process holding port 8765 | `Get-Process python \| Stop-Process -Force` then restart backend |
| Slow first query (~30–49 s) | PyTorch / HF model weights loading to CUDA | Expected on first query; subsequent queries are fast (<1 s) |
| Exact frame JPEG fails to load | Video file not present in media root | Check `F:\KTLT\data_extracted\video\<video_id>.mp4` exists |
| Lane returns EMPTY | Query terms absent in vocabulary / short query | Expected behavior; try alternative synonyms or semantic lane |
| Lane returns DEGRADED / 500 | FTS table or mapping DB absent on dev machine | Use healthy dense lanes (`siglip_custom`, `btc_clip`, `asr_bge`, `qwen_bge`) |
| Sequence returns `STEP_ONLY` | One step lane was degraded | Change degraded step to a healthy lane |

---

## 9. Emergency Restart

If backend crashes:
```powershell
cd F:\AIC_DEV\aic2026
.venv\Scripts\python -m aic2026.search.api --host 127.0.0.1 --port 8765
```

If frontend crashes:
```powershell
cd F:\aic-video-search-demo
npm run dev
```

All indexes and databases are static, persistent files on disk. Restart is instantaneous and requires **zero index rebuild**.

---

*Document reconciled and frozen for M13R release — 2026-08-20.*
