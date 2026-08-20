# M13-lite Final Result — AIC 2026 Core Workstation Release
<!-- docs/retrieval_v2/M13_LITE_FINAL_RELEASE_RESULT.md — frozen 2026-08-20 -->

## Release Identity

| Field | Value |
|---|---|
| Milestone | **M13-lite** |
| Status | **PASS** |
| Core git | `1bc3be6` |
| Frontend git | `2824418` |
| Freeze date | 2026-08-20 |
| Preflight | 25/25 PASS |
| Rehearsal | 26/26 PASS |

---

## Milestone Chain

```
M0  Baseline freeze                   CLOSED
M1  Universe registry                  CLOSED
M2  SigLIP lane                        CLOSED
M3  BTC CLIP lane                      CLOSED
M4  ASR / OCR / Media lanes            CLOSED
M5  Qwen + Object lanes                CLOSED
M6  Compare mode                       CLOSED
M7  Manual Sequence mode               PASS
M7R Temporal audit                     PASS
M9  Media Inspector hardening          PASS
M9F Authority fix (source frame)       PASS
M9G Real-source closure (PSNR=inf)     PASS
──────────────────────────────────────────
M13-lite  Final hardening / rehearsal  PASS ← THIS DOCUMENT
```

---

## Acceptance Statement

```
M13_LITE_ACCEPTANCE                  = PASS
CORE_COMPETITION_WORKSTATION_READY   = YES
CORE_RELEASE_FROZEN                  = YES
```

The AIC 2026 Core Retrieval Workstation is **competition-ready** at git `1bc3be6` / frontend `2824418`.

---

## Evidence

### Preflight (25/25 PASS)
Script: [`m13_preflight.py`](file:///F:/AIC_WORK/artifacts/retrieval_v2/m13_preflight.py)
Report: `F:\AIC_WORK\artifacts\retrieval_v2\release_rehearsal\m13_lite_001\preflight.json`

All 25 checks passed:
- Python 3.11.9 ✓
- ffmpeg 8.1.1 ✓ / ffprobe ✓
- GPU: RTX 3050 6GB CUDA=12.1 ✓
- All 9 required artifacts present ✓
- 4 optional artifacts DEGRADED_ALLOWED (not blocking) ✓
- Media root: 39 videos ✓
- Frame cache writable ✓
- F: drive: 373.7 GB free ✓ / C: drive: 69.3 GB free ✓
- All 12 provider classes importable ✓
- Backend and frontend ports: not running (expected pre-start) ✓

### Regression Tests
- **Core**: `406 passed, 2 skipped` (`.venv/Scripts/python -m pytest -q tests`)
- **Frontend**: `63 passed, 14 suites` (`npm test -- --run`), typecheck PASS, build PASS

### Rehearsal (26/26 PASS)
Full machine-readable report: `F:\AIC_WORK\artifacts\retrieval_v2\release_rehearsal\m13_lite_001\summary.json`

#### Single Mode (7 sessions)
| Session | Lane | Query | Results | Latency | Status |
|---|---|---|---|---|---|
| S1 | siglip_custom | nguoi dung truoc bien hieu | 20 | 49 s cold | PASS |
| S2 | btc_clip | fire truck on highway | 20 | 891 ms | PASS |
| S3 | siglip_custom | waterfall in forest | 20 | 1806 ms | PASS |
| S4 | asr_bge | kinh te | 20 | fast | PASS |
| S5 | ocr_trigram | VNPT | 20 | fast | PASS |
| S6 | qwen_bge | meeting room presentation | 20 | fast | PASS |
| S7 | btc_objects | person (threshold=0.5) | 20 | fast | PASS |

#### Compare Mode (6 sessions)
| Session | Lanes | Query | Per-lane results | Status |
|---|---|---|---|---|
| C1 | siglip_custom + btc_clip | xe canh sat | 20 + 20 | PASS |
| C2 | siglip + btc + ocr_trigram | VNPT | 20 + 20 + 20 | PASS |
| C3 | 5 lanes | presentation screen | 20 each | PASS |
| C4 | siglip + asr_bm25 (DEGRADED) | car accident | 20 + DEGRADED | PASS |
| C5 | siglip + qwen_structured | outdoor scene | 20 + 20 | PASS |
| C6 | siglip + ocr_bge + qwen_bge | bao cao ket qua | 20 each | PASS |

#### Sequence Mode (6 sessions)
| Session | Steps | Lanes | Strict | Results | Type | Status |
|---|---|---|---|---|---|---|
| Q1 | 2 | btc_clip → asr_bm25 | ON | 43 | STEP_ONLY (bm25 DEGRADED) | PASS |
| Q2 | 2 | siglip → siglip | ON | 20 | FULL/PARTIAL | PASS |
| Q3 | 3 | siglip → ocr → siglip | ON | 20 | STEP_ONLY | PASS |
| Q4 | 2 | btc_clip → asr_bge | OFF | 20 | FULL/PARTIAL | PASS |
| Q5 | 2 | siglip → btc_clip | ON | 20 | FULL/PARTIAL | PASS |
| Q6 | 2 | siglip → btc_objects | ON | 20 | FULL/STEP_ONLY | PASS |

#### Inspector Mode (3 sessions)
| Session | Opened From | Frame Space | Exact JPEG | CUSTOM KF | BTC KF | Nav | Status |
|---|---|---|---|---|---|---|---|
| I1 | siglip_custom | CUSTOM | YES | YES | YES | YES | PASS |
| I2 | btc_clip | BTC | YES | YES | YES | YES | PASS |
| I3 | sequence result | BTC | YES | YES | YES | — | PASS |

#### Failure / Degraded Handling (4 sessions)
| Session | Test | Graceful | Status |
|---|---|---|---|
| F1 | Sequence with asr_bm25 DEGRADED | YES — STEP_ONLY returned | PASS |
| F2 | Compare with DEGRADED lane | YES — other lanes unaffected | PASS |
| F3 | /api/health endpoint | YES — 200 OK | PASS |
| F4 | Invalid endpoint /api/capabilities wrong path | YES — JSON error, not crash | PASS |

---

## System Architecture (Frozen)

```
Competition Workstation
│
├── Frontend  (Svelte / localhost:3000)
│   ├── Single mode
│   ├── Compare mode     ─── per-lane tabs, no merging
│   └── Sequence mode    ─── step config, gap config, strict_order
│
└── Backend   (Python / 127.0.0.1:8765)
    │
    ├── /api/health
    ├── /api/v1/capabilities
    ├── /api/v1/search           ─── single lane
    ├── /api/v1/search/compare   ─── multi-lane parallel
    └── /api/v1/search/sequence  ─── temporal sequence
        │
        ├── siglip_custom  ─── SigLIP2 FAISS (CUSTOM 116k kf)
        ├── btc_clip       ─── ViT-B-32 FAISS (BTC 177k kf)
        ├── asr_bge        ─── BGE-M3 FAISS (SOURCE segments)
        ├── asr_bm25       ─── SQLite FTS5 [DEGRADED on dev]
        ├── ocr_trigram    ─── Trigram SQLite
        ├── ocr_bge        ─── BGE-M3 FAISS (CUSTOM kf)
        ├── ocr_bm25       ─── SQLite FTS5 [DEGRADED on dev]
        ├── media_bm25     ─── SQLite FTS5 [DEGRADED on dev]
        ├── qwen_structured─── SQLite structured rank
        ├── qwen_bge       ─── BGE-large-en FAISS (CUSTOM kf)
        ├── qwen_bm25      ─── SQLite FTS5 [DEGRADED on dev]
        └── btc_objects    ─── Detection postings (BTC kf)
            │
            └── MediaResolver ─── Physical H.264 → exact frame JPEG
                               (BoundedSemaphore=2, LRU 500 items / 100 MB)
```

---

## Query Policy

| Rule | Value |
|---|---|
| LLM query analysis | **DISABLED** |
| Automatic translation | **DISABLED** |
| Automatic lane routing | **DISABLED** |
| Hidden query transformation | **NONE** |
| Automatic synonym expansion | **DISABLED** |
| Query decomposition | **DISABLED** |

All retrieval is **deterministic and manual**. Operator enters queries directly into each lane.

---

## Known Limitations

1. No verified relevance GT — quality claims blocked by ground truth absence
2. Structured Qwen/Object searches require manual operator JSON config
3. `asr_bm25`, `ocr_bm25`, `media_bm25`, `qwen_bm25` artifacts absent on dev machine (DEGRADED_ALLOWED)
4. Only L21+L22 (39 of 873 videos) present on dev machine
5. Cold model load: ~49 s first visual query (RTX 3050 6GB)
6. Sequence decomposition is fully manual (operator defines each step)
7. No automatic fusion — per-lane independent ranking only
8. `ocr_trigram` returns EMPTY for very short or single-character queries (expected)

---

## Operator Reference

See [`docs/OPERATOR_RUNBOOK.md`](file:///F:/AIC_DEV/aic2026/docs/OPERATOR_RUNBOOK.md) for competition-day operation.

---

*Frozen at M13-lite — 2026-08-20. No further code changes without explicit new milestone.*
