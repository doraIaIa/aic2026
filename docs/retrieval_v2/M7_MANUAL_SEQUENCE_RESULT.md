# M7 Manual Temporal Sequence V1 Acceptance Report

## 1. Executive Summary

- **Task**: M7 Manual Temporal Sequence Engine V1 & Diagnostics UI
- **Active Core Roadmap**: M6 Compare (DONE) -> M7 Manual Sequence (ACCEPTED) -> M9 Inspector Hardening (NEXT CORE) -> M13-lite Freeze (AFTER M9)
- **Status**: ACCEPTED / FUNCTIONAL_TEMPORAL_GATE_PASS
- **Quality Status**: `M7_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH` (controlled functional temporal fixtures + real corpus smokes)
- **Core Principles**:
  - Manual definition of 2–5 retrieval steps with independent per-step execution.
  - Same-video grouping with canonical video identity.
  - Strict-order & temporal gap constraint satisfaction (`min_gap_ms`, `max_gap_ms`, `max_span_ms`).
  - Separation into 5 deterministic match groups: `FULL_MATCH`, `PREFIX_MATCH`, `SUFFIX_MATCH`, `PARTIAL_MATCH`, `STEP_ONLY_MATCH`.
  - Deterministic lexicographical ranking (no cross-modality score arithmetic / raw score fusion).
  - Explicit exclusion of `media_bm25` (zero temporal authority).
  - Seamless click-through from compact step timeline nodes to canonical `EvidenceInspector`.

---

## 2. Commit Hashes & Baseline Reference

| Component | Commit Hash | Summary | Tests & Build |
| :--- | :--- | :--- | :--- |
| **Core Backend** | `215c7d4` | `feat(search): add manual sequence mode` | 393 passed, 2 skipped in 153s |
| **Frontend UI** | `b0a08a5` | `feat(ui): add manual sequence mode` | 14 test files (63 passed), typecheck PASS, build PASS |
| **Acceptance Docs** | (this commit) | `docs(retrieval-v2): record M7 sequence acceptance` | Docs only |

---

## 3. Supported Temporal Lanes & Temporal Authority

The Sequence engine supports 11 temporal-capable lanes across 3 representation types:

| Lane ID | Modality | Representation Entity | Time Units & Anchor | Authority |
| :--- | :--- | :--- | :--- | :--- |
| `siglip_custom` | Visual | Frame Point | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (CUSTOM keyframe) |
| `btc_clip` | Visual | Frame Point | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (BTC frame) |
| `asr_bm25` | Speech | Segment Interval | `start_ms = round(start_sec * 1000)`, `end_ms = round(end_sec * 1000)` | Yes (Whisper medium) |
| `asr_bge` | Speech | Segment Interval | `start_ms = round(start_sec * 1000)`, `end_ms = round(end_sec * 1000)` | Yes (BGE-M3 dense) |
| `ocr_bm25` | Text | OCR Item | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (PaddleOCR raw) |
| `ocr_trigram` | Text | OCR Item | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (3-Gram typo) |
| `ocr_bge` | Text | OCR Item | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (BGE-M3 dense) |
| `qwen_bm25` | Vision-Lang | Frame Point | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (Qwen caption) |
| `qwen_bge` | Vision-Lang | Frame Point | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (7 fields dense) |
| `qwen_structured` | Vision-Lang | Frame Point | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (6 facets) |
| `btc_objects` | Detector | Frame Point | `start_ms = end_ms = anchor_ms = round(pts_time * 1000)` | Yes (584 classes) |
| `media_bm25` | Metadata | Video Record | No temporal timestamps | **REJECTED (NO_TEMPORAL_AUTHORITY)** |

---

## 4. Controlled Functional Temporal Fixtures (12/12 PASS)

Artifact path: `F:/AIC_WORK/artifacts/evaluation/sequence_v1/m7_seq_20260820_053432/fixture_results.json`

| Case ID | Name | Scenario | Expected Group | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| `FIX01` | `point_to_point_valid` | Point -> Point, +10s gap (within 0–60s) | `FULL_MATCH` | PASS |
| `FIX02` | `point_to_point_order_violation` | Point -> Point, reversed timestamps (30s -> 10s) | Filtered (order violation) | PASS |
| `FIX03` | `point_to_point_gap_too_large` | Point -> Point, +70s gap (exceeds 60s max) | Filtered (gap too large) | PASS |
| `FIX04` | `point_to_point_gap_too_small` | Point -> Point, +2s gap (violates min 5s) | Filtered (gap too small) | PASS |
| `FIX05` | `point_to_segment_valid` | Point -> Segment, 10s -> [20s, 25s] | `FULL_MATCH` | PASS |
| `FIX06` | `segment_to_point_valid` | Segment -> Point, [10s, 15s] -> 25s | `FULL_MATCH` | PASS |
| `FIX07` | `ocr_item_to_segment_valid` | OCR point -> Speech segment interval | `FULL_MATCH` | PASS |
| `FIX08` | `3step_chain_full_match` | S1 -> S2 -> S3 valid monotonic chain | `FULL_MATCH` | PASS |
| `FIX09` | `3step_prefix_match` | S1 -> S2 valid, S3 missing | `PREFIX_MATCH` | PASS |
| `FIX10` | `3step_suffix_match` | S1 missing, S2 -> S3 valid | `SUFFIX_MATCH` | PASS |
| `FIX11` | `4step_partial_match` | S1 missing, S2 -> S3 valid, S4 missing | `PARTIAL_MATCH` | PASS |
| `FIX12` | `span_violation_filter` | Total span 65s (exceeds max_span 60s) | Filtered (span violation) | PASS |

---

## 5. Real-Corpus Manual AIC Smoke Sessions (10/10 PASS)

Artifact path: `F:/AIC_WORK/artifacts/evaluation/sequence_v1/m7_seq_20260820_053432/smoke_sessions.json`

| Session ID | Description | Steps | Status | Latency | FULL | PREFIX | PARTIAL | STEP ONLY |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `SEQ01` | Traffic red car -> street crowd (Visual -> Visual) | 2 | OK | 23,764 ms | 1 | 0 | 0 | 50 |
| `SEQ02` | OCR text item -> Visual person (OCR -> Visual) | 2 | OK | 1,876 ms | 2 | 0 | 0 | 44 |
| `SEQ03` | Speech interval -> Visual kitchen (Speech -> Visual) | 2 | OK | 100 ms | 0 | 0 | 0 | 36 |
| `SEQ04` | 3-step Mixed Modality (OCR -> Visual -> Speech) | 3 | OK | 34,397 ms | 0 | 0 | 0 | 50 |
| `SEQ05` | 2-step Cross-Space Visual (SigLIP -> OpenCLIP) | 2 | OK | 10,299 ms | 0 | 0 | 0 | 42 |
| `SEQ06` | Structured Qwen facets -> SigLIP Visual | 2 | OK | 4,215 ms | 1 | 0 | 0 | 48 |
| `SEQ07` | BTC Objects detector -> ASR speech | 2 | OK | 23,077 ms | 1 | 0 | 0 | 47 |
| `SEQ08` | 3-step Co-occurrence (Strict Order OFF, max_span 120s) | 3 | OK | 222 ms | 0 | 2 | 0 | 49 |
| `SEQ09` | Qwen BGE embedding -> SigLIP visual | 2 | OK | 7,368 ms | 0 | 0 | 0 | 50 |
| `SEQ10` | 4-step Multimodal Narrative (OCR -> Vis -> Vis -> Speech) | 4 | OK | 1,006 ms | 0 | 2 | 1 | 50 |

---

## 6. Frontend Acceptance & UI Flow

1. **Top Bar Mode Switcher**:
   - Toggling between `SINGLE LANE`, `COMPARE MODE`, and `SEQUENCE MODE`.
   - Topbar activity indicator reports real-time Sequence response status (`READY` / `OK` / `PARTIAL`).
2. **Sequence Controls (`SequenceControls.tsx`)**:
   - 2–5 step builder with step numbers (`S1`, `S2`, ...).
   - Lane dropdown containing only temporal-capable lanes (excludes `media_bm25`).
   - Query inputs with modality-specific placeholders.
   - Lane-specific configuration drawers for `qwen_bge` (field selector), `qwen_structured` (6 facets), and `btc_objects` (584 classes, mode, threshold).
   - Temporal constraints panel with Strict Order toggle, Same Video locked badge, gap inputs and presets (`15s`, `30s`, `60s`, `120s`), and Top-K per step.
3. **Sequence Results (`SequenceResults.tsx`)**:
   - Diagnostics summary bar (latency, videos considered, multi-step videos, order violations, gap violations, chains emitted).
   - Group navigation tabs (`ALL`, `FULL MATCH`, `PREFIX MATCH`, `SUFFIX MATCH`, `PARTIAL MATCH`, `STEP ONLY`).
   - Chain cards with compact timeline track:
     `[S1: Lane] 12.0s` -> `+10.0s gap` -> `[S2: Lane] 24.0s`
   - Clicking any step node or "Inspect Chain" opens the exact timestamp and keyframe in the existing `EvidenceInspector`.
4. **Validation Gate**:
   - Vitest: 14 test suites, 63 tests PASS.
   - TypeScript: `tsc --noEmit` PASS (0 errors).
   - Build: `vite build` PASS.

---

## 7. Next Roadmap Gate

- **Active Core Roadmap**:
  - `M6 Compare` = DONE
  - `M7 Manual Sequence` = ACCEPTED
  - `M9 Inspector hardening` = **NEXT CORE TASK**
  - `M13-lite Freeze` = AFTER M9
