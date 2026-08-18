# 05 — IMPLEMENTATION, EVALUATION & DELIVERY ROADMAP
## Kế hoạch thi công, benchmark, acceptance gate, ablation và failure explorer cho AIC 2026 Retrieval Workstation

> **Trạng thái:** Design freeze candidate / execution authority.  
> **Vai trò tài liệu:** chuyển toàn bộ kiến trúc ở các file `00`–`04` thành một kế hoạch triển khai có dependency, deliverable, test gate, benchmark và tiêu chí promote rõ ràng.  
> **Nguyên tắc:** **Không promote một thành phần vì “trông có vẻ tốt”; chỉ promote khi có evidence từ benchmark và không phá recall safety.**

---

# 1. Mục tiêu của roadmap

Bộ tài liệu kiến trúc đã xác định các thành phần chính:

- Data Hub / Unified Mapping;
- Query Workspace / Query Brain;
- independent search lanes;
- Compare Mode;
- Sequence / Temporal Retrieval;
- taxonomy + pruning;
- Manual Hybrid;
- Auto Mode;
- fusion + rescue;
- Media Inspector + exact-frame verification;
- evaluation + failure analysis.

Roadmap này quyết định **làm cái gì trước, cái gì sau, cái gì có thể làm song song, và khi nào được xem là hoàn tất**.

Không được biến roadmap thành danh sách task thuần túy. Mỗi milestone phải có:

```text
INPUTS
↓
WORK
↓
ARTIFACTS
↓
TESTS
↓
METRICS
↓
ACCEPTANCE GATE
↓
NEXT DEPENDENCIES
```

---

# 2. Ba loại trạng thái cần phân biệt

Mọi task, artifact, policy và benchmark nên có một trong ba trạng thái:

## 2.1 VERIFIED

Đã được audit hoặc test bằng dữ liệu thật.

Ví dụ:

```text
873 videos
116,767 custom keyframes
116,587 Qwen records mapped
BTC map/keyframe/CLIP/media coverage theo audit
ASR corpus theo audit
```

## 2.2 DESIGN DECISION

Quyết định kiến trúc nhưng chưa phải kết quả benchmark.

Ví dụ:

```text
Independent lanes
Late fusion
Pruning modes OFF / SAFE / AGGRESSIVE
RRF as first fusion baseline
Sequence max_gap seed = 60s
```

## 2.3 EXPERIMENTAL

Một giá trị hoặc công nghệ cần test trước khi dùng production.

Ví dụ:

```text
Top-K = 100
router threshold = 0.88
HNSW vs FlatIP
reranker top 50
specific RRF k
specific temporal gap penalty
```

Không được ghi experimental number vào code rồi gọi nó là “production policy” nếu chưa benchmark.

---

# 3. Delivery strategy tổng thể

Kiến trúc được triển khai theo bốn tầng trưởng thành:

```text
LEVEL 0 — DATA CORRECTNESS
        mapping đúng trước

LEVEL 1 — SINGLE-LANE RETRIEVAL
        từng nguồn search riêng

LEVEL 2 — TEMPORAL + MANUAL HYBRID
        operator phối hợp có kiểm soát

LEVEL 3 — AUTO ORCHESTRATION
        brain + pruning + fusion + rescue
```

Điều này tránh tình trạng:

```text
LLM + taxonomy + SigLIP + ASR + OCR + Qwen + CLIP
                    ↓
               1 pipeline lớn
                    ↓
           fail nhưng không biết vì sao
```

Thay vào đó:

```text
mỗi lane có benchmark riêng
        ↓
Compare Mode
        ↓
biết failure source
        ↓
chỉ sau đó mới fusion
```

---

# 4. Dependency graph

```text
M0  Design Freeze
 │
 ▼
M1  Data Registry + Mapping Core
 │
 ├─────────────┬────────────┬───────────────┐
 ▼             ▼            ▼               ▼
M2 SigLIP   M3 BTC CLIP   M4 Text lanes   M5 Semantic/Object lanes
                              │               │
                              └──────┬────────┘
                                     ▼
                              M6 Compare Mode
                                     │
                     ┌───────────────┼───────────────┐
                     ▼               ▼               ▼
                M7 Sequence      M8 Pruning      M9 Inspector polish
                     │               │               │
                     └───────────────┼───────────────┘
                                     ▼
                              M10 Manual Hybrid
                                     │
                                     ▼
                               M11 Query Brain
                                     │
                                     ▼
                             M12 Fusion + Rescue
                                     │
                                     ▼
                              M13 Hardening/Freeze
```

Một milestone ở bên phải không được âm thầm thay đổi data contract của milestone bên trái.

Nếu cần schema migration:

```text
propose
→ version bump
→ migration note
→ rebuild derived
→ rerun validation
```

---

# 5. M0 — Architecture & Contract Freeze

## 5.1 Mục tiêu

Khóa các invariant để các thành viên có thể làm song song mà không tự tạo contract riêng.

## 5.2 Phải khóa

### Identity

```text
video_id
frame_space
frame_id
frame_idx
timestamp_ms
region_id
lane_id
build_id
```

### Frame spaces

```text
BTC != CUSTOM != SOURCE_VIDEO_FRAME
```

### Search result contract

Tất cả lane phải trả tối thiểu:

```json
{
  "lane": "siglip_custom",
  "query_id": "...",
  "video_id": "L21_V001",
  "evidence_type": "FRAME",
  "frame_space": "CUSTOM",
  "frame_id": "...",
  "frame_idx": 426,
  "timestamp_ms": 14200,
  "raw_score": 0.83,
  "rank": 4,
  "build_id": "..."
}
```

Text result có thể thay frame bằng window:

```text
start_ms
end_ms
text_ref
```

### Time unit

Canonical:

```text
integer milliseconds
```

### Path

Canonical:

```text
relative paths
```

Runtime resolver mới ghép root.

## 5.3 Deliverables

- versioned contract;
- schema list;
- source registry schema;
- result contract schema;
- frame-space contract;
- migration policy;
- architecture decision log.

## 5.4 Acceptance gate

PASS khi:

- mọi thành viên đọc cùng một contract;
- không còn ambiguity về BTC/custom frame IDs;
- result lane nào cũng có thể quy về `video + time`;
- không có absolute-path dependency trong canonical spec;
- raw data được xác nhận immutable.

---

# 6. M1 — Unified Data Hub & Mapping Core

Đây là milestone quan trọng nhất trước search.

## 6.1 Mục tiêu

Từ bất kỳ `video_id`, BTC keyframe hoặc custom keyframe nào, hệ thống có thể truy ngược tới các nguồn liên quan.

## 6.2 Ingest order

```text
1. video catalog
2. source registry
3. BTC map-keyframes
4. BTC keyframe catalog
5. custom keyframe catalog
6. media-info
7. ASR
8. Qwen
9. OCR metadata/vector refs
10. BTC objects
11. visual vector row maps
12. taxonomy refs
```

## 6.3 Runtime tables tối thiểu

### `videos`

```text
video_id PK
ordinal
series
duration_ms
source_relpath
flags
```

### `btc_keyframes`

```text
btc_frame_id PK
video_id FK
n
frame_idx
timestamp_ms
fps
image_relpath
clip_row
```

### `custom_keyframes`

```text
custom_frame_id PK
video_id FK
source_keyframe_id
frame_idx
timestamp_ms
shot_id
image_relpath
siglip_row
qwen_status
```

### `asr_segments`

```text
segment_id PK
video_id FK
start_ms
end_ms
text
source_ref
```

### `ocr_records`

```text
ocr_id PK
video_id FK
frame_space
frame_id
frame_idx?
timestamp_ms?
raw_text
normalized_text
bbox
confidence
vector_ref
```

### `qwen_semantics`

```text
custom_frame_id FK
objects
attributes
spatial_relations
counts
scene
visible_actions
caption
raw_ref
```

### `media_info`

```text
video_id PK/FK
title
description
keywords
author
publish_date
...
```

### `btc_objects`

Có thể materialize theo detection hoặc giữ raw JSON + derived compact table.

## 6.4 Mapping checks

### Video integrity

```text
canonical videos = 873
unique = 873
unknown refs = 0
```

### Custom

```text
all custom keyframes map to known video
all Qwen success rows map exactly one custom keyframe
Qwen missing rows remain explicit MISSING
```

### BTC

```text
map CSV n ↔ image filename
map CSV row ↔ CLIP row
object file ↔ BTC keyframe
all video IDs known
```

### OCR

Không giả định OCR audit schema là tuyệt đối nếu dataset thật có variant.

Validator phải kiểm tra thực tế:

```text
metadata length == embedding rows
video_id known
frame reference resolvable or marked unresolved
bbox valid if present
confidence parsed if present
```

## 6.5 Data Hub API nội bộ

Nên có các primitive:

```text
get_video(video_id)
get_btc_frame(frame_id)
get_custom_frame(frame_id)
get_nearest_btc_frame(video_id, timestamp_ms)
get_nearest_custom_frame(video_id, timestamp_ms)
get_asr_window(video_id, start_ms, end_ms)
get_qwen(frame_id)
get_ocr(frame_id/time)
resolve_source_frame(video_id, frame_idx or timestamp_ms)
```

## 6.6 Acceptance gate M1

Không được sang “Auto Brain” khi M1 chưa PASS.

PASS khi:

```text
873/873 videos resolvable
BTC frame mapping validated
Custom frame mapping validated
Qwen mapping validated
OCR shard/vector alignment validated
ASR timelines valid
No unknown video IDs
No hidden absolute-path requirement
No index row without mapping
```

## 6.7 Artifact output

```text
mapping.sqlite
source_registry.json
mapping_validation_report.json
mapping_validation_report.md
checksums.sha256
build_manifest.json
```

---

# 7. M2 — Custom SigLIP2 Lane

## 7.1 Mục tiêu

Có một visual lane độc lập hoàn chỉnh:

```text
text query
→ exact SigLIP2 text preprocessing
→ query vector
→ custom image vector index
→ Top-K custom frames
→ canonical result contract
```

## 7.2 Test bắt buộc

### Encoder compatibility

Query phải dùng đúng model/preprocessing contract của image vectors.

Kiểm tra:

```text
model id
processor config
max_length
padding
normalization
similarity metric
```

### Index integrity

```text
vector row count == custom frame mapping row count
vector dimension exact
no NaN
self/query smoke tests
```

### Search tests

- simple object query;
- scene query;
- attribute query;
- composed visual query;
- long query truncation behavior;
- Vietnamese vs English reformulation;
- filters by video set.

## 7.3 Benchmark

Report:

```text
video Recall@K
frame Recall@K
first_correct_rank
latency
candidate diversity
```

Không cần fusion.

## 7.4 Acceptance

PASS nếu:

- deterministic encode/index behavior;
- mapping không sai row;
- filtered search vẫn đúng;
- có benchmark baseline lưu artifact.

---

# 8. M3 — BTC CLIP Lane

## 8.1 Mục tiêu

Giữ BTC visual search như một lane độc lập và sau này làm global rescue.

```text
query
→ OpenAI CLIP ViT-B/32 compatible text encoder
→ BTC CLIP 512D
→ Top-K BTC frames
```

## 8.2 Validation đặc biệt

BTC vectors phải map chính xác:

```text
.npy row i
↔ map-keyframes row i
↔ BTC image n
```

Không suy luận bằng filename nếu audit chưa đủ; build validator xác nhận.

## 8.3 Benchmark

Chạy cùng query set với SigLIP để tạo **ablation độc lập**, không phải để tuyên bố model nào luôn tốt hơn.

Report:

```text
SigLIP only
BTC CLIP only
hits unique to SigLIP
hits unique to BTC
both hit
both miss
```

Đây là cơ sở định lượng cho quyết định dùng BTC CLIP làm rescue.

---

# 9. M4 — Text Retrieval Lanes: ASR + OCR + Metadata

Ba lane có thể dùng chung hạ tầng text nhưng không nên mất identity riêng.

---

## 9.1 ASR lane

### Tier 1

```text
FTS/BM25 lexical
+
BGE-M3 dense semantic
```

Có thể giữ hai sub-results riêng trước:

```text
asr_lexical
asr_dense
```

Sau benchmark mới RRF nội bộ.

### Query cases

- named entities;
- phrase spoken in video;
- topic/event queries;
- Vietnamese paraphrases;
- numbers/dates;
- news story content.

### Result

ASR trả temporal windows, không giả làm exact frame.

```text
video_id
start_ms
end_ms
text
rank
```

---

## 9.2 OCR lane

OCR cần khác ASR vì raw text có noise.

### Tier 1 retrieval

```text
normalized exact tokens
+
FTS/BM25
+
trigram/fuzzy support
+
optional existing OCR embeddings
```

### OCR normalization phải reversible

Lưu:

```text
raw_text
normalized_text
search_text
```

Không overwrite raw.

### Confidence policy

Confidence threshold là experimental.

Không hard delete toàn bộ low-confidence OCR ở canonical layer.

Nên:

```text
canonical keeps record
runtime search may downweight/filter based on policy
```

### Benchmark buckets

- exact proper noun;
- Vietnamese diacritics corruption;
- numbers;
- short labels;
- cooking ingredients;
- lower-third name/title;
- scene signage.

---

## 9.3 Media-info lane

### Role

Video-level prior/search, không frame truth.

Search fields:

```text
title
description
keywords
author
publish_date
```

### Use cases

- program recognition;
- episode/date hints;
- high-level topic;
- channel/source.

### Guardrail

Không được nói:

```text
keyword found in media-info
⇒ exact frame contains it
```

---

# 10. M5 — Semantic / Structured Evidence Lanes

## 10.1 Qwen lane

Qwen raw semantic fields hiện có phải được khai thác theo đúng evidence level.

Possible sub-lanes:

```text
qwen_caption
qwen_objects
qwen_attributes
qwen_scene
qwen_visible_actions
qwen_relations
qwen_counts
```

Không cần implement tất cả ngay.

### Tier 1

- raw caption lexical/dense search;
- normalized facet postings;
- exact/raw string matching for useful terms;
- video/frame aggregation.

### Important

`visible_actions` = visual observation tại frame.

Không tự nâng thành “temporal action confirmed”.

## 10.2 BTC Object lane

Object detector phù hợp cho:

```text
Person
Car
Bowl
Food
Chair
...
```

Dùng confidence thật của detector.

Không dùng missing detection như hard negative.

### Tier 1

```text
normalized class dictionary
→ postings per BTC frame
→ optional video-level support bitmap
```

### Tier 2

spatial/bbox reasoning đơn giản:

```text
left/right
large/small
count by class
co-occurrence
```

Nhưng chỉ khi query benchmark chứng minh giá trị.

---

# 11. M6 — Compare Mode & Lane Diagnostics

Đây là milestone bắt buộc trước fusion.

## 11.1 UI behavior

Một query có thể chạy:

```text
SigLIP
BTC CLIP
Qwen
ASR
OCR
BTC Object
Metadata
```

và hiển thị song song.

## 11.2 Metrics per query

```text
GT video rank
GT frame rank / overlap
first correct rank
latency
candidate count
```

## 11.3 Failure tags

Ví dụ:

```text
SIGLIP_VISUAL_MISS
BTC_CLIP_VISUAL_MISS
ASR_NO_SPEECH_EVIDENCE
OCR_TEXT_CORRUPTION
QWEN_MISSING_FRAME
QWEN_SEMANTIC_MISS
OBJECT_VOCAB_LIMIT
MAPPING_ERROR
```

## 11.4 Why Compare Mode is a release gate

Không có Compare Mode thì fusion failure khó giải thích.

PASS M6 khi team trả lời được bằng số liệu:

> “Query này fail vì lane nào?”

chứ không chỉ:

> “Search chưa tốt.”

---

# 12. M7 — Temporal / Sequence Engine

Sequence engine phải được benchmark độc lập trước khi để LLM tự chia query.

## 12.1 Manual sequence first

Operator nhập:

```text
Step A
Step B
Step C
```

Mỗi step chọn lane hoặc Auto-Lane nhẹ.

## 12.2 Constraints

```text
same_video = true/false
strict_order = true/false
min_gap_ms
max_gap_ms
max_span_ms
same_region optional
```

`60s` chỉ là seed cho “sau đó gần”, không phải truth.

## 12.3 Output groups

Không chỉ full match.

Phải giữ:

```text
FULL_MATCH
PREFIX_MATCH
SUFFIX_MATCH
PARTIAL_MATCH
STEP_ONLY_MATCH
```

Ví dụ A→B:

```text
A+B valid gap
A-only
B-only
A+B wrong gap
```

UI có thể hiển thị tách section.

## 12.4 Scoring dimensions

```text
step retrieval ranks
coverage ratio
temporal order correctness
gap plausibility
compactness
lane support
```

Không cần neural temporal model ở V1.

## 12.5 Acceptance

Benchmark query temporal phải đo:

```text
correct video Recall@K
full-sequence Recall@K
partial-match utility
gap error
order error
```

---

# 13. M8 — Taxonomy & Pruning

Pruning không được build như một boolean gate duy nhất.

## 13.1 Modes

### OFF

Search toàn corpus/index space.

Dùng làm baseline và rescue reference.

### SAFE

Taxonomy tạo priority candidate set nhưng không loại bỏ hoàn toàn global route.

Conceptually:

```text
priority pool
+
small global escape
```

### AGGRESSIVE

Harder intersection/filtering chỉ cho branch đã benchmark đủ.

## 13.2 Benchmark principle

Metric quan trọng nhất:

```text
GT survival after pruning
```

Không phải:

```text
candidate count càng nhỏ càng tốt
```

## 13.3 Pruning report

Cho mỗi query:

```text
before_count
after_count
prune_fraction
GT_survived
router branches
router scores
evidence families
escape used?
```

## 13.4 Branch-level calibration

Không dùng một threshold cho mọi branch.

Ví dụ:

```text
Education subject
```

có thể mạnh hơn generic:

```text
Food
Person
Outdoor
```

## 13.5 Acceptance

SAFE mode chỉ được default khi:

- GT survival đạt mục tiêu đã thống nhất;
- failure cases được hiểu;
- global escape có tác dụng đo được;
- candidate reduction có ý nghĩa.

Nếu không, default vẫn OFF.

---

# 14. M9 — Media Inspector Hardening

Phần media đã có foundation, nhưng milestone này biến nó thành công cụ thi đấu đáng tin.

## 14.1 Result → video navigation

Click result:

```text
video_id + timestamp
→ media resolver
→ video seek
```

## 14.2 Controls

Temporal:

```text
-10s
-3s
+3s
+10s
```

Exact frame:

```text
-10f
-3f
-1f
+1f
+3f
+10f
```

Không trộn hai khái niệm.

## 14.3 Nearest-keyframe fallback

Nếu target timestamp không có custom/BTC keyframe:

```text
nearest before
nearest after
nearest absolute
```

phải có thể hiển thị.

## 14.4 Exact source frame

Khi operator cần frame thật:

```text
video source
→ exact-frame endpoint
→ JPEG
```

Keyframe không phải authority cuối.

## 14.5 Heavy-video strategy

Không preload toàn bộ video.

Tier 1:

```text
HTTP Range streaming
seek by timestamp
server exact-frame extraction
nearby keyframe strip
```

Tier 2 nếu cần:

```text
short proxy preview clips
server-side thumbnail neighborhood cache
```

## 14.6 Acceptance

- click result seek đúng vùng;
- frame stepping deterministic;
- exact-frame extraction reproducible;
- source path không leak bất hợp lý;
- failure không crash cả UI;
- latency đủ cho operator workflow.

---

# 15. M10 — Manual Hybrid

Đây là fusion đầu tiên nên đưa vào production-like workflow.

## 15.1 Operator chooses lanes

Ví dụ:

```text
☑ SigLIP
☑ Qwen
☐ ASR
☑ OCR
☐ BTC CLIP
```

## 15.2 Fusion baseline

Tier 1:

```text
RRF on ranks
```

Lý do:

- raw scores khác scale;
- dễ debug;
- reproducible;
- support missing lane naturally.

## 15.3 Fusion unit

Không nhất thiết fusion trực tiếp frame IDs vì BTC/custom spaces khác nhau.

Có thể fusion theo:

```text
video-level
```

hoặc canonical temporal evidence:

```text
video_id + temporal neighborhood
```

Sau đó chọn representative frame.

## 15.4 Acceptance

Manual Hybrid được promote khi:

```text
RRF >= best single lane on useful query subsets
```

hoặc ít nhất tăng robustness mà không làm tụt đáng kể overall recall.

Ablation phải giữ.

---

# 16. M11 — Query Brain

Chỉ sau khi lanes và modes đã ổn mới để Brain orchestration.

## 16.1 Query Brain tasks

```text
preserve original query
identify program/topic hints
extract objects
extract attributes
extract actions
extract scenes
extract text/OCR hints
extract ASR/narrative hints
detect temporal intent
suggest lanes
suggest pruning mode
```

## 16.2 Structured output contract

Ví dụ:

```json
{
  "original_query": "...",
  "program_hints": [],
  "topic_hints": [],
  "facets": {
    "objects": [],
    "attributes": [],
    "actions": [],
    "scenes": [],
    "visible_text": [],
    "spoken_text": []
  },
  "temporal": {
    "enabled": false,
    "steps": []
  },
  "recommended_lanes": [],
  "recommended_pruning": "SAFE"
}
```

## 16.3 Human override

UI bắt buộc cho operator:

```text
add/remove facet
edit translated term
select/unselect lane
change Program/Topic
change sequence order/gap
change pruning mode
```

## 16.4 Brain evaluation

Không chỉ đo “JSON parse success”.

Cần labeled decomposition sample:

```text
object extraction accuracy
action extraction
OCR-intent detection
ASR-intent detection
temporal intent detection
program/topic suggestion
lane recommendation utility
```

## 16.5 Guardrail

LLM/router output không được một mình hard prune ở default mode.

---

# 17. M12 — Auto Fusion + Global Rescue

Auto Mode là orchestration layer, không phải search algorithm mới.

## 17.1 Auto flow

```text
query
↓
brain
↓
SAFE routing
↓
selected lanes
↓
independent retrieval
↓
video/temporal aggregation
↓
RRF baseline
↓
confidence / disagreement check
↓
optional rescue
↓
final top-K
```

## 17.2 Rescue triggers

Seed conditions có thể gồm:

```text
low fusion support
strong lane disagreement
few candidates
no evidence family consensus
pruning uncertainty
sequence partial-only
```

Các threshold cần benchmark.

## 17.3 Rescue lanes

Tier 1 candidates:

```text
BTC CLIP global
custom SigLIP global
ASR global
```

Có thể thêm OCR/Qwen depending query.

## 17.4 Acceptance

Auto phải được so với:

```text
best single lane
manual hybrid baseline
global no-prune baseline
```

Nếu Auto không hơn hoặc ít nhất không robust hơn, không được coi là default chỉ vì “tự động”.

---

# 18. M13 — Competition Hardening & Freeze

## 18.1 Freeze artifacts

```text
build manifest
checksums
SQLite DB
FAISS indexes
FTS indexes
bitsets/postings
model IDs
processor configs
routing policy
fusion policy
UI build
```

## 18.2 Startup checks

Fail closed khi:

```text
checksum mismatch
schema mismatch
ordinal mismatch
index row mismatch
missing mandatory artifact
```

Lane optional có thể `UNAVAILABLE`, nhưng UI phải báo rõ.

## 18.3 Rehearsal

Chạy full workflow:

```text
query
→ results
→ inspect
→ exact frame
→ candidate build
→ submission-like action
```

## 18.4 Freeze rule

Sau freeze:

- không upgrade model vô cớ;
- không thay threshold mà không rerun benchmark;
- không rebuild index từ source khác checksum;
- bug fix phải có regression tests.

---

# 19. Evaluation dataset architecture

Không dùng một tập query duy nhất cho mọi mục đích.

## 19.1 DEV

Dùng để:

- debug;
- tune thresholds;
- build failure taxonomy;
- iterate.

## 19.2 HOLDOUT

Không dùng để tune hàng ngày.

Dùng để kiểm tra generalization của policy.

## 19.3 QUERY BUCKETS

Nên gắn nhãn query theo loại:

```text
visual_object
visual_attribute
action
scene
spatial_relation
count
OCR
ASR
named_entity
program
metadata
temporal_2step
temporal_multistep
mixed_modality
ambiguous
```

Một query có thể multi-label.

## 19.4 Difficulty buckets

```text
EASY
MEDIUM
HARD
```

hoặc bằng evidence availability:

```text
single-lane sufficient
requires cross-modal
requires temporal
requires rescue
```

---

# 20. Ground Truth representation

GT không chỉ là một frame duy nhất nếu challenge semantics cho phép range.

Schema cần support:

```text
query_id
video_id
acceptable_frame_ranges[]
acceptable_time_ranges[]
query_type
notes
```

Temporal query có thể thêm:

```text
steps[]
step_ranges[]
order
max_gap? as annotation if known
```

Scoring contract phải được freeze riêng.

---

# 21. Metrics hierarchy

Không tối ưu một metric duy nhất.

## 21.1 Video retrieval

```text
Video Recall@1/5/10/20/50/100
First correct video rank
```

## 21.2 Frame retrieval

```text
Frame/Range Recall@K
First correct frame rank
```

## 21.3 Temporal

```text
Sequence video Recall@K
Full sequence Recall@K
Step coverage
Order accuracy
Gap validity
```

## 21.4 Pruning

```text
GT survival
candidate reduction
false-negative prune rate
escape rescue rate
```

## 21.5 Fusion

```text
best single lane vs fusion
unique rescue wins
fusion demotion failures
```

## 21.6 Operational

```text
p50/p95 latency
search-stage latency
inspector seek latency
exact-frame latency
error rate
```

Không dùng latency để che recall regression.

---

# 22. Benchmark contract

Mọi benchmark run phải ghi:

```text
run_id
code revision
artifact build IDs
model IDs
processor configs
query dataset checksum
routing policy
pruning mode
lane config
K values
fusion config
timestamp
```

Output per query:

```text
query_id
query text
query plan
candidate videos
pruning trace
lane results
fused results
rescue results
GT comparison
latencies
failure tags
```

Summary:

```text
overall metrics
by query bucket
by series
by program
by lane
by pruning mode
```

---

# 23. Ablation matrix bắt buộc

Đây là cách quyết định feature có đáng giữ không.

## 23.1 Single lane

```text
SigLIP only
BTC CLIP only
Qwen only
ASR only
OCR only
BTC Object only
Metadata only
```

## 23.2 Hybrid

```text
SigLIP + Qwen
SigLIP + BTC CLIP
ASR + OCR
Qwen + OCR
SigLIP + Qwen + OCR
all useful lanes
```

## 23.3 Pruning

```text
OFF
SAFE
AGGRESSIVE
```

## 23.4 Rescue

```text
no rescue
visual rescue
ASR rescue
multi-rescue
```

## 23.5 Temporal

```text
independent steps only
same-video grouping
ordered grouping
ordered + gap
ordered + gap + region
```

## 23.6 Reranking

```text
no reranker
text reranker top-N
video-profile rerank
```

Tier 2 chỉ promote nếu ablation chứng minh gain đủ lớn so với complexity.

---

# 24. Failure Explorer

Failure Explorer không phải optional dev luxury; nó là công cụ để đội cải thiện hệ thống.

## 24.1 Mỗi failure cần trả lời

```text
GT video có bị prune không?
GT frame có trong index không?
lane nào retrieve được?
lane nào miss?
fusion có demote không?
rescue có tìm được không?
sequence constraint có quá chặt không?
query decomposition có sai không?
```

## 24.2 Failure taxonomy đề xuất

### Data / mapping

```text
DATA_MISSING
MAPPING_ORPHAN
WRONG_FRAME_SPACE
WRONG_VECTOR_ROW
TIMESTAMP_MISMATCH
```

### Query understanding

```text
QUERY_BAD_DECOMPOSITION
QUERY_WRONG_TOPIC
QUERY_WRONG_OBJECT
QUERY_TEMPORAL_NOT_DETECTED
QUERY_OVER_TRUNCATED
```

### Pruning

```text
VIDEO_PRUNED_FALSE_NEGATIVE
BRANCH_TOO_BROAD
BRANCH_TOO_NARROW
RESCUE_NOT_TRIGGERED
```

### Lane

```text
SIGLIP_MISS
BTC_CLIP_MISS
QWEN_MISS
ASR_MISS
OCR_MISS
BTC_OBJECT_MISS
METADATA_MISS
```

### Fusion

```text
FUSION_DEMOTION
FUSION_NO_CONSENSUS
WEIGHTING_BIAS
```

### Temporal

```text
SEQUENCE_STEP_MISS
SEQUENCE_ORDER_FAIL
SEQUENCE_GAP_TOO_STRICT
SEQUENCE_GAP_TOO_LOOSE
CROSS_EVENT_FALSE_MATCH
```

### Inspector

```text
VIDEO_SEEK_FAIL
EXACT_FRAME_FAIL
MEDIA_PATH_FAIL
```

## 24.3 Failure review loop

```text
query fails
↓
assign failure tag
↓
cluster repeated failures
↓
propose one change
↓
run ablation
↓
accept/reject
```

Không sửa nhiều subsystem cùng lúc nếu muốn biết cái gì tạo gain.

---

# 25. Acceptance gates tổng hợp

## Gate A — Data correctness

- canonical corpus correct;
- source registry complete;
- no unknown IDs;
- vector row mapping valid;
- Qwen/OCR/ASR mapping validated.

## Gate B — Independent lanes

- every production lane searchable alone;
- deterministic results under same build;
- benchmark artifacts saved;
- UI/CLI can inspect lane independently.

## Gate C — Compare diagnostics

- per-lane results visible;
- GT rank report generated;
- failure tags useful.

## Gate D — Temporal

- manual sequence 2–5 steps works;
- same-video/order/gap constraints correct;
- partial matches surfaced.

## Gate E — Safe pruning

- GT survival meets agreed target;
- OFF baseline retained;
- rescue path exists.

## Gate F — Hybrid

- fusion has ablation evidence;
- score spaces not naively summed;
- source lanes remain visible.

## Gate G — Auto

- brain output editable;
- routing trace shown;
- Auto compared against manual/global baselines.

## Gate H — Competition readiness

- exact-frame flow stable;
- build reproducible;
- startup validation strict;
- full rehearsal completed.

---

# 26. Parallel work plan cho team

Sau M0/M1 contract freeze, các lane có thể chia song song.

```text
TEAM / WORKSTREAM A
SigLIP lane

TEAM / WORKSTREAM B
ASR + text infrastructure

TEAM / WORKSTREAM C
OCR

TEAM / WORKSTREAM D
Qwen semantic + facet normalization

TEAM / WORKSTREAM E
BTC CLIP + BTC Objects + media-info

TEAM / WORKSTREAM F
UI Compare / Inspector
```

Nhưng tất cả phải dùng:

```text
same video IDs
same timestamp units
same result schema
same data hub resolver
same benchmark runner
```

Không cho mỗi lane tự định nghĩa:

```text
video path
frame id
score output
result JSON
```

---

# 27. Definition of Done cho một search lane

Một lane chưa “xong” chỉ vì query trả được Top-K.

DONE khi có đủ:

1. **Source contract** — biết dữ liệu nào nó dùng.
2. **Encoder/search contract** — model/preprocessing/index exact.
3. **Mapping contract** — result về được video/time/frame.
4. **Filter support** — candidate video set nếu lane hỗ trợ.
5. **Deterministic tests**.
6. **Benchmark**.
7. **Failure tags**.
8. **Capabilities/health status**.
9. **UI/CLI inspectability**.
10. **Provenance/build ID**.

---

# 28. Definition of Done cho Query Mode

Ví dụ Sequence Mode DONE khi:

- query input contract rõ;
- manual mode chạy được không cần LLM;
- lane assignments được chọn;
- temporal constraints hoạt động;
- partial matches giữ lại;
- result trace giải thích được;
- benchmark temporal riêng;
- UI click về inspector.

Auto Mode DONE khi:

- manual modes vẫn hoạt động;
- brain parse structured;
- operator override;
- routing trace;
- no invisible hard pruning;
- benchmark vs manual baseline.

---

# 29. Tier promotion policy

Công nghệ Tier 2 không được thêm chỉ vì mới hơn hoặc mạnh trên benchmark ngoài project.

Promote khi:

```text
measurable project gain
+
acceptable complexity
+
reproducible build
+
failure behavior understood
```

Ví dụ:

## HNSW promote nếu

- FlatIP latency không đạt target;
- recall loss acceptable;
- build/memory complexity worth it.

## Reranker promote nếu

- Top-K contains GT but ordering poor;
- reranker improves first-correct-rank consistently.

## Qdrant/OpenSearch/Vespa/etc promote nếu

- current local stack becomes operational bottleneck;
- feature need is concrete, not hypothetical.

## Sparse BGE-M3 promote nếu

- lexical+dense gap remains;
- sparse improves relevant query buckets.

---

# 30. Release channels đề xuất

## `dev`

- fast iteration;
- experimental indexes;
- loose compatibility allowed with version tags.

## `candidate`

- all checksums pinned;
- eval pass required;
- no schema drift.

## `competition`

- frozen artifacts;
- only critical bug fixes;
- full rehearsal pass.

---

# 31. Regression test suite

Mỗi release candidate cần chạy:

## Data tests

```text
video counts
ID uniqueness
foreign keys
index rows
mapping integrity
```

## Lane tests

```text
known query → expected result presence
filter behavior
empty query validation
invalid lane handling
```

## Temporal tests

```text
A before B
B before A rejected in strict mode
max-gap respected
partial results preserved
```

## Media tests

```text
range stream
seek
authority exact frame
± frame controls
path traversal guard
```

## API tests

```text
partial lane failure
UNAVAILABLE lane
capabilities
schema compatibility
```

## UI tests

```text
query edit
mode switch
result inspect
sequence cards
candidate builder
```

---

# 32. Observability & trace requirements

Trong dev/benchmark mode, mọi search nên có trace:

```text
query_id
mode
query plan
candidate-video transitions
lane start/end
lane result counts
fusion input ranks
rescue trigger
final ranks
latency breakdown
```

Production/competition UI không nhất thiết show tất cả, nhưng debug panel nên truy cập được.

Một result card nên có evidence badges:

```text
SIGLIP #3
QWEN #7
OCR HIT
ASR WINDOW
BTC CLIP #12
```

để operator hiểu vì sao result lên cao.

---

# 33. Query log & session snapshot

Operator workflow cần lưu:

```text
original query
edited facets
selected modes
pruning mode
sequence constraints
pinned results
rejected results
confirmed candidate
```

Mục tiêu:

- không mất tiến trình khi thử nhiều query;
- có thể quay lại một search tốt;
- dùng logs để cải thiện benchmark/failure corpus.

Session log không được làm thay đổi canonical data.

---

# 34. Phased UI delivery

## UI Phase 1

```text
Single Lane Search
Result cards
Inspector
```

## UI Phase 2

```text
Compare Mode
lane tabs
query history
```

## UI Phase 3

```text
Structured facets
Manual Hybrid
pruning switch
```

## UI Phase 4

```text
Sequence Builder
step cards
gap controls
partial/full sections
```

## UI Phase 5

```text
Auto Brain
query plan preview
editable decomposition
rescue trace
```

Không chờ Auto Mode mới làm UI hữu ích.

---

# 35. Milestone deliverable table

| Milestone | Output chính | Không phụ thuộc | Phụ thuộc bắt buộc | Gate |
|---|---|---|---|---|
| M0 | Frozen contracts | model tuning | current audits/specs | Contract PASS |
| M1 | Mapping SQLite + registry | fusion | M0 | Mapping PASS |
| M2 | SigLIP lane | Query Brain | M1 | Lane benchmark |
| M3 | BTC CLIP lane | Query Brain | M1 | Lane benchmark |
| M4 | ASR/OCR/metadata lanes | fusion | M1 | Text benchmark |
| M5 | Qwen/BTC Object lanes | fusion | M1 | Semantic benchmark |
| M6 | Compare Mode | Auto | M2–M5 enough lanes | Diagnostic PASS |
| M7 | Sequence | LLM decomposition | M6/results contract | Temporal PASS |
| M8 | Pruning | fusion | M1 + taxonomy | GT survival PASS |
| M9 | Inspector hardening | Auto | M1 | Media PASS |
| M10 | Manual Hybrid | LLM | M6 | Ablation PASS |
| M11 | Query Brain | new indexes | M6–M10 | Brain eval |
| M12 | Auto+Rescue | new preprocessing | M11 | Auto eval |
| M13 | Freeze | experimentation | all required | Rehearsal PASS |

---

# 36. Recommended execution order thực tế

Nếu cần một thứ tự duy nhất để follow:

```text
STEP 01
Freeze result + mapping contracts

STEP 02
Finish Data Hub validator

STEP 03
Bring up SigLIP lane

STEP 04
Bring up BTC CLIP lane

STEP 05
Bring up ASR lexical+dense

STEP 06
Bring up OCR lexical/fuzzy + existing embeddings

STEP 07
Bring up Qwen caption/facet search

STEP 08
Bring up BTC Object + Media-info

STEP 09
Build Compare Mode + benchmark runner

STEP 10
Run real BTC query ablations

STEP 11
Build manual Sequence Mode

STEP 12
Benchmark sequence constraints

STEP 13
Materialize SAFE taxonomy pruning

STEP 14
Measure GT survival

STEP 15
Build Manual Hybrid RRF

STEP 16
Harden Inspector / exact frame

STEP 17
Build editable Query Brain

STEP 18
Auto orchestration + Rescue

STEP 19
Full regression + holdout

STEP 20
Competition freeze + rehearsal
```

---

# 37. What should NOT block initial progress

Không cần đợi những thứ sau hoàn hảo mới chạy single lanes:

```text
perfect taxonomy
perfect temporal regions
perfect Qwen normalization
full Auto Brain
neural fusion
final hard-prune thresholds
```

Architecture phải degrade gracefully:

```text
region missing
→ search video frames directly

Qwen missing
→ other lanes continue

OCR unavailable
→ capability marked unavailable

pruning uncertain
→ OFF/SAFE
```

---

# 38. What MUST block progress

Có những lỗi không được “chạy tạm”:

```text
unknown vector-row mapping
wrong frame-space mapping
checksum mismatch
video_id orphan
wrong query encoder for vector space
non-deterministic frame identity
fake confidence inserted into canonical data
```

Các lỗi này phá nền tảng và sẽ làm benchmark vô nghĩa.

---

# 39. Final technology rollout decision

## Tier 1 — triển khai trước

```text
SQLite canonical/runtime metadata
SQLite FTS/BM25
trigram/fuzzy OCR support
FAISS vector indexes
SigLIP2 custom visual lane
BTC CLIP lane
BGE-M3 text dense lane
Qwen normalized facets/caption
BTC Object postings
fixed video bitsets
RRF late fusion
source-video exact frame
```

## Tier 2 — chỉ thêm sau benchmark

```text
BGE-M3 sparse/hybrid
HNSW where needed
cross-encoder/reranker top-N
region-level vector indexes
Qdrant/OpenSearch/Vespa-class server if concrete need
proxy preview clips
learned fusion
```

## Tier 3 — experimental / không ưu tiên

```text
single giant multimodal vector
end-to-end LLM agent controlling all search silently
online Qwen over every candidate frame
hard pruning from one weak signal
complex distributed vector infrastructure without measured need
```

---

# 40. Final architecture acceptance statement

Hệ thống được xem là đạt architecture objective khi một operator có thể:

1. nhập query tự nhiên hoặc structured;
2. chạy một lane riêng để debug;
3. chạy Compare để hiểu nguồn nào mạnh/yếu;
4. dùng Sequence nếu query có trước/sau;
5. bật/tắt pruning;
6. chạy Manual Hybrid;
7. xem Auto Brain phân tích query và sửa nó;
8. nhận final results có evidence trace;
9. click vào result và mở đúng video/timestamp;
10. xem neighboring frames/timeline;
11. lấy exact source frame;
12. xác định được vì sao một query fail;
13. reproduce kết quả bằng build manifest.

Một architecture đẹp nhưng không hỗ trợ 13 hành vi trên chưa phải workstation hoàn chỉnh.

---

# 41. Kết luận

Roadmap chính thức nên tuân theo ba nguyên tắc:

> **Data correctness before intelligence.**  
> **Independent evidence before fusion.**  
> **Benchmark before automation.**

Thứ tự có ý nghĩa nhất là:

```text
MAPPING
  ↓
SINGLE LANES
  ↓
COMPARE
  ↓
SEQUENCE
  ↓
SAFE PRUNING
  ↓
MANUAL HYBRID
  ↓
QUERY BRAIN
  ↓
AUTO FUSION + RESCUE
  ↓
EXACT-FRAME COMPETITION WORKFLOW
```

Mục tiêu cuối không phải tạo một pipeline “thông minh nhất có thể”, mà là tạo một hệ thống **có nhiều cách ứng chiến, có thể giải thích, có thể kiểm chứng, không mất recall vì một quyết định duy nhất, và có đường từ query đến exact frame thật sự đáng tin cậy**.
