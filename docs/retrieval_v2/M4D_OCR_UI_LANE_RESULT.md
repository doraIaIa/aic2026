# M4D — OCR Standalone UI + OCR Operational Closure

**Milestone:** M4D  
**Internal slice:** OCR Standalone UI + OCR Operational Closure  
**Date:** 2026-08-19  

---

## Verdict

| Flag | Value |
|---|---|
| M4D_ACCEPTANCE | **PASS** |
| OCR_IMPLEMENTATION_ACCEPTANCE | **PASS** |
| OCR_OPERATIONAL_ACCEPTANCE | **PASS** |
| M4_OCR_QUALITY_EVAL_STATUS | BLOCKED_BY_GROUND_TRUTH |
| M4_OCR_SUBSYSTEM_CLOSED | **YES** |
| M4E_READY | **YES** |
| M4_LANE_CLOSED | NO |

---

## Scope

Expose all THREE M4C OCR retrieval legs as explicit **Single Lane** modes
in the existing React retrieval workspace:

| Lane | Engine | Corpus | Score | Direction |
|---|---|---|---|---|
| OCR BM25 | SQLite FTS5 `ocr_fts` | 676,925 raw OCR items | `bm25_lower_is_better` | Lower is better |
| OCR Trigram | SQLite FTS5 trigram `ocr_trigram.sqlite` | 676,925 raw OCR items | `bm25_lower_is_better` | Lower is better |
| OCR BGE | BAAI/bge-m3 + FAISS IndexFlatIP `ocr_bge.faiss` | 612,813 dense OCR items | `cosine_ip_higher_is_better` | Higher is better |

**Non-dense raw items:** 64,112 items without dense vectors are preserved (not hidden).
**Low-confidence items:** 18,922 items with confidence < 0.5 are valid raw evidence (not filtered).

---

## Evidence & Identity Contract

- Entity type: `OCR_ITEM`
- Frame space: `CUSTOM`
- Attached to CUSTOM keyframe (retrieval evidence only)
- Exact frame submission authority remains the source video via Evidence Inspector
- `retrieval_score` and `ocr_confidence` are **never** combined or averaged

---

## Negative Invariants Preserved

- ✅ NO score fusion (`ocr_hybrid`, `ocr_auto` forbidden)
- ✅ NO fallback/rescue across lanes
- ✅ NO query rewriting/translating/accent-stripping in frontend
- ✅ NO comparing BGE scores with BM25/trigram raw scores
- ✅ NO client-side filtering of low-confidence OCR records
- ✅ NO calling non-dense raw items "invalid" or "failed"
- ✅ NO fabricating BTC identity or converting OCR items to ASR segments
- ✅ NO new npm dependencies

---

## Artifacts Verified

| Artifact | Checksum |
|---|---|
| `ocr_trigram.sqlite` | `0c58640840c06e00d2e504054bb2373791f65813ec13074031993c1f464b3ded` |
| `ocr_bge.faiss` | `69d5049fd87a47d33428029bf90dbbd2d5f7ba7022ce774d89e9c9291fde67f9` |
| `ocr_bge_rowmap.jsonl` | `9358c831049ea88bf9d70976e4d71658e97f5f9418ff2c3a357933270704df97` |

---

## Frontend Changes (9 files, 1196 insertions)

### Repository: `F:/aic-video-search-demo`

| File | Change |
|---|---|
| `client/src/retrieval/api.ts` | OCR health types, search types, API functions, `ocrHitToEvidenceWindow` |
| `client/src/retrieval/session.ts` | OCR routing strategies, state fields, reducer actions |
| `client/src/retrieval/useSearchSession.ts` | OCR health fetching, 3 search routing branches |
| `client/src/retrieval/SearchWorkspace.tsx` | OCR props, loading lanes, route badges, empty states |
| `client/src/retrieval/components/LaneControls.tsx` | 9-button strategy control, OCR active cards |
| `client/src/retrieval/components/EvidenceResults.tsx` | OCR card badges, text snippet, detector confidence, score labels |
| `client/src/retrieval/components/EvidenceInspector.tsx` | OCR ledger details (keyframe_uid, confidence, bbox) |
| `client/src/retrieval/components/OcrLanes.test.tsx` | 4 OCR-specific unit tests |
| `client/src/retrieval-workspace.css` | OCR lane styling (cyan/amber/rose color scheme) |

### Commit

```
a8eafa6 feat(retrieval-v2): add OCR single-lane UI modes (M4D)
```

---

## Verification Results

### Frontend

| Gate | Result |
|---|---|
| `npm test` (vitest) | **38 passed** (9 test files) |
| `npm run check` (tsc --noEmit) | **Clean** |
| `npm run build` (production) | **Clean** |

### Backend

| Gate | Result |
|---|---|
| `pytest -q tests` | **298 passed** |
| OCR BM25 health | OK (676,925 FTS rows) |
| OCR Trigram health | OK (676,925 indexed rows) |
| OCR BGE health | OK (612,813 FAISS rows) |

### API Smoke Queries

| Lane | Query | Hits | Score Example |
|---|---|---|---|
| OCR BM25 | "Đại học Cần Thơ" | 1 | -22.70 (bm25_lower_is_better) |
| OCR BM25 | "HTV9" | 3 | -10.07 |
| OCR BM25 | "Bệnh viện Chợ Rẫy" | 2 | -40.13 |
| OCR Trigram | "Dai hoc Can Tho" | 1 | -24.45 (typo-tolerant match) |
| OCR Trigram | "benh vien" | 3 | -51.48 |
| OCR BGE | "cơ quan công an" | 3 | 0.8703 (cosine_ip_higher_is_better) |
| OCR BGE | "lễ hội truyền thống" | 3 | 0.7239 |

### Scoping Verification

- Scoped "HTV9" to `L21_V001` → 3 hits, all L21_V001 ✅
- Scoped "HTV9" to non-existent `L29_V999` → 0 hits clean ✅

---

## Quality Evaluation Status

```
M4_OCR_QUALITY_EVAL_STATUS = BLOCKED_BY_GROUND_TRUTH
DEV_QUERIES = 15
SCORED = 0
UNSCORED = 15
```

Quality evaluation cannot proceed until ground truth annotations are available.

---

## Color Scheme

| Lane | Button | Card Border | Pill |
|---|---|---|---|
| OCR BM25 | `#06b6d4` (cyan) | `#06b6d4` | `#06b6d4` |
| OCR Trigram | `#f59e0b` (amber) | `#f59e0b` | `#f59e0b` |
| OCR BGE | `#f43f5e` (rose) | `#f43f5e` | `#f43f5e` |

---

## M4 Overall Status

| Subsystem | Status |
|---|---|
| ASR (M4A/M4B) | CLOSED |
| OCR (M4C/M4D) | **CLOSED** |
| Metadata (M4E) | NOT STARTED |
| M4 Overall | **OPEN** (Metadata remains) |
