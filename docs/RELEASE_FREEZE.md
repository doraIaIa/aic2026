# M13R Release Freeze & Truthfulness Reconciliation
<!-- docs/RELEASE_FREEZE.md — frozen 2026-08-20 M13R -->

## Release Identity

| Field | Value |
|---|---|
| Release ID | `AIC2026_CORE_V1` |
| Milestone | **M13R** |
| Freeze Date | 2026-08-20 |
| Core Code HEAD | `1bc3be6` (`fix(media): bound exact frame extraction and close M9F authority gaps`) |
| Core Final Release HEAD | `HEAD` (reconciled release documentation) |
| Frontend HEAD | `2824418` (`feat(ui): harden media inspector`) |

---

## Required Release Status Semantics

```
CORE_SOFTWARE_RELEASE_FROZEN                = YES
LOCAL_DEV_RUNTIME_READY                     = YES (39 / 873 videos)
FULL_CORPUS_COMPETITION_DEPLOYMENT_READY    = UNVERIFIED
CORE_COMPETITION_WORKSTATION_READY          = PENDING_DEPLOYMENT
M13_FINAL_ACCEPTANCE                        = SOFTWARE_PASS
```

### Status Definitions:
1. **`CORE_SOFTWARE_RELEASE_FROZEN = YES`**: All core retrieval code, test suites, builds, and manifests are finalized, clean, and frozen without unresolved defects.
2. **`LOCAL_DEV_RUNTIME_READY = YES`**: The configured local development environment (39 physical source videos in L21/L22) executes all documented workflows, single/compare/sequence queries, and frame extraction.
3. **`FULL_CORPUS_COMPETITION_DEPLOYMENT_READY = UNVERIFIED`**: The actual competition target workstation (hosting all 873 physical videos and full canonical datasets) was not accessible for direct execution in this task.
4. **`CORE_COMPETITION_WORKSTATION_READY = PENDING_DEPLOYMENT`**: Software is approved and frozen; full competition deployment will be verified upon deploying onto the target runtime.

---

## Gate & Test Summary

| Gate / Suite | Result | Details |
|---|---|---|
| Core Pytest | **PASS** | 406 passed, 2 skipped in 280.29s (`.venv/Scripts/python -m pytest -q tests`) |
| Frontend Vitest | **PASS** | 14 test files passed, 63 tests passed |
| Frontend Typecheck | **PASS** | `tsc --noEmit` exit code 0 |
| Frontend Build | **PASS** | `vite build && esbuild` built in 15.28s, exit code 0 |
| Preflight Inspection | **PASS** | 25/25 checks passed (`m13_preflight.py`) |
| Rehearsal Suite | **PASS** | **26/26 sessions VERIFIED_EXECUTED** (7 Single, 6 Compare, 6 Sequence, 3 Inspector, 4 Failure) |
| Restart Rehearsal | **PASS** | Clean restart verified, port cleared, health 200 OK, zero index rebuild |
| Media Authority | **PASS** | Exact H.264 frame decode proven via M9G (PSNR=inf) |

---

## Provider Inventory (Dev Machine Status)

| Lane | Frame Space | Type | Status on Dev |
|---|---|---|---|
| `siglip_custom` | CUSTOM (116,767 kf) | Dense embedding | **HEALTHY** |
| `btc_clip` | BTC (177,321 kf) | Dense embedding | **HEALTHY** |
| `asr_bge` | SOURCE (segments) | Dense embedding | **HEALTHY** |
| `asr_bm25` | SOURCE (segments) | Lexical FTS | **DEGRADED** (missing `asr_fts` table on dev) |
| `ocr_trigram` | CUSTOM (116,767 kf) | Character 3-gram FTS | **DEGRADED** (index present; mapping DB lacks `ocr_items`) |
| `ocr_bge` | CUSTOM (116,767 kf) | Dense embedding | **DEGRADED** (index present; metadata join requires `ocr_items`) |
| `ocr_bm25` | CUSTOM (116,767 kf) | Lexical FTS | **DEGRADED** (missing `ocr_fts` table on dev) |
| `media_bm25` | SOURCE (video info) | Lexical FTS | **DEGRADED** (missing `media_fts` table on dev) |
| `qwen_structured` | CUSTOM (116,767 kf) | Structured facet rank | **HEALTHY** |
| `qwen_bge` | CUSTOM (116,767 kf) | Dense embedding | **HEALTHY** |
| `qwen_bm25` | CUSTOM (116,767 kf) | Lexical FTS | **DEGRADED** (missing `qwen_caption_fts` table on dev) |
| `btc_objects` | BTC (177,321 kf) | Object detections | **HEALTHY** |

---

## Query Intelligence & Scope Policy

| Policy | Value |
|---|---|
| LLM Query Analysis | **DISABLED** |
| Automatic Translation | **DISABLED** |
| Automatic Lane Routing | **DISABLED** |
| Automatic Synonym Expansion | **DISABLED** |
| Hidden Query Rewriting | **NONE** |
| Submission Integration | **NOT IN CORE RELEASE** (frozen core ends at exact frame evidence verification) |

---

## Rehearsal Evidence Files

Located in `F:\AIC_WORK\artifacts\retrieval_v2\release_rehearsal\m13_lite_001\`:
- `manifest.json`: Rehearsal run metadata
- `preflight.json`: 25 preflight checks
- `single_sessions.jsonl`: 7 single-lane query sessions
- `compare_sessions.jsonl`: 6 compare-mode sessions
- `sequence_sessions.jsonl`: 6 temporal sequence sessions
- `inspector_sessions.jsonl`: 3 media inspector exact decode sessions
- `failure_sessions.jsonl`: 4 partial/degraded error isolation sessions
- `restart.json`: Clean restart verification record
- `summary.json`: Aggregated session metrics
- `DONE`: Rehearsal completion marker

---

## Rollback Reference

| Repo | Previous Accepted | Message |
|---|---|---|
| Core | `7594755` | docs(retrieval-v2): record M9 inspector acceptance |
| Frontend | `2824418` | feat(ui): harden media inspector |

> **Do NOT perform rollback.** This section is documentation only.

---

*Frozen at M13R — 2026-08-20.*
