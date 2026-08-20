# M13R Final Release Reconciliation — AIC 2026 Core Workstation
<!-- docs/retrieval_v2/M13_LITE_FINAL_RELEASE_RESULT.md — reconciled 2026-08-20 M13R -->

## Release Identity

| Field | Value |
|---|---|
| Milestone | **M13R (Final Release Reconciliation)** |
| Core Code HEAD | `1bc3be6af9e17bb329b9abfb3a2217a6403fa9de` (`1bc3be6`) |
| Core Final Release HEAD | `HEAD` (current reconciled freeze commit) |
| Frontend HEAD | `28244182970b4512add950949b5a989f785cbc1b` (`2824418`) |
| Freeze Date | 2026-08-20 |
| Preflight | 25/25 PASS |
| Rehearsal Status | **26/26 VERIFIED_EXECUTED (PASS)** |

---

## Release Status Semantics

```
CORE_SOFTWARE_RELEASE_FROZEN                = YES
LOCAL_DEV_RUNTIME_READY                     = YES (39 / 873 videos)
FULL_CORPUS_COMPETITION_DEPLOYMENT_READY    = UNVERIFIED
CORE_COMPETITION_WORKSTATION_READY          = PENDING_DEPLOYMENT
M13_FINAL_ACCEPTANCE                        = SOFTWARE_PASS
```

### Rationale:
- **Software Freeze**: Core code, tests, build, and API/UI interfaces are verified, stable, and frozen.
- **Local Dev Runtime**: Fully operational on the locally available 39-video subset (L21 + L22).
- **Target Deployment**: Unverified in this task because the full 873-video target competition machine was not accessible for direct execution.
- **Workstation Readiness**: Software PASS; full competition-readiness pending deployment verification on the 873-video server.

---

## Regression Verification

| Component | Command | Result |
|---|---|---|
| Core Backend | `.venv\Scripts\python -m pytest -q tests` | **406 passed, 2 skipped** (in 280.29s) |
| Frontend Vitest | `npm test -- --run` | **14 test files passed, 63 tests passed** |
| Frontend Typecheck | `npm run check` (`tsc --noEmit`) | **PASS** (exit code 0) |
| Frontend Production Build | `npm run build` (`vite build && esbuild`) | **PASS** (built in 15.28s, exit code 0) |

---

## Rehearsal Evidence Audit (26/26 VERIFIED_EXECUTED)

All 26 sessions were executed against the live running backend and physical video media. All individual machine-readable files (`single_sessions.jsonl`, `compare_sessions.jsonl`, `sequence_sessions.jsonl`, `inspector_sessions.jsonl`, `failure_sessions.jsonl`, `manifest.json`, `restart.json`, `summary.json`, `DONE`) are preserved in `F:\AIC_WORK\artifacts\retrieval_v2\release_rehearsal\m13_lite_001\`.

### 1. Single Mode Sessions (7/7 VERIFIED_EXECUTED)
| ID | Lane | Query / Config | Result Count | Latency | Execution Status |
|---|---|---|---|---|---|
| S1 | `siglip_custom` | "nguoi dung truoc bien hieu" | 20 | 31.3 s (cold) | **VERIFIED_EXECUTED** |
| S2 | `btc_clip` | "fire truck on highway" | 20 | 22.5 s (cold) | **VERIFIED_EXECUTED** |
| S3 | `siglip_custom` | "waterfall in forest" | 20 | 256.9 ms (warm) | **VERIFIED_EXECUTED** |
| S4 | `asr_bge` | "kinh te" | 20 | 23.2 s (cold) | **VERIFIED_EXECUTED** |
| S5 | `ocr_trigram` | "VNPT" | 0 (degraded on dev) | 1.7 s | **VERIFIED_EXECUTED** |
| S6 | `qwen_bge` | "meeting room presentation projector" | 20 | 9.8 s (cold) | **VERIFIED_EXECUTED** |
| S7 | `btc_objects` | `classes=['person']`, `min_detector_score=0.5` | 20 | 300.3 ms | **VERIFIED_EXECUTED** |

### 2. Compare Mode Sessions (6/6 VERIFIED_EXECUTED)
| ID | Lanes | Query | Per-Lane Counts | Latency | Status |
|---|---|---|---|---|---|
| C1 | `siglip_custom` + `btc_clip` | "xe canh sat" | 20 + 20 | 712.9 ms | **VERIFIED_EXECUTED** |
| C2 | `siglip` + `btc` + `ocr_trigram` | "VNPT" | 20 + 20 + 0 (degraded) | 539.8 ms | **VERIFIED_EXECUTED** |
| C3 | 5 lanes (`siglip`, `btc`, `asr_bge`, `ocr_bge`, `qwen_bge`) | "presentation screen" | 20 + 20 + 20 + 0 + 20 | 38.8 s | **VERIFIED_EXECUTED** |
| C4 | `siglip` + `asr_bm25` (degraded) | "car accident" | 20 + 0 (PARTIAL status) | 2.6 s | **VERIFIED_EXECUTED** |
| C5 | `siglip` + `qwen_structured` | "outdoor scene" (`objects=['car']`, `scenes=['outdoor']`) | 20 + 20 | 4.8 s | **VERIFIED_EXECUTED** |
| C6 | `siglip` + `ocr_bge` + `qwen_bge` | "bao cao ket qua" | 20 + 0 + 20 | 2.0 s | **VERIFIED_EXECUTED** |

### 3. Sequence Mode Sessions (6/6 VERIFIED_EXECUTED)
| ID | Steps | Lanes | Strict | Results / Group | Status |
|---|---|---|---|---|---|
| Q1 | 2 | `btc_clip` → `asr_bm25` | `true` | STEP_ONLY (bm25 degraded) | **VERIFIED_EXECUTED** |
| Q2 | 2 | `siglip` → `siglip` | `true` | FULL / PARTIAL match | **VERIFIED_EXECUTED** |
| Q3 | 3 | `siglip` → `ocr_trigram` → `siglip` | `true` | STEP_ONLY (ocr degraded) | **VERIFIED_EXECUTED** |
| Q4 | 2 | `btc_clip` → `asr_bge` | `false` | Co-occurrence matched (gaps bypassed) | **VERIFIED_EXECUTED** |
| Q5 | 2 | `siglip` → `btc_clip` | `true` | FULL / PARTIAL match | **VERIFIED_EXECUTED** |
| Q6 | 2 | `siglip` → `btc_objects` | `true` | FULL / STEP_ONLY match | **VERIFIED_EXECUTED** |

### 4. Media Inspector Sessions (3/3 VERIFIED_EXECUTED)
| ID | Opened From | Video ID : Frame | Exact JPEG Bytes | Navigation / Stepping | Status |
|---|---|---|---|---|---|
| I1 | `siglip_custom` | `L21_V001:75` | 61,355 bytes | +1 frame (76), +10 frames (85) OK | **VERIFIED_EXECUTED** |
| I2 | `btc_clip` | `L21_V002:100` | 59,929 bytes | Nearest keyframes resolved OK | **VERIFIED_EXECUTED** |
| I3 | Sequence Chain | `L21_V001:200` | 72,327 bytes | Exact source frame decode OK | **VERIFIED_EXECUTED** |

### 5. Failure / Degraded Handling Sessions (4/4 VERIFIED_EXECUTED)
| ID | Test | Expected | Actual Result | Status |
|---|---|---|---|---|
| F1 | Sequence with degraded `asr_bm25` | Graceful HTTP 200 with `PARTIAL`/`STEP_ONLY` | Code 200, no crash | **VERIFIED_EXECUTED** |
| F2 | Compare with degraded `ocr_bm25` | Graceful HTTP 200 with `PARTIAL` status | Code 200, siglip intact | **VERIFIED_EXECUTED** |
| F3 | Backend health probe (`/api/health`) | HTTP 200 with `status=OK` | Code 200, status OK | **VERIFIED_EXECUTED** |
| F4 | Invalid endpoint probe (`/api/v1/invalid-route`) | HTTP 404 structured JSON error | Code 404, server healthy | **VERIFIED_EXECUTED** |

---

## Restart Rehearsal Evidence

| Metric | Value |
|---|---|
| Backend stopped | **True** (PID terminated, port 8765 cleared) |
| Backend restarted | **True** (new PID spawned, `/api/health` returned 200 OK) |
| No index rebuild | **True** (all FAISS / SQLite mtimes unchanged) |
| No artifact rebuild | **True** (static artifact tree preserved) |
| Total restart duration | **< 3 s** |
| Evidence file | `F:\AIC_WORK\artifacts\retrieval_v2\release_rehearsal\m13_lite_001\restart.json` |

---

## Corpus Reality Reconciliation

| Parameter | Value |
|---|---|
| Canonical Corpus Count | **873 videos** (L21–L30) |
| Local Physical Media Count | **39 videos** (L21: 29, L22: 10) |
| Physical Media Root | `F:\KTLT\data_extracted\video` |
| Target Competition Environment | **UNVERIFIED** (host containing 873 physical videos not accessible in this session) |

---

## Operator Runbook Reconciliations

1. **Frontend Framework**: Corrected from "Svelte" to **React 19 + TypeScript + Vite 7 + Tailwind CSS** (matches `package.json`).
2. **Sequence `strict_order=false`**: Clarified that ordered `min_gap`/`max_gap` checks are bypassed; same-video co-occurrence and `max_span` apply.
3. **Qwen Structured Schema**: Reconciled to accepted namespaces (`objects`, `attributes`, `relations`, `counts`, `scene`, `actions`); removed unsupported `activity`/`setting`.
4. **BTC Objects Config**: Documented accepted field names (`classes`, `match_mode`, `min_detector_score`, `top_k`).
5. **Inspector Keyboard Shortcuts**: Corrected to actual code handlers (`← / →` ±1 frame, `Shift + ← / →` ±10 frames, `J / L` ±3s, `Shift + J / L` ±10s; removed `Alt+←/→`).
6. **Submission Scope**: Removed submission/QA instructions; explicitly stated that frozen core ends at exact frame evidence verification.
7. **Compare Execution Model**: Corrected from "parallel" to **SEQUENTIAL** (deterministic lane-by-lane dispatch).
8. **Capabilities Endpoint**: Documented `/api/health` as fast readiness probe and `/api/v1/capabilities` as potentially slow/cold.

---

## Provider Inventory Classification

| Classification | Count | Providers |
|---|---|---|
| **HEALTHY** | 6 | `siglip_custom`, `btc_clip`, `asr_bge`, `qwen_structured`, `qwen_bge`, `btc_objects` |
| **DEGRADED** | 6 | `asr_bm25`, `ocr_bm25`, `media_bm25`, `qwen_bm25`, `ocr_trigram`, `ocr_bge` |
| **UNAVAILABLE** | 0 | None (all providers gracefully handle missing/degraded data) |

---

*Reconciled and recorded for M13R release — 2026-08-20.*
