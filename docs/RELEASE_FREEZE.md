# M13-lite Release Freeze
<!-- docs/RELEASE_FREEZE.md — frozen 2026-08-20 -->

## Release Identity

| Field | Value |
|---|---|
| Release ID | `AIC2026_CORE_V1` |
| Milestone | M13-lite |
| Freeze Date | 2026-08-20 |
| Core git | `1bc3be6` (main) |
| Frontend git | `2824418` (main) |

## Gate Summary

| Gate | Status |
|---|---|
| M0–M6 | CLOSED |
| M7 Manual Sequence | PASS |
| M7R Temporal Audit | PASS |
| M9 Media Inspector | PASS |
| M9F Authority Fix | PASS |
| M9G Real-Source Closure | PASS |
| M13-lite Preflight (25/25) | **PASS** |
| M13-lite Rehearsal (26/26) | **PASS** |
| Core regression (406 pass, 2 skip) | **PASS** |
| Frontend regression (63 pass) | **PASS** |

## Acceptance

```
M13_LITE_ACCEPTANCE              = PASS
CORE_COMPETITION_WORKSTATION_READY = YES
CORE_RELEASE_FROZEN              = YES
RELEVANCE_QUALITY                = BLOCKED_BY_GROUND_TRUTH (not a gate)
```

## Provider Inventory

| Lane | Group | Frame Space | Classification |
|---|---|---|---|
| `siglip_custom` | VISUAL | CUSTOM | CRITICAL |
| `btc_clip` | VISUAL | BTC | CRITICAL |
| `asr_bm25` | ASR | SOURCE | DEGRADED on dev |
| `asr_bge` | ASR | SOURCE | DEGRADED_ALLOWED |
| `ocr_bm25` | OCR | CUSTOM | DEGRADED on dev |
| `ocr_trigram` | OCR | CUSTOM | DEGRADED_ALLOWED |
| `ocr_bge` | OCR | CUSTOM | DEGRADED_ALLOWED |
| `media_bm25` | MEDIA | SOURCE | DEGRADED on dev |
| `qwen_structured` | QWEN | CUSTOM | DEGRADED_ALLOWED |
| `qwen_bm25` | QWEN | CUSTOM | DEGRADED_ALLOWED |
| `qwen_bge` | QWEN | CUSTOM | DEGRADED_ALLOWED |
| `btc_objects` | OBJECT | BTC | DEGRADED_ALLOWED |

## Known Limitations

- No LLM query analysis, automatic translation, or lane routing
- `asr_bm25`, `ocr_bm25`, `media_bm25`, `qwen_bm25` artifact absent on dev machine (DEGRADED_ALLOWED)
- Only L21+L22 (39 videos) physically present on dev; full 873-video corpus on competition server
- Cold model load: ~49 s first query (RTX 3050); warm: <2 s
- No fused ranking — per-lane independent scores only

## Rollback Reference

| Repo | Previous Accepted | Message |
|---|---|---|
| Core | `7594755` | docs(retrieval-v2): record M9 inspector acceptance |
| Frontend | `2824418` | feat(ui): harden media inspector |

> **Do NOT perform rollback.** This section is documentation only.

## Manifest

Full machine-readable manifest:
`F:\AIC_WORK\artifacts\retrieval_v2\release_freeze\AIC2026_CORE_RELEASE_V1.json`

## Rehearsal Evidence

Full rehearsal sessions (26 sessions):
`F:\AIC_WORK\artifacts\retrieval_v2\release_rehearsal\m13_lite_001\summary.json`

Preflight report:
`F:\AIC_WORK\artifacts\retrieval_v2\release_rehearsal\m13_lite_001\preflight.json`
