# AGENTS.md — AIC 2026 Engineering Constitution for AI Coding Agents

> **Status:** Mandatory repository-wide engineering rules  
> **Applies to:** All AI coding agents, coding assistants, autonomous agents, scripts, and delegated implementation tasks working on the AIC 2026 repository.  
> **Purpose:** Protect data integrity, preserve architectural invariants, prevent silent scope expansion, and keep every change reproducible, auditable, and reversible.

---

# 0. Core Principle

All work in this repository must preserve:

> **Independent evidence, shared identity, late fusion.**

And:

> **Raw immutable → Canonical normalized → Runtime rebuildable.**

Priority:

```text
Correctness
→ Recall safety
→ Data integrity
→ Reproducibility
→ Explainability
→ Operator control
→ Speed
→ Architectural elegance
```

If a requested implementation conflicts with these rules, **STOP and report the conflict**. Never silently work around the rule.

---

# 1. Mandatory Reading Before Every Task

Before making any change, read:

1. `AGENTS.md`
2. `docs/PROJECT_STATE.md`
3. `docs/DATA_CONTRACT_LOCK.md`
4. relevant Retrieval V2 design document(s)
5. the exact current task prompt

For Retrieval V2 work, read the relevant planning files:

```text
README
00_MASTER_ARCHITECTURE
01_DATA_HUB_MAPPING
02_QUERY_BRAIN_SEARCH_MODES
03_SEARCH_LANES_TECH_STACK
04_TEMPORAL_MEDIA_INSPECTOR
05_IMPLEMENTATION_EVALUATION_ROADMAP
```

If a required document is missing:
- report `NOT FOUND`;
- do not invent its contents;
- do not silently substitute another document.

---

# 2. Source-of-Truth Precedence

When sources disagree:

```text
1. Verified raw/source artifact
2. Frozen data contract / canonical manifest
3. Validated canonical machine data
4. Validated derived runtime index
5. Current audit report
6. Architecture/design document
7. Project state / task notes
8. Historical notes/chat/stale reports
```

Rules:

- Newer modification time does not automatically mean more authoritative.
- A stale merged artifact does not prove its source extraction is incomplete.
- A copied file is not automatically more authoritative than its source.
- Never reconcile contradictions silently.
- Material conflicts must stop the affected import/decision until resolved.

---

# 3. Scope Discipline

1. Implement **only** the milestone/slice explicitly requested.
2. Completing one milestone does not authorize work on later milestones.
3. Do not “finish adjacent work while already here”.
4. Do not refactor unrelated working code.
5. Do not create parallel replacements for working subsystems unless explicitly required.
6. Before creating a new resolver/provider/result contract/database abstraction/evaluation runner/media service, inspect whether an existing implementation can be reused or extended.
7. Prefer adapters and versioned extensions over parallel rewrites.
8. If scope is ambiguous, choose the **smallest safe interpretation** and report assumptions.
9. Minimize files changed.
10. Respect any task-specific file allowlist exactly.

---

# 4. Git and Repository Safety

1. Never use destructive repository commands unless explicitly authorized.
2. Never run `git reset --hard`, destructive `git clean`, history rewrite, or equivalent against user work.
3. If the working tree is dirty, inspect and report it; preserve pre-existing user changes.
4. Do not stash user changes automatically.
5. Do not push unless explicitly requested.
6. Prefer small reversible commits.
7. One implementation slice should normally correspond to one focused commit.
8. Do not mix unrelated formatting/refactoring into feature commits.
9. Record the starting `HEAD`.
10. Report final `HEAD` and working-tree status.

---

# 5. Raw Data Is Immutable

1. Never modify, rename, move, delete, or rewrite BTC source data.
2. Never modify organizer-provided source video, BTC keyframes, map-keyframes, objects, media-info, or feature files.
3. Validated expensive team outputs are immutable raw artifacts:
   - ASR;
   - OCR;
   - Qwen;
   - vector shards;
   - source manifests.
4. Corrections create a new canonical/derived artifact or version.
5. Never clean raw OCR text in place.
6. Never rewrite raw Qwen JSON to fit a nicer schema.
7. Never overwrite a valid completed shard.
8. Model/config/input changes require a new artifact/version.

---

# 6. Canonical vs Derived

Canonical machine data:
- versioned;
- stable identity;
- provenance-preserving;
- rebuildable from raw/source artifacts.

Derived runtime data includes:

```text
SQLite
FTS
FAISS
bitsets
postings
profiles
caches
```

Derived runtime artifacts are rebuildable and are never more authoritative than canonical data.

If runtime conflicts with canonical data:

> canonical data wins.

Never alter canonical data merely to make an index pass.

---

# 7. Never Infer Data Contracts

Never infer without evidence:

- file format;
- schema;
- vector dimension;
- dtype;
- vector normalization;
- distance/similarity metric;
- model identity;
- model revision;
- tokenizer/preprocessing behavior;
- FPS;
- time base;
- physical frame convention;
- local keyframe numbering;
- stable ID mapping;
- vector row mapping;
- shard completeness.

If unverified, use:

```text
UNKNOWN
NOT_VERIFIED
SOURCE_NOT_AVAILABLE_FOR_RUNTIME_AUDIT
```

Never fabricate a plausible value.

---

# 8. Canonical Video Identity

`video_id` is the global video identity.

1. Do not duplicate video entities because one video belongs to multiple branches.
2. Multi-parent taxonomy membership is valid.
3. Video ordinal is a compact runtime ID only.
4. Ordinal never replaces `video_id`.
5. Every ordinal map must have an `ordinal_space_id` or equivalent build identity.
6. Never load a bitset with a different ordinal space.

---

# 9. Frame Spaces Are Strictly Separate

The namespaces are distinct:

```text
BTC
CUSTOM
SOURCE_VIDEO
```

Rules:

1. Never merge BTC and CUSTOM keyframe namespaces.
2. Never assume BTC keyframe `123` equals CUSTOM keyframe `123`.
3. Never assume local keyframe ordinal equals physical source-video frame index.
4. Do not use reset-per-video filename/keyframe ID/embedding index as a global ID.
5. Cross-space association must use verified `video_id + time + physical frame mapping when available`.
6. Nearby BTC and CUSTOM frames remain distinct evidence entities.
7. Nearest-time mapping is a derived relation, not identity.

---

# 10. Exact Frame Authority

Exact submission-frame authority is the **source video**.

1. Retrieval keyframes are candidate/evidence anchors.
2. ASR/OCR/Qwen timestamps are temporal anchors.
3. BTC/CUSTOM keyframes are not final submission-frame authority.
4. Browser playback position is not exact-frame authority.
5. Exact frame selection must resolve through verified source-video frame/time mapping.
6. Never convert keyframe ordinals into source-frame IDs without a verified contract.
7. Exact mapping uncertainty must fail closed for exact-frame submission.
8. Reuse the existing verified media resolver where possible.
9. Never create a second competing exact-frame convention.

---

# 11. Canonical Time

Canonical/runtime temporal joins use:

```text
integer milliseconds
```

unless a frozen contract explicitly says otherwise.

Preserve raw `pts_time` or source timing in provenance when useful.

Do not use float timestamps as global identity.

---

# 12. Path Portability

1. Never persist machine-specific absolute paths in manifests, canonical files, SQLite, FAISS metadata, evaluation data, or taxonomy artifacts.
2. Store relative paths/source references.
3. Resolve against runtime-configured roots.
4. Do not hardcode Colab paths, Windows drive letters, or personal Drive roots into canonical artifacts.
5. Do not expose local absolute paths through public APIs unless explicitly required for internal diagnostics.

---

# 13. Source Registry and Artifact Passport

Every important source/artifact/index must record, where applicable:

```text
artifact/source ID
task
producer/model
model revision
config hash
schema version
git commit
input manifest hash
input checksum(s)
expected count
processed count
failures
output checksum
build timestamp
status
```

Vector index passports additionally require:

```text
index ID
lane
model ID
model revision
preprocessing/processor version
dimension
dtype
normalization
similarity metric
entity space
row count
row-map checksum
```

Encoder/index mismatch must **fail closed for that lane**.

Never “search anyway”.

---

# 14. Batch Processing

Every batch process must be:

- resumable;
- idempotent;
- shardable;
- restart-safe;
- atomic at finalization.

Rules:

1. Write temp/partial output first.
2. Validate before finalizing.
3. Completed valid artifacts are immutable.
4. A shard is trusted only when completion metadata validates against output checksum and manifest/config.
5. Never overwrite a valid completed shard.
6. Changed model/config/input requires a new version.
7. Before any full-dataset ML run:

```text
pilot
→ validate
→ benchmark
→ GO / NO-GO
→ shard production
```

8. Cloud workers must not mutate production SQLite.
9. Cloud workers emit immutable artifacts.
10. Local validation/import owns production runtime state.

---

# 15. Retrieval V2 Common Evidence Contract

Every retrieval lane must ultimately return evidence resolvable to:

```text
lane
entity/evidence type
video_id
time or interval
frame space if applicable
frame/keyframe reference if applicable
rank
raw score
score type
query variant
build/index provenance
evidence payload
```

Lane-specific internal results are allowed only if converted to the common contract at the lane boundary.

Do not create incompatible provider-specific identity systems.

---

# 16. Retrieval Lanes Remain Independent

The following evidence families must remain independently runnable/measurable where practical:

```text
SigLIP2 custom visual
BTC CLIP visual
Qwen semantics
ASR
OCR
BTC Objects
Media-info
Taxonomy/routing
```

Rules:

1. Each lane keeps independent diagnostics.
2. Lane failure must not silently disable unrelated lanes.
3. Per-lane metrics must remain measurable after hybrid search exists.
4. Do not create a “mega embedding”.
5. Do not hide lane provenance after fusion.

---

# 17. Never Cross Embedding Spaces

Forbidden:

```text
BGE query ↔ SigLIP image vector
SigLIP query ↔ BTC CLIP image vector
CLIP query ↔ BGE OCR vector
```

Known conceptual spaces:

```text
CUSTOM VISUAL → SigLIP2
BTC VISUAL    → CLIP ViT-B/32
TEXT SEMANTIC → BGE-M3
```

Each vector lane must use the matching query encoder/preprocessing contract.

If model identity is unknown, that vector lane is not production-safe.

---

# 18. Lexical and Semantic Text Retrieval Must Coexist

For ASR/OCR/text-heavy evidence:

1. Do not replace lexical retrieval with dense embeddings by default.
2. Exact names, numbers, acronyms and phrases require a lexical path.
3. Dense retrieval is complementary.
4. OCR should retain fuzzy/trigram support.
5. Raw text remains available for explanation.
6. Normalized text must not overwrite raw text.

---

# 19. Missing Evidence Is Not Negative Evidence

Do not interpret absence as semantic absence.

Examples:

```text
zero ASR != irrelevant video
missing Qwen != irrelevant frame
no object detection != object absent
no OCR != no useful content
taxonomy uncertainty != excluded video
```

Optional modalities fail open.

Data-integrity failures fail closed for the affected lane/import.

---

# 20. Qwen Guardrails

1. Raw Qwen output is immutable.
2. Qwen semantic fields are observations, not guaranteed truth.
3. Never fabricate Qwen confidence.
4. Normalization score is not Qwen confidence.
5. Single-frame `visible_actions` are not verified temporal actions.
6. Missing Qwen records remain explicit.
7. Qwen absence is not a hard negative.
8. Raw phrase and normalized facet must both remain traceable.

---

# 21. OCR Guardrails

1. Preserve raw OCR text.
2. Preserve bbox/confidence when available.
3. Normalization is derived.
4. Do not permanently delete low-confidence raw OCR solely for cleaner search.
5. Runtime may downweight/filter via explicit policy.
6. OCR embedding row ↔ metadata row mapping must validate exactly.
7. OCR frame space must be explicit.
8. Unresolvable OCR references are marked unresolved, never guessed.
9. Never draw OCR bbox on another physical frame without verified equivalence.

---

# 22. ASR Guardrails

1. ASR segments are temporal intervals, not exact submission frames.
2. Preserve start/end/raw transcript.
3. Zero-ASR videos remain corpus members.
4. Do not duplicate ASR text into every frame as canonical truth.
5. Frame↔ASR is a temporal join.
6. A stale merged artifact does not prove incomplete extraction.
7. If validated source outputs are complete, rebuild canonical merge rather than rerun expensive ASR.

---

# 23. BTC Object Guardrails

1. BTC detections belong to BTC frame space.
2. Preserve detector confidence and bbox.
3. Missing detection is not a hard negative.
4. Never transfer BTC bbox to CUSTOM/SOURCE frames.
5. Normalized aliases must preserve raw class provenance.
6. Coverage must be measured before object evidence can participate in hard pruning.

---

# 24. Taxonomy Guardrails

1. Taxonomy is routing/prior evidence, not universal truth.
2. One leaf corresponds to one canonical `video_id`.
3. A video may have multiple parent memberships.
4. Program and Topic are distinct views.
5. Object/action/attribute/scene/relation facets are not forced into one tree.
6. Temporal Region is below video, not a taxonomy leaf.
7. News/topic-heavy content may require region-level membership.
8. Generic object absence must not hard-prune videos.
9. Membership status/confidence/provenance must be explicit.
10. Routing terms are not membership truth.

---

# 25. Pruning Rules

Supported policy concepts:

```text
OFF
SAFE
AGGRESSIVE
```

Rules:

1. OFF must remain available.
2. SAFE is the default candidate for automated routing after benchmark.
3. SAFE preserves a global escape/rescue path.
4. AGGRESSIVE/hard prune requires explicit GT-survival evidence.
5. Never hard-prune production solely from LLM output, Qwen facets, OCR, object absence, or unverified taxonomy.
6. Primary pruning metric is GT survival, not minimum candidate count.
7. Policy changes require benchmark/regression evidence.

---

# 26. Query Brain / LLM Guardrails

LLM output is advisory.

The Query Brain may:
- parse;
- suggest Program/Topic;
- suggest objects/actions/attributes/scenes;
- suggest OCR/ASR hints;
- detect temporal structure;
- recommend lanes;
- recommend pruning mode;
- generate structured variants.

It must never:

1. overwrite `original_query`;
2. invent video/frame/timestamp evidence;
3. become the sole retrieval engine;
4. hard-prune solely from free-form LLM judgment;
5. mutate canonical taxonomy memberships;
6. treat uncalibrated LLM confidence as retrieval truth;
7. silently remove user-entered constraints;
8. silently rewrite user-pinned facets.

Manual/user-pinned input overrides auto suggestions.

If Query Brain fails, valid non-LLM retrieval paths must remain usable.

---

# 27. Preserve the Whole Query

Structured decomposition does not replace the original query.

Keep:

```text
original query
+
structured/query-plan variants
```

Do not reduce a complex BTC query to object keywords only.

Generated rewrites must record producer/version.

---

# 28. Sequence / Temporal Guardrails

1. Sequence V1 = independent per-step retrieval + temporal matching.
2. Different steps may use different lanes.
3. Match by canonical `video_id + time`.
4. Never use keyframe ordinal order as temporal truth.
5. Gap thresholds are heuristics.
6. Never hardcode 60 seconds as universal.
7. Preserve full, prefix, suffix, step-only and useful violation groups.
8. For 3–5 steps prefer bounded DP/beam search over brute-force Cartesian joins.
9. Same-video sequence does not prove same-person/same-object identity.
10. Never claim ReID unless an explicit validated identity model exists.

---

# 29. Fusion Rules

Never directly sum heterogeneous raw scores:

```text
SigLIP cosine
CLIP cosine
BGE cosine
BM25
OCR confidence
detector confidence
```

Tier-1 baseline:

```text
rank-based fusion / RRF
```

Rules:

1. Preserve per-lane provenance.
2. RRF parameters must be config/experiment values.
3. Weighted fusion requires benchmark evidence.
4. Calibration requires explicit methodology.
5. Compare fusion against the best single lane.
6. Do not promote fusion merely because it is more sophisticated.

---

# 30. Global Rescue

1. Global Rescue must remain possible after routing/taxonomy exists.
2. Rescue runs outside the primary hypothesis.
3. Rescue provenance must be visible.
4. Rescue must not silently widen a strict query.
5. Trigger thresholds/quotas are experimental/config values.
6. Measure recovered GT and latency cost.

---

# 31. Media / Exact-Frame Reuse

1. Reuse the existing verified media resolver.
2. Do not create a parallel exact-frame backend unless explicitly required.
3. Nearest sampled keyframe != exact physical frame.
4. UI/API must distinguish seconds, physical frames, and sampled keyframes.
5. Never label “+3 keyframes” as “+3 frames”.
6. Browser seek is navigation, not frame authority.
7. Prefer on-demand Range/exact-JPEG/cache approaches before precomputing all frames.

---

# 32. Runtime Database and Infrastructure

1. Do not add PostgreSQL, Elasticsearch/OpenSearch, Milvus, Qdrant, Vespa, Celery, Airflow, or another service without a measured bottleneck.
2. Tier-1 architecture prefers:

```text
SQLite
+ FTS5
+ FAISS
+ bitsets/postings
```

3. Cloud workers never mutate production SQLite.
4. Do not store raw media/vector bytes in SQLite unless explicitly required.
5. Production DB must be reproducible from canonical artifacts.
6. Schema changes require migration notes and tests.

---

# 33. Dependency Rules

1. Never run `pip install --upgrade` as a convenience fix.
2. Never upgrade dependencies merely to make tests pass.
3. Dependency changes require explicit review.
4. Do not introduce infrastructure because it is newer/fashionable.
5. Prefer existing project dependencies.
6. New dependencies require documented need, impact and rollback.

---

# 34. Evaluation First, Claims Second

Never claim retrieval quality improved without benchmark evidence.

Use appropriate metrics such as:

```text
Video Recall@K
Frame/Range Recall@K
First Correct Rank
MRR
Sequence Recall
GT survival after pruning
Rescue recovery
latency p50/p95
unique lane contribution
```

A model is not better because:
- it is newer;
- a few examples look good;
- an LLM says so.

---

# 35. Evaluation Dataset Integrity

Every eval dataset should record:

```text
dataset_id
version
source
query_count
query types
GT representation
verification status
checksum
```

Do not mix incompatible:
- historical Group A;
- internal range labels;
- organizer labels;
- ad hoc manual examples;

under one metric without an explicit compatible contract.

Keep DEV and HOLDOUT distinct.

Do not tune continuously on HOLDOUT.

---

# 36. Failure Taxonomy

Prefer explicit failure tags such as:

```text
QUERY_PARSE_FAILURE
ROUTER_FAILURE
PRUNE_FALSE_NEGATIVE
VIDEO_RANK_FAILURE
REGION_FAILURE
SAMPLING_MISS
VISUAL_ENCODER_MISS
ASR_MISS
OCR_MISS
QWEN_SEMANTIC_MISS
OBJECT_COVERAGE_MISS
FUSION_DEMOTION
TEMPORAL_ORDER_MISS
TEMPORAL_GAP_MISS
RESCUE_MISS
MAPPING_ERROR
MEDIA_RESOLVE_ERROR
EXACT_FRAME_ERROR
GT_OR_PROVENANCE_UNCERTAIN
```

Do not collapse everything into `SEARCH_FAILED`.

---

# 37. Testing Rules

Before modifying code:
- inspect existing test commands;
- inspect nearby tests;
- preserve project conventions.

After modification:

1. run targeted tests first;
2. run broader regression tests if safe;
3. never weaken legitimate tests just to get green output;
4. contract changes require updated/new tests;
5. ordinary unit tests must not trigger expensive model downloads/inference;
6. optional external-data tests must degrade explicitly.

Report exact commands run.

---

# 38. Fail-Open vs Fail-Closed

Optional modality/runtime failure → fail open:

```text
ASR unavailable
OCR unavailable
SigLIP unavailable
Qwen unavailable
BTC Objects unavailable
```

Data-integrity failure → fail closed for affected lane/import:

```text
wrong ID mapping
duplicate stable ID
vector dimension mismatch
vector/metadata row mismatch
checksum mismatch
malformed manifest
unsupported schema
frame convention uncertainty
encoder/index mismatch
ordinal-space mismatch
```

Never trade integrity for availability.

---

# 39. Logging and Provenance

Search/evaluation trace should retain where applicable:

```text
original query
query plan
manual edits
selected lanes
routing/pruning mode
candidate counts by stage
per-lane results
fusion/rescue trace
build IDs
latencies
errors
```

Fused results must remain explainable.

---

# 40. Performance Rules

1. Measure before optimizing.
2. Do not sacrifice recall for latency without evidence.
3. Do not precompute every source frame by default.
4. Decode expensive media only around small candidate sets where possible.
5. Prefer reuse/cache before new preprocessing pipelines.
6. ANN is not automatically superior to exact Flat search at this scale.
7. Keep an exact baseline when practical.

---

# 41. Repository Hygiene

Never commit:

- raw datasets;
- videos;
- keyframes;
- model weights;
- embeddings;
- indexes;
- SQLite databases;
- tokens;
- credentials;
- secrets;
- private absolute paths.

Respect repository ignore/policy rules.

---

# 42. Architecture Change Control

Any frozen-contract change requires:

```text
proposal
→ reason
→ affected artifacts/modules
→ migration/version impact
→ updated tests
→ acceptance evidence
→ rollback plan
```

Never silently alter:
- ID conventions;
- time units;
- frame spaces;
- result schema;
- manifests;
- encoder/index contracts.

---

# 43. Retrieval V2 Dependency Order

Default implementation dependency:

```text
M0  Contract/source-of-truth freeze
M1  Unified Data Hub/mapping
M2  Independent search lanes
M3  Compare + benchmark
M4  Sequence/temporal retrieval
M5  Taxonomy + SAFE pruning
M6  Manual Hybrid + RRF
M7  Query Brain/Assisted
M8  Auto + Global Rescue
M9  Approved Tier-2 optimization/hardening
```

If another roadmap version uses different milestone numbers, preserve the **dependency order**, not the numeric label.

Never jump to Auto/LLM orchestration while earlier gates are incomplete.

---

# 44. Preserve Existing Working Systems

Before Retrieval V2 changes, inspect and reuse existing:

- unified retrieval API;
- provider/orchestrator abstractions;
- evaluation infrastructure;
- media resolver;
- exact-frame APIs;
- Evidence Inspector;
- candidate builder;
- current ASR/visual providers;
- current schema/config patterns.

Do not duplicate them unless reuse is explicitly proven impossible or incompatible.

---

# 45. Closed Audits Stay Closed

Do not re-audit the full corpus merely because implementation begins.

Repeat full audit only when:
- dataset/schema changed;
- source checksum changed;
- canonical mapping materially changed;
- production code reveals a contradiction;
- task explicitly requests it.

Prefer targeted validation.

---

# 46. No Expensive Re-Inference Without Explicit Approval

Do not rerun full-corpus:
- ASR;
- OCR;
- Qwen/VLM;
- SigLIP image encoding;
- BTC feature extraction;

unless explicitly requested and justified by a changed/failed artifact contract.

If source outputs are already valid but a merged artifact is stale:

> rebuild canonical/merged artifacts, not the expensive model output.

---

# 47. Small-Slice Policy for AI Agents

Preferred task shape:

```text
one bounded objective
one explicit allowlist
one acceptance gate
targeted tests
one reversible commit
```

A task should state:
- inputs;
- allowed files;
- forbidden files;
- output artifacts;
- tests;
- acceptance criteria;
- rollback.

If no allowlist is provided, minimize changes anyway.

---

# 48. End-of-Task Report

Every coding task must report:

```text
1. Starting HEAD
2. Final HEAD
3. Files created
4. Files modified
5. Files deleted
6. Files changed outside requested scope
7. Commands/tests executed
8. Test results
9. Data/artifact evidence
10. Acceptance gate status
11. Known limitations
12. Blockers/unknowns
13. Rollback procedure
14. Commit hash if explicitly requested
```

Never report `PASS` without evidence.

---

# 49. Rollback

Every implementation task requires a rollback strategy.

Preferred:
- revert the focused commit;
- delete newly generated derived artifacts;
- restore prior config/schema version.

Do not rely on destructive reset.

---

# 50. STOP Conditions

Immediately stop the affected task when any of these occur:

- source-of-truth conflict;
- unknown frame convention;
- unknown vector model for an existing index;
- vector dimension mismatch;
- vector row/metadata mismatch;
- duplicate stable ID;
- checksum mismatch;
- unexpected raw-data mutation;
- required contract document missing;
- requested task requires forbidden file changes;
- frozen contract would need silent alteration;
- tests expose a contradiction that changes architectural assumptions.

Do not “solve around” the problem.

---

# 51. Final Engineering Rule

The goal is not maximum code volume.

The goal is:

```text
query
→ correct scope
→ GT video survives
→ correct temporal area survives
→ correct evidence enters Top-K
→ operator verifies source video
→ exact physical frame is reproducible
```

If a change makes this harder to audit, harder to reproduce, or easier to silently corrupt, it is not an improvement.
