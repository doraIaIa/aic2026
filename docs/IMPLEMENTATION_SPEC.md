# Implementation specification v0.1

## 1. System boundaries

### GitHub
Stores source code, small config templates, manifests without private raw data, tests, documentation, and reproducible job definitions.

### Google Drive
Canonical read-only BTC corpus and durable derived artifacts/checkpoints that must survive ephemeral cloud runtimes.

### Local Windows machine
Control plane and source of truth for validated SQLite/FAISS/index state. Uses `F:/AIC_WORK` as an explicit managed cache/work area where possible.

### Colab/Kaggle
Stateless or disposable compute workers. They process deterministic shards and emit immutable results. They never become the only location of important state.

## 2. Execution lifecycle

```text
PILOT -> VALIDATE -> BENCHMARK -> GO/NO-GO -> SHARD -> RUN -> FINALIZE -> VERIFY -> LOCAL IMPORT
```

A model or modality does not bypass this lifecycle because it appears useful.

## 3. Artifact lifecycle

For each shard:

```text
manifest shard
   -> checkpoint.json
   -> results.partial.jsonl
   -> results.jsonl.tmp
   -> results.jsonl
   -> checksum
   -> DONE.json (last)
```

If a runtime dies before `DONE.json`, the next run resumes from checkpoint/partial results.
If `DONE.json` exists but validation fails, quarantine the artifact; do not auto-repair silently.

## 4. Stable IDs

Persist stable corpus IDs and relative paths. Never use array row order as a durable cross-system identifier.
FAISS later must use stable database embedding IDs through an ID-mapped index rather than implicit row position.

## 5. Failure domains

- Cloud disconnect: lose at most current checkpoint interval.
- Corrupt partial final JSONL line: ignored/recovered on resume.
- Artifact copy interrupted: no valid DONE marker, therefore not imported.
- Optional modality failure: baseline lane remains available.
- Data-integrity mismatch: affected import/job stops.

## 6. M0 gates before M1 retrieval

1. Dataset root resolves without mutating Drive.
2. Canonical video list reconciles.
3. Keyframe relative paths and stable IDs are unique.
4. BTC metadata field containing actual frame index is identified and sampled.
5. Random frame-mapping golden tests pass against source videos.
6. CLIP feature shape and ordering match keyframe enumeration.
7. SQLite schema initialized and foreign keys enabled.
8. Eval/scorer contract can represent KIS, Q&A, TRAKE.
9. Full test suite passes.

Only after these gates should the project implement CLIP + FAISS baseline.

## 7. Cloud workload recommendations

- ASR: one video/audio item per work unit; shard many units for scheduling.
- OCR: 500-3000 keyframes per shard after throughput pilot.
- SigLIP2: 500-3000 keyframes per shard after pilot and GO decision.
- Exact-frame TRAKE refinement: local/source-video path, not a cloud preprocessing dependency.

Shard size must be set by measured wall-clock runtime, targeting a small fraction of a free runtime session rather than the maximum possible session length.
