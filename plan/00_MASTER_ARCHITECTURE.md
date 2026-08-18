# 00 — MASTER ARCHITECTURE

## AIC 2026 Mode-First Hierarchical Temporal Multimodal Retrieval Workstation

> **Vai trò tài liệu:** Architecture authority cho toàn bộ retrieval system.
> **Trạng thái:** Design freeze candidate.
> **Mục tiêu:** mô tả từ nguồn dữ liệu → mapping → query input → pruning → independent search lanes → temporal matching → fusion/rescue → media inspector → exact frame.

---

# 1. Bài toán thực tế

AIC interactive video retrieval không chỉ là “text-to-image search”. Một query có thể yêu cầu:

- một object cụ thể;
- màu/trạng thái/trang phục;
- hành động;
- bố cục/quan hệ không gian;
- chữ xuất hiện trên màn hình;
- nội dung người nói;
- program/topic;
- một cảnh rồi **sau đó** một cảnh khác;
- exact frame để submit.

Không một nguồn nào giải tốt mọi dạng query.

Ví dụ:

```text
"người áo xanh đi xe máy qua barie"
```

- SigLIP có thể bắt semantic visual.
- Qwen có thể bắt object/attribute/action/relation.
- BTC detector có thể xác nhận Person/Motorcycle.
- ASR/OCR có thể hoàn toàn không hữu ích.

Nhưng query:

```text
"bản tin nói về điều chỉnh lãi suất ngân hàng"
```

- ASR là signal chính.
- Metadata có thể giúp program/topic prior.
- OCR có thể bắt headline/chart label.
- Visual có thể rất generic.

Còn query:

```text
"sau cảnh người đầu bếp cho nguyên liệu vào nồi là cảnh món ăn được bày ra đĩa"
```

đòi hỏi **retrieval + temporal ordering**, không phải Top-K frame độc lập.

Vì vậy kiến trúc phải tối ưu cho **đa dạng chiến thuật**, không phải một pipeline cứng.

---

# 2. Mục tiêu kiến trúc

Hệ thống phải đạt đồng thời 10 mục tiêu:

1. **Independent modes:** SigLIP/OCR/ASR/Qwen/BTC CLIP... chạy riêng được.
2. **Shared mapping:** mọi result biết video/time/frame/evidence.
3. **Operator control:** người dùng có thể chỉnh decomposition và lane plan.
4. **Temporal search:** hỗ trợ A→B→C cùng video với gap constraint.
5. **Recall-safe pruning:** taxonomy không được biến thành single point of failure.
6. **Late fusion:** không trộn score space sớm.
7. **Global rescue:** luôn có đường tìm ngoài hypothesis của Brain/taxonomy.
8. **Explainability:** result biết đến từ lane nào và evidence gì.
9. **Exact-frame authority:** final frame lấy từ source video.
10. **Benchmarkability:** mỗi stage đo được hit/miss/latency/failure.

---

# 3. Nguyên tắc thiết kế

## 3.1 Independent evidence, shared identity, late fusion

```text
        SHARED DATA HUB / IDENTITY
                  │
  ┌───────────────┼───────────────────┐
  ▼               ▼                   ▼
SigLIP         BTC CLIP              BGE/Text
  ▼               ▼                   ▼
Custom frame     BTC frame        ASR/OCR/Qwen
  │               │                   │
  └───────────────┼───────────────────┘
                  ▼
          canonical results
                  ▼
          temporal / fusion
```

Các model không cần cùng vector dimension, cùng score scale hay cùng sampling. Chúng chỉ cần thống nhất **entity identity** ở output.

## 3.2 Human-controllable AI

Brain được dùng để giảm thao tác, không được che giấu logic.

Người dùng luôn thấy:

```text
Program guess
Topic guess
Objects
Attributes
Actions
Scenes
OCR hints
ASR hints
Temporal intent
Selected lanes
Pruning mode
```

và có thể sửa.

## 3.3 Fail-soft, không fail-closed theo modality

Nếu OCR không có → visual/ASR vẫn chạy.

Nếu Qwen missing 180 frames → frame vẫn tồn tại trong keyframe catalog.

Nếu video zero-ASR → video không bị loại khỏi corpus.

Nếu taxonomy uncertain → SAFE/GLOBAL route.

---

# 4. Toàn bộ nguồn dữ liệu

## 4.1 Source video — authority cuối

Entity:

```text
video_id = Lxx_Vxxx
```

Dùng cho:

- playback;
- seek;
- exact-frame extraction;
- verification;
- neighborhood frame extraction.

Không dùng raw MP4 scan làm search hot-loop.

---

## 4.2 BTC Keyframe Space

### Thành phần

1. BTC JPEG keyframes.
2. Map-keyframes CSV.
3. CLIP ViT-B/32 512D vectors.
4. BTC object detections.

### Identity đề xuất

```text
frame_space = BTC
btc_keyframe_id = BTC:L21_V001:KF000001
video_id = L21_V001
n = 1
frame_idx = ...
timestamp_ms = ...
```

### Vai trò

- independent visual search;
- broad/global rescue;
- detector object evidence;
- alternative sampling so với custom keyframes;
- candidate browsing.

**Không merge BTC keyframe row với custom row chỉ vì chúng có ordinal gần nhau.**

---

## 4.3 Custom Keyframe Space

Audit hiện có **116,767** custom keyframes.

Identity:

```text
frame_space = CUSTOM
custom_keyframe_id = CUSTOM:L21_V001:KF000001
video_id
frame_idx
timestamp_ms
shot_id
image_relpath
embedding_index
```

Vai trò:

- primary custom visual candidates;
- Qwen mapping;
- custom SigLIP mapping;
- OCR mapping nếu OCR chạy trên custom frame set;
- temporal/shot aggregation.

---

## 4.4 Qwen semantic source

Audit:

```text
116,587 success / 116,767 custom keyframes
873/873 videos
180 missing
```

### Raw fields

```text
objects
attributes
spatial_relations
counts
scene
visible_actions
caption
```

### Qwen không được dùng như thế nào

Không:

- coi visible action từ một frame là temporal action chắc chắn;
- tạo fake confidence;
- hard-prune video chỉ vì một Qwen term không xuất hiện;
- coi raw unique strings là controlled ontology.

### Qwen dùng tốt cho

- semantic frame search;
- facet postings;
- caption retrieval;
- scene/action/object evidence;
- reranking;
- region/video semantic aggregation.

---

## 4.5 OCR source

### Raw evidence cần giữ

```text
video_id
frame/keyframe ref
text
bbox
confidence
vector row
```

### Hai cách search song song

**Lexical/fuzzy:**

```text
FTS/BM25
+ normalized Vietnamese
+ accentless variant
+ trigram/n-gram
```

**Semantic:**

```text
query → BGE-M3
OCR text embeddings → vector index
```

### Tại sao cần cả hai

Exact token tốt cho:

- số;
- tên;
- mã;
- title;
- acronym.

Dense semantic tốt khi OCR hơi sai chính tả hoặc query paraphrase.

OCR confidence chỉ là detector/recognizer evidence, không đồng nhất với search relevance.

---

## 4.6 ASR source

Entity:

```text
segment_id
video_id
start_ms
end_ms
text
```

Search:

- lexical/BM25;
- BGE-M3 dense;
- optional sparse/hybrid;
- segment grouping into windows.

ASR là signal mạnh cho:

- news;
- education;
- documentary;
- named entity/event;
- spoken topic.

Zero-ASR phải được giữ như explicit status.

---

## 4.7 BTC Media-info

Fields như:

```text
title
description
keywords
author
publish_date
```

Vai trò:

- Program prior;
- source/channel identity;
- broad topic prior;
- lexical semantic lane phụ.

Không dùng title/description như frame-level truth.

---

## 4.8 Taxonomy / memberships

Taxonomy có hai tầng chức năng:

```text
Program / Format
Topic / Semantic
```

và facets không buộc vào tree:

```text
object
action
attribute
scene
relation
visible_text
...
```

Program/Topic là graph membership; một video có thể có nhiều edge.

Temporal multi-topic News phải cho topic ở **region scope**, không ép toàn video thành một topic.

---

# 5. Trung tâm dữ liệu — Unified Data Hub

## 5.1 Data Hub không phải giant JSON

Data Hub gồm ba lớp:

```text
RAW SOURCES
   ↓
CANONICAL MACHINE DATA
   ↓
DERIVED RUNTIME INDEX
```

### Raw

Giữ nguyên các output đắt tiền:

- raw Qwen;
- raw OCR metadata/vector shards;
- BTC files;
- ASR artifacts;
- source video.

### Canonical

JSON/JSONL có version, relative path và stable IDs.

### Runtime

- SQLite;
- FTS;
- bitsets/postings;
- FAISS indexes;
- caches.

---

## 5.2 Core tables đề xuất

```text
videos
media_info
asr_segments
keyframes
qwen_semantics
ocr_texts
btc_objects
taxonomy_nodes
video_memberships
temporal_regions
region_memberships
artifacts
index_registry
```

### `videos`

```text
video_id PK
ordinal
series
duration_ms
source_relpath
flags
```

### `keyframes`

Một table có discriminator hoặc hai physical tables đều được, nhưng identity phải rõ:

```text
keyframe_uid PK
frame_space    BTC|CUSTOM
video_id FK
local_keyframe_no
frame_idx
timestamp_ms
shot_id nullable
image_relpath
embedding_index nullable
```

Unique:

```text
(frame_space, video_id, local_keyframe_no)
(frame_space, video_id, frame_idx)
```

nếu dữ liệu audit bảo đảm uniqueness.

### `asr_segments`

```text
segment_uid PK
video_id
start_ms
end_ms
text
normalized_text
```

### `ocr_texts`

```text
ocr_uid PK
video_id
keyframe_uid nullable
frame_idx nullable
timestamp_ms nullable
raw_text
normalized_text
bbox_json
ocr_confidence
embedding_ref
```

### `qwen_semantics`

Không nhất thiết explode toàn bộ arrays vào SQL row-per-facet. Có thể giữ raw JSON + normalized child postings.

```text
keyframe_uid PK
raw_semantic_json
caption
normalization_version
flags
```

---

# 6. Index Registry — lớp thường bị thiếu nhưng rất quan trọng

Mỗi vector index phải có manifest:

```text
index_id
lane
model_id
model_revision
preprocessing_version
dimension
metric
entity_space
row_count
metadata_checksum
built_at
```

Ví dụ:

```text
index_id: siglip2_custom_v1
lane: siglip_custom
model_id: google/siglip2-base-patch16-224
entity_space: CUSTOM_KEYFRAME
```

BTC CLIP index:

```text
index_id: btc_clip_v1
model_id: OpenAI CLIP ViT-B/32
entity_space: BTC_KEYFRAME
```

Điều này ngăn query bị encode bằng model sai.

---

# 7. Query Workspace

Hệ thống không dùng chỉ một textbox.

## 7.1 Natural Query

```text
[ Một người mặc áo xanh chạy xe máy qua barie ... ]
```

Câu gốc luôn được giữ nguyên.

## 7.2 Structured facet editor

```text
PROGRAM       [Auto ▼]
TOPIC         [Auto ▼]
OBJECTS       [motorcycle] [barrier] [+]
ATTRIBUTES    [green shirt] [+]
ACTIONS       [riding] [passing] [+]
SCENES        [checkpoint] [+]
OCR TEXT      [+]
ASR PHRASE    [+]
NEGATIVE      [+]
```

## 7.3 Brain suggestions

Brain có thể tự điền structured editor, nhưng đó là **suggested plan**.

Operator có thể:

- accept;
- delete;
- add;
- change priority;
- force a lane;
- disable pruning.

---

# 8. Query Brain

Brain gồm nhiều tầng, không phụ thuộc hoàn toàn vào LLM.

```text
Natural Query
    │
    ├── deterministic parser
    │     temporal words / quoted text / numbers
    │
    ├── taxonomy / alias matcher
    │
    ├── semantic branch matcher
    │
    └── optional LLM decomposition
            │
            ▼
       Query Plan
```

## 8.1 Output contract

```json
{
  "intent": "SEQUENCE",
  "program_candidates": [],
  "topic_candidates": [],
  "facets": {
    "objects": [],
    "attributes": [],
    "actions": [],
    "scenes": [],
    "ocr_hints": [],
    "asr_hints": []
  },
  "sequence_steps": [],
  "lane_priorities": [],
  "pruning_mode": "SAFE"
}
```

## 8.2 Brain không được quyết định irrevocably

Mọi decision phải có đường override.

---

# 9. Pruning architecture

## 9.1 OFF

Không loại video dựa taxonomy.

Dùng cho:

- baseline;
- debugging;
- suspected taxonomy failure;
- global query.

## 9.2 SAFE

Không phải hard intersection.

Ví dụ:

```text
priority_pool = taxonomy candidates
escape_pool   = global lane candidates
final_video_pool = union(priority_pool, escape_pool)
```

Taxonomy được dùng để:

- boost;
- allocate larger K;
- search branch trước;
- không loại tuyệt đối generic uncertain branches.

## 9.3 AGGRESSIVE

Chỉ bật khi:

- branch specificity cao;
- router margin đủ;
- ≥2 evidence families nếu policy yêu cầu;
- GT calibration chứng minh recall.

Threshold là experiment config, không hard-code vào taxonomy truth.

---

# 10. Independent Search Lanes

Mỗi lane có interface logic:

```text
search(query_plan, scope, top_k) -> EvidenceResult[]
```

## 10.1 SigLIP2 Custom

Input:

- natural visual query;
- optionally visual subset text synthesized từ facets.

Search space:

- custom keyframe embeddings.

Output:

- custom keyframe result.

Đặc biệt:

- đúng text encoder và preprocessing của SigLIP2;
- không BGE query vào SigLIP vectors.

## 10.2 BTC CLIP

Search BTC keyframes độc lập.

Vai trò chính:

- baseline;
- alternative sampling;
- global visual rescue.

## 10.3 Qwen Semantic

Sub-lanes có thể gồm:

```text
objects postings
scene postings
action postings
caption lexical/dense
relation rerank
```

Không bắt buộc biến Qwen thành một vector duy nhất.

## 10.4 ASR

```text
BM25/FTS
BGE dense
window aggregation
```

## 10.5 OCR

```text
exact / BM25
trigram fuzzy
BGE dense
confidence-aware rerank
```

## 10.6 BTC Objects

Search:

- class exact/alias;
- detector score threshold;
- bbox optional constraints;
- aggregate frame→video.

Absence không được dùng hard negative.

## 10.7 Media-info

Video-level lane; không tạo frame hit trực tiếp trừ khi kết hợp với timeline lane khác.

---

# 11. Canonical Evidence Result

Đây là contract bắt buộc để mọi lane phối hợp được.

```json
{
  "result_id": "...",
  "lane": "siglip_custom",
  "entity_type": "KEYFRAME",
  "video_id": "L21_V001",
  "frame_space": "CUSTOM",
  "keyframe_uid": "...",
  "frame_idx": 426,
  "timestamp_ms": 14200,
  "start_ms": null,
  "end_ms": null,
  "rank": 4,
  "score_raw": 0.831,
  "score_type": "cosine",
  "evidence": {},
  "provenance": {}
}
```

ASR result có thể entity type `SEGMENT`, OCR `TEXT_BOX`, media `VIDEO`.

Các stage sau chỉ cần biết:

```text
video_id
when?
what evidence?
rank?
```

---

# 12. Compare Mode

Mục tiêu Compare không phải UI “đẹp”, mà là **công cụ khoa học để hiểu failure**.

Ví dụ một query:

```text
SigLIP       correct video rank 3   correct frame rank 8
BTC CLIP     rank 17                rank 31
Qwen         rank 1                 rank 4
ASR          miss
OCR          miss
```

Từ đó biết:

- fusion có cần ASR không;
- custom sampling có lợi hơn BTC không;
- Qwen tạo value ở loại query nào;
- lane nào chỉ nên rescue.

---

# 13. Temporal / Sequence Engine

## 13.1 Query representation

```text
STEP 1: scene A
STEP 2: scene B
STEP 3: scene C
```

Constraint:

```text
same_video = true
strict_order = true
min_gap_ms = 0
max_gap_ms = configurable
```

Seed UX có thể mặc định max gap 60s cho dạng “sau đó”, nhưng **60s là configurable heuristic**, không phải truth.

## 13.2 Mỗi step có lane riêng

Ví dụ:

```text
STEP 1 OCR: "Đại học Cần Thơ"
STEP 2 SigLIP/Qwen: person riding motorcycle
```

Temporal engine chỉ cần canonical evidence timestamps.

## 13.3 Partial matches

Không chỉ trả full A+B.

Phải trả riêng:

```text
FULL MATCH       A + B thỏa gap
BEFORE ONLY      A mạnh, B chưa thấy
AFTER ONLY       B mạnh, A chưa thấy
ORDER VIOLATION  A/B đều có nhưng sai thứ tự
GAP VIOLATION    đúng thứ tự nhưng quá xa
```

Điều này rất quan trọng vì operator “mò kim đáy bể”; partial evidence vẫn có giá trị để mở video kiểm tra.

## 13.4 Ranking chuỗi

Sequence score V1 có thể dựa trên rank-normalized component + temporal coherence, không cộng raw scores khác space.

Ví dụ logic:

```text
score = evidence_rank_support
      + order_bonus
      + gap_coherence_bonus
      + modality_diversity_bonus(optional)
```

Các weight cần benchmark.

---

# 14. Temporal Regions

Sequence search và region search là hai khái niệm khác nhau.

**Region:** chia một video thành semantic windows để giảm frame search.

**Sequence:** tìm nhiều event/scene có thứ tự.

Region builder có thể dùng:

```text
ASR semantic continuity
shot boundaries
Qwen semantic change
OCR headline/lower-third changes
```

News L21/L22 ưu tiên region-level topic.

Nhưng runtime phải hỗ trợ fallback:

```text
region unavailable → search candidate frames directly
```

Không để region dependency chặn toàn hệ thống.

---

# 15. Late Fusion

## 15.1 V0 — không fusion

Hiển thị lanes riêng.

## 15.2 V1 — RRF

RRF phù hợp vì chỉ cần rank, tránh vấn đề score scale.

```text
RRF(result) = Σ 1 / (k + rank_lane)
```

`k` cần config/benchmark.

## 15.3 V2 — weighted rank fusion

Sau ablation có thể tăng priority lane theo query type.

Ví dụ:

```text
OCR-heavy query → OCR rank weight ↑
spoken event → ASR ↑
visual relation → Qwen/SigLIP ↑
```

## 15.4 V3 — calibrated/learned rerank

Chỉ sau khi có đủ evaluation data.

---

# 16. Global Rescue

Rescue không phải “chạy lại mọi thứ sau fail”. Nó là một lane strategy có ngân sách nhỏ chạy ngoài local scope.

Ví dụ SAFE mode:

```text
primary scope:
  taxonomy → 80 videos

rescue:
  global SigLIP Top50
  global BTC CLIP Top50
  global ASR TopN

final video candidates = union
```

Mục tiêu là giảm false-negative từ:

- taxonomy error;
- sampling difference;
- Brain decomposition error;
- local region miss.

---

# 17. Result Cards

Một result card nên cho operator biết ngay:

```text
thumbnail
video_id
timestamp
frame_idx
rank
lane badges
matched facets / matched text
sequence step nếu có
review status
```

Review status:

```text
UNREVIEWED
LIKELY
REJECTED
CONFIRMED
```

---

# 18. Media Inspector

Click result:

```text
candidate
→ source video
→ seek timestamp
```

Controls:

```text
±3s
±10s
±1 frame
±3 frames
±10 frames
```

Nếu keyframe tại exact offset không tồn tại:

1. tìm nearest indexed keyframe để preview nhanh;
2. nếu operator cần exact temporal point → extract frame trực tiếp từ MP4;
3. exact frame có thể cache tạm.

### Key insight

“Frame không có trong keyframe dataset” **không có nghĩa frame không tồn tại**. Mọi physical frame tồn tại trong video authority nếu timestamp/frame mapping hợp lệ.

---

# 19. Tránh lag khi mở video

Kiến trúc không được giả định browser phải tải full video mới seek.

Backend media layer nên hỗ trợ:

- HTTP Range;
- ffprobe metadata;
- server-side seek/extract;
- exact JPEG endpoint;
- optional short preview clip around timestamp;
- thumbnail/neighbor cache.

UX có thể ưu tiên:

```text
instant thumbnail neighborhood
↓
video stream on demand
```

thay vì bắt player tải xa trước khi operator có evidence.

---

# 20. Fast/Balanced/Deep search profiles

Ngoài lane mode, Auto/Hybrid có thể có execution profile:

## FAST

- SAFE coarse video prior;
- smaller K;
- no expensive reranker;
- top lanes only.

## BALANCED

- multiple main lanes;
- RRF;
- moderate rescue.

## DEEP

- larger K;
- sequence expansion;
- reranker;
- broader rescue;
- more neighborhood inspection.

Profiles chỉ thay execution budget, không thay canonical query meaning.

---

# 21. Technology stack — Tier 1

## Metadata / mapping

**SQLite**

Ưu:

- relational integrity;
- easy indexes;
- single-file deployment;
- FTS5;
- excellent cho 873-video metadata graph.

Nhược:

- không phải distributed vector DB;
- specialized ANN functionality cần FAISS/extension khác.

**Chốt:** dùng.

## Text lexical

**SQLite FTS5 / BM25**

Dùng cho:

- ASR;
- OCR;
- media title/keywords;
- Qwen caption lexical.

OCR thêm n-gram/trigram auxiliary representation.

## Text semantic

**BGE-M3**

Dùng cho text↔text semantic retrieval.

Không dùng cho SigLIP/CLIP image vector query.

## Visual ANN

**FAISS**

Index riêng:

```text
siglip_custom.faiss
btc_clip.faiss
```

Flat inner-product/cosine baseline trước; HNSW/IVF chỉ benchmark nếu cần.

## Video filter

**Fixed bitset** cho 873 video.

873 bit chỉ khoảng 110 bytes/branch, rất đơn giản.

## Fusion

**RRF** baseline.

## API

**FastAPI** / existing backend architecture.

---

# 22. Technology stack — Tier 2

Chỉ thêm khi benchmark chỉ ra vấn đề cụ thể.

### BGE-M3 sparse/hybrid

Có thể tăng exact-term + semantic retrieval trên Vietnamese text.

### Cross-encoder reranker

Chỉ rerank Top-N, không toàn corpus.

### Qdrant

Hữu ích nếu cần:

- named vectors;
- hybrid query orchestration;
- payload filters;
- centralized vector service.

Nhưng thêm operational complexity. Không cần để khởi động V1 nếu SQLite+FAISS đủ.

### OpenSearch/Elasticsearch

Hữu ích nếu lexical/fuzzy/filtering trở nên phức tạp hoặc cần service-scale observability. Không cần làm dependency đầu tiên.

### Vespa

Mạnh cho multi-stage rank profiles, nhưng engineering cost cao hơn. Chỉ đáng cân nhắc nếu architecture tiến đến sophisticated serving platform.

---

# 23. Tier 3 / experimental

Không ưu tiên trước benchmark:

- mega multimodal embedding;
- LLM rerank hàng chục nghìn frames online;
- end-to-end learned fusion;
- late-interaction index toàn bộ nếu chưa có need;
- graph neural ranking;
- aggressive hard-prune bằng inferred facets.

---

# 24. Feature set mục tiêu

## Search

- Natural query.
- Structured facets.
- Assisted decomposition.
- Single lane.
- Compare.
- Manual Hybrid.
- Auto.
- Sequence.
- Search Entire Corpus.
- Global Rescue.

## Filtering

- Program.
- Topic.
- video allow/deny list.
- object/action/scene.
- OCR text.
- time constraints.
- negative constraints.

## Results

- lane badges.
- explain evidence.
- group by video.
- dedup/diversity.
- same-video timeline.
- sequence cards.
- side-by-side compare.

## Inspector

- open source video at timestamp.
- exact frame.
- ±seconds.
- ±frames.
- nearest keyframes.
- filmstrip.
- candidate pin/review.

## Developer tools

- query plan trace.
- per-lane latency.
- candidate count after each prune stage.
- GT survival.
- failure explorer.
- index health/provenance.

---

# 25. Failure taxonomy

Mỗi failed query phải phân loại được ít nhất:

```text
QUERY_PARSE_FAILURE
TAXONOMY_ROUTE_FAILURE
VIDEO_PRUNED_OUT
LANE_VISUAL_MISS
LANE_ASR_MISS
LANE_OCR_MISS
QWEN_SEMANTIC_MISS
FRAME_SAMPLING_MISS
TEMPORAL_ORDER_MISS
TEMPORAL_GAP_MISS
FUSION_DEMOTION
RESCUE_MISS
MAPPING_ERROR
EXACT_FRAME_RESOLUTION_ERROR
```

Nếu không biết failure ở đâu, không thể cải thiện có hệ thống.

---

# 26. Evaluation architecture

Ba lớp recall:

## Video Recall

Correct video có vào candidate pool không?

## Temporal Recall

Correct interval/region có vào candidates không?

## Frame Recall

Correct frame/range có trong Top-K không?

Thêm:

- first correct rank;
- per-lane recall;
- sequence full/partial match;
- pruning survival;
- rescue recovery rate;
- latency p50/p95.

---

# 27. Ablation plan

Không chỉ benchmark “full system”.

Chạy:

```text
SigLIP
BTC CLIP
Qwen
ASR
OCR
Objects

SigLIP + Qwen
ASR + OCR
SigLIP + BTC CLIP
all lanes RRF
all lanes - OCR
all lanes - Qwen
...
```

Mục tiêu biết **mỗi nguồn tạo thêm giá trị bao nhiêu**.

---

# 28. Roadmap architecture-level

## M0 — Mapping Freeze

Deliver:

- complete source registry;
- BTC/custom frame spaces;
- keyframe catalogs;
- ASR/Qwen/OCR references;
- runtime SQLite schema;
- validation PASS.

## M1 — Independent Lanes

Deliver:

- lane APIs;
- canonical result format;
- per-lane smoke tests.

## M2 — Compare + Benchmark

Deliver:

- Run All;
- result comparison;
- GT metrics;
- failure logging.

## M3 — Sequence

Deliver:

- 2–5 step queries;
- full/partial matches;
- configurable gap.

## M4 — SAFE Pruning

Deliver:

- Program/Topic bitsets;
- OFF/SAFE/AGG modes;
- pruning survival metrics.

## M5 — Manual Hybrid

Deliver:

- lane selection;
- RRF;
- evidence fusion.

## M6 — Query Brain

Deliver:

- LLM-assisted + deterministic decomposition;
- editable plan;
- lane suggestions.

## M7 — Auto + Rescue

Deliver:

- Auto planner;
- rescue budget;
- trace.

## M8 — Hardening

Deliver:

- frozen build manifest;
- reproducible index artifacts;
- competition presets;
- latency/reliability rehearsal.

---

# 29. Acceptance gates

## Mapping Gate

- 873 videos represented.
- no unknown `video_id`.
- BTC/custom spaces distinguishable.
- Qwen 116,587 records map deterministically.
- 180 Qwen missing explicit, not silently dropped.
- OCR mapping coverage measured explicitly.
- vector row ↔ metadata mapping checksums.

## Lane Gate

Mỗi lane:

- deterministic query encoder config;
- correct entity mapping;
- Top-K returned;
- latency recorded;
- failure does not crash other lanes.

## Sequence Gate

- same-video order correct;
- max-gap works;
- full + partial categories;
- timestamps inspectable.

## Pruning Gate

- candidate count measured;
- GT survival measured;
- AGGRESSIVE disabled until calibrated.

## Fusion Gate

- fusion must outperform or add rescue value vs best single lane on target metrics;
- otherwise keep lane separate.

## Exact Frame Gate

- result opens correct video/time;
- ±frame stepping deterministic;
- source-video exact frame returned.

---

# 30. Các quyết định phải được benchmark thay vì tranh luận

Không tranh luận cảm tính về:

- custom vs BTC keyframes;
- SigLIP vs CLIP;
- OCR có “ngu” quá nên bỏ không;
- Qwen có đáng dùng không;
- Top-K bao nhiêu;
- max gap 30s/60s/120s;
- taxonomy hard/soft;
- fusion weights.

Mọi câu trên đều có thể biến thành experiment với Ground Truth.

---

# 31. Các quyết định chốt

### Chốt 1

**Không gộp SigLIP2 và BTC CLIP index.**

### Chốt 2

**Không bỏ BTC data.** BTC là independent evidence/rescue system.

### Chốt 3

**Không bỏ natural query để đổi lấy structured fields.** Giữ cả hai.

### Chốt 4

**Sequence Mode sẽ được làm**, nhưng manual sequence trước, auto decomposition sau.

### Chốt 5

**Taxonomy dùng SAFE prior trước, hard prune sau benchmark.**

### Chốt 6

**SQLite + FTS + FAISS + bitset/postings + RRF là Tier 1 stack.**

### Chốt 7

**BGE-M3 chỉ phục vụ text semantic space**, không thay text encoder của SigLIP/CLIP.

### Chốt 8

**Click result phải về source video + exact timestamp/frame**, không dừng ở keyframe JPEG.

### Chốt 9

**Compare Mode phải có trước Auto Fusion**, vì cần biết tại sao từng lane fail.

### Chốt 10

**Raw data immutable; canonical mapping/index là rebuildable.**

---

# 32. Architecture diagram cuối

```text
                            ┌───────────────────────┐
                            │     QUERY WORKSPACE   │
                            │ natural + structured  │
                            └───────────┬───────────┘
                                        │
                                        ▼
                            ┌───────────────────────┐
                            │      QUERY BRAIN      │
                            │ Program Topic Facets  │
                            │ temporal / lane plan  │
                            └───────────┬───────────┘
                                        │
                            ┌───────────▼───────────┐
                            │     PRUNING POLICY    │
                            │ OFF / SAFE / AGG      │
                            └───────────┬───────────┘
                                        │
                       ┌────────────────▼────────────────┐
                       │        CANDIDATE SCOPE          │
                       │ videos / optional regions       │
                       └────────────────┬────────────────┘
                                        │
       ┌────────────────┬───────────────┼───────────────┬─────────────────┐
       ▼                ▼               ▼               ▼                 ▼
┌────────────┐   ┌────────────┐   ┌────────────┐  ┌────────────┐  ┌────────────┐
│ SigLIP2    │   │ BTC CLIP   │   │ Qwen      │  │ ASR        │  │ OCR        │
│ CUSTOM     │   │ BTC        │   │ semantic  │  │ text       │  │ text       │
└─────┬──────┘   └─────┬──────┘   └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
      │                │                │               │               │
      │                │                │               │               │
      │         ┌──────▼──────┐         │               │               │
      │         │ BTC Objects │         │               │               │
      │         └──────┬──────┘         │               │               │
      └────────────────┴────────────────┴───────┬───────┴───────────────┘
                                               │
                                               ▼
                                    ┌────────────────────┐
                                    │ CANONICAL EVIDENCE │
                                    │ video/time/frame   │
                                    └─────────┬──────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                      ┌──────────────┐                ┌───────────────┐
                      │ NORMAL RANK  │                │ SEQUENCE      │
                      │ / GROUP      │                │ A→B→C         │
                      └──────┬───────┘                └──────┬────────┘
                             └──────────────┬────────────────┘
                                            ▼
                                  ┌────────────────────┐
                                  │ COMPARE / RRF      │
                                  │ LATE FUSION        │
                                  └─────────┬──────────┘
                                            │
                                  ┌─────────▼──────────┐
                                  │ GLOBAL RESCUE      │
                                  └─────────┬──────────┘
                                            │
                                            ▼
                                  ┌────────────────────┐
                                  │ FINAL RESULT CARDS │
                                  └─────────┬──────────┘
                                            │
                                            ▼
                                  ┌────────────────────┐
                                  │ MEDIA INSPECTOR    │
                                  │ video / neighbors  │
                                  └─────────┬──────────┘
                                            │
                                            ▼
                                  ┌────────────────────┐
                                  │ SOURCE VIDEO       │
                                  │ EXACT FRAME        │
                                  └────────────────────┘
```

---

# 33. Kết luận

“Bộ não” của hệ thống không phải Qwen, LLM, taxonomy hay một vector DB.

**Bộ não thực tế là orchestration layer có khả năng:**

1. hiểu hypothesis từ query;
2. cho operator sửa hypothesis;
3. chọn đúng evidence lanes;
4. giữ evidence độc lập;
5. cắt tỉa có kiểm soát;
6. hiểu timeline;
7. so sánh/hợp nhất kết quả;
8. rescue ngoài hypothesis ban đầu;
9. đưa operator đến đúng video và exact frame;
10. ghi lại toàn bộ trace để lần sau biết vì sao thành công/thất bại.

Đó là kiến trúc nên được dùng làm nền cho các tài liệu Data Hub, Query Brain, Search Lanes, Temporal Inspector và Roadmap tiếp theo.
