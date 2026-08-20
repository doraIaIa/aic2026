# M5C — Qwen Standalone UI & Qwen Operational Closure Result

## 1. Executive Summary

Milestone M5C establishes full frontend workstation integration and operational closure for the three accepted Qwen single-lane retrieval providers:
1. `qwen_structured` — Exact structured facet matching on 116,767 Qwen frame annotations across 873 videos.
2. `qwen_bm25` — Exact lexical BM25 retrieval (`sqlite_fts5_bm25`) over Qwen frame captions (`LOWER_IS_BETTER`).
3. `qwen_bge` — Dense semantic retrieval using external BAAI/bge-large-en-v1.5 embeddings over 7 canonical fields (`full_text`, `caption`, `objects_attributes`, `spatial_relations`, `counts`, `scene`, `visible_actions`) with cosine similarity (`IndexFlatIP`, `HIGHER_IS_BETTER`) and optional manual `embedding_query` override.

All three lanes are exposed as independent, operator-controlled standalone retrieval modalities in the retrieval workstation UI (`F:/aic-video-search-demo`). No Compare mode, automatic fusion, automatic field routing, automatic translation, pruning, or Query Brain modifications were introduced.

---

## 2. Milestone Verification & Gate Results

### 2.1 Acceptance Criteria Matrix

| Gate / Requirement | Target / Constraint | Result | Status |
|---|---|---|---|
| **Independent Standalone Lanes** | `qwen_structured`, `qwen_bm25`, `qwen_bge` | Exposed via 13-way strategy selector | **PASS** |
| **Qwen BGE Field Control** | Exactly 7 fields (`full_text` default + 6 subfields) | Implemented dropdown with 7 accepted fields | **PASS** |
| **Qwen BGE Query Override** | Optional manual `embedding_query` override | Dedicated override input field | **PASS** |
| **Qwen BM25 Semantics** | FTS5 BM25 `LOWER_IS_BETTER`, no confidence badge | Formatted with `Lower is better` note | **PASS** |
| **Qwen Structured Facets** | 6 facet inputs (`objects`, `attributes`, etc.) | Dedicated facet input controls in active card | **PASS** |
| **Evidence Cards & Inspector** | Correct badges, caption snippet, matched facets | Full rendering in cards and evidence ledger | **PASS** |
| **Media Inspector Navigation** | Anchor jump to keyframe timestamp | Synced with custom keyframe timeline | **PASS** |
| **Frontend Unit Tests** | All suites passing | 11 passed (48 tests), 0 failed | **PASS** |
| **Frontend Typecheck** | `tsc --noEmit` zero errors | Clean typecheck | **PASS** |
| **Frontend Build** | `vite build` production bundle | Built successfully in 6.29s | **PASS** |
| **Backend Regression Test** | `pytest -q tests` (349 passed, 2 skipped) | 349 passed, 2 skipped in 154.59s | **PASS** |

---

## 3. Frontend Architecture & Artifacts

### 3.1 Modified Frontend Files (`F:/aic-video-search-demo`)

1. `client/src/retrieval/api.ts`
   - Added types: `QwenStructuredHit`, `QwenBm25Hit`, `QwenBgeHit`, `QwenBgeField`, health & search request/response types.
   - Added health check API functions: `fetchQwenStructuredHealth`, `fetchQwenBm25Health`, `fetchQwenBgeHealth`.
   - Added search API functions: `searchQwenStructured`, `searchQwenBm25`, `searchQwenBge`.
   - Added canonical EvidenceWindow converters: `qwenStructuredHitToEvidenceWindow`, `qwenBm25HitToEvidenceWindow`, `qwenBgeHitToEvidenceWindow`.

2. `client/src/retrieval/session.ts`
   - Extended `RoutingStrategy` with `"qwen_structured" | "qwen_bm25" | "qwen_bge"`.
   - Added session state fields for health responses, video candidate scopes, BGE field, embedding query override, and structured facet inputs.
   - Added action types and reducer cases for Qwen operations.

3. `client/src/retrieval/useSearchSession.ts`
   - Added health checks polling on mount.
   - Added execution branches routing search triggers to `searchQwenStructured`, `searchQwenBm25`, and `searchQwenBge`.

4. `client/src/retrieval/components/LaneControls.tsx`
   - Added 3 strategy selector buttons with status dots and badges.
   - Added active cards for Qwen Structured (with 6 facet inputs), Qwen BM25 (with FTS5 stats), and Qwen Field BGE (with 7-field selector and query override).

5. `client/src/retrieval/SearchWorkspace.tsx`
   - Connected Qwen props and callbacks to `LaneControls`.
   - Added Qwen route badges and empty-stage guidance text.

6. `client/src/retrieval/components/EvidenceResults.tsx`
   - Added Qwen card classes (`qwen-structured-card`, `qwen-bm25-card`, `qwen-bge-card`).
   - Added badge groups (`QWEN STRUCTURED`, `QWEN BM25`, `QWEN BGE [FIELD]`).
   - Added caption snippet display, matched facets tags, and directional score notes.

7. `client/src/retrieval/components/EvidenceInspector.tsx`
   - Added Qwen ledger formatting displaying caption, field, and matched facets.

8. `client/src/retrieval-workspace.css`
   - Added styles for `strategy-control-thirteen`, active cards, facet grids, dropdowns, card borders, pills, and snippets.

9. `client/src/retrieval/components/QwenLanes.test.tsx`
   - Unit test suite verifying UI rendering, selector state changes, reducer transitions, EvidenceWindow conversion invariants, and card presentation.

---

## 4. Backend Read-Only Status & Regression Audit

- Repository: `F:/AIC_DEV/aic2026`
- Source code status: **READ-ONLY** (no modifications made to core engine or provider source files during M5C).
- Pytest test suite: **349 passed, 2 skipped** (100% parity with accepted M5B2 / M5B2R baseline).

---

## 5. Git Commit Sign-Off

- Frontend repository (`F:/aic-video-search-demo`):
  - Commit Hash: `413b7c4432dd857b0ded2b36305d5f45c0a3e8ba`
  - Message: `feat(ui): add standalone qwen retrieval lanes`
- Core repository (`F:/AIC_DEV/aic2026`):
  - Documentation report: `docs/retrieval_v2/M5C_QWEN_UI_OPERATIONAL_CLOSURE_RESULT.md`
  - Message: `docs(retrieval-v2): record M5C qwen ui closure`
