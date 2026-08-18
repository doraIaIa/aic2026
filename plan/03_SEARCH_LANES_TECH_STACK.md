# 03 — SEARCH LANES & TECHNOLOGY STACK
## SigLIP2, BTC CLIP, Qwen, ASR, OCR, BTC Objects, Media-info; Tier 1 / Tier 2 / Tier 3 và stack chốt

> **Trạng thái:** Design freeze candidate  
> **Mục tiêu:** Mỗi nguồn dữ liệu có một lane tìm kiếm độc lập, có input/output contract rõ ràng, benchmark riêng, sau đó mới late-fusion.  
> **Quy tắc:** **Không so sánh/cộng trực tiếp raw score từ các model khác space.**

---

# 1. Tại sao phải giữ các lane độc lập?

Hệ thống hiện có nhiều loại evidence không cùng bản chất:

```text
Visual embedding
Text embedding
Lexical text
Object detection
Structured semantics
Video metadata
```

Nếu gộp tất cả thành một “super score” ngay từ đầu:

- không biết lane nào đang giúp;
- không biết lane nào làm sai;
- raw scores không cùng scale;
- khó benchmark;
- khó xử lý model/index lỗi;
- khó thay công nghệ từng phần.

Kiến trúc chốt:

```text
shared Data Hub
      │
      ├── SigLIP2 lane
      ├── BTC CLIP lane
      ├── Qwen lane
      ├── ASR lane
      ├── OCR lane
      ├── BTC Object lane
      └── Media-info lane
              │
              ▼
     canonical evidence results
              │
              ▼
         late fusion
```

---

# 2. Các vector space phải tách tuyệt đối

Có ít nhất ba không gian embedding chính:

```text
CUSTOM VISUAL SPACE
SigLIP2 image embeddings
↕
SigLIP2 text encoder

BTC VISUAL SPACE
CLIP ViT-B/32 image embeddings
↕
CLIP ViT-B/32 text encoder

TEXT SEMANTIC SPACE
BGE-M3 embeddings
↕
BGE-M3 query embeddings
```

Không làm:

```text
BGE query vector ↔ SigLIP image vector
```

Không làm:

```text
SigLIP query vector ↔ BTC CLIP image vector
```

Không làm:

```text
0.82 SigLIP cosine + 0.82 BGE cosine
```

mà không có calibration/rank fusion.

---

# 3. Canonical lane interface

Mỗi lane nên expose logic tương đương:

```text
search(
  query_variant,
  candidate_scope,
  top_k,
  filters,
  options
) -> EvidenceResult[]
```

Output tối thiểu:

```json
{
  "lane": "siglip_custom",
  "source_space": "CUSTOM_KEYFRAME",
  "video_id": "L21_V001",
  "frame_id": "...",
  "frame_idx": 426,
  "timestamp_ms": 14200,
  "raw_score": 0.83,
  "rank": 4,
  "evidence": {},
  "query_variant_id": "Q1:visual_original"
}
```

Text lane có thể trả segment range thay vì frame:

```json
{
  "lane": "asr_dense",
  "video_id": "L21_V001",
  "start_ms": 13000,
  "end_ms": 17000,
  "raw_score": 0.71,
  "rank": 2
}
```

Data Hub chịu trách nhiệm map result sang nearest frame/region khi UI cần.

---

# 4. Lane 1 — CUSTOM SigLIP2 Visual Search

## 4.1 Nguồn dữ liệu

- Custom keyframes: 116,767.
- Custom image embeddings đã được encode bằng SigLIP2.
- Mapping về custom keyframe catalog.

## 4.2 Query encoder

Query **phải** dùng text encoder/processor tương thích chính xác với model đã tạo image embeddings.

Nếu index được build từ:

```text
google/siglip2-base-patch16-224
```

thì runtime phải freeze:

```text
model_id
model revision/checksum nếu có
processor configuration
text max length
normalization policy
embedding normalization policy
```

Điểm nhóm đã thảo luận về:

```python
padding="max_length"
truncation=True
max_length=64
```

phải được coi là **index contract**, không phải tùy chọn UI.

Nếu đổi preprocessing, phải benchmark/rebuild contract thay vì âm thầm thay đổi runtime query encoding.

---

# 5. SigLIP2 search implementation

Tier 1:

```text
query text
↓
SigLIP2 text processor
↓
text embedding
↓
normalize theo index contract
↓
FAISS similarity search
↓
row IDs
↓
index row map
↓
custom frame metadata
```

Nếu candidate videos đã được prune:

hai cách:

### Cách A — global FAISS rồi post-filter

Ưu:

- đơn giản;
- index duy nhất;
- rất nhanh cho corpus này.

Nhược:

- nếu filter quá hẹp, cần over-fetch K lớn để đủ results trong scope.

### Cách B — scoped sub-index / selector

Ưu:

- search đúng candidate rows;
- hiệu quả khi candidate scope hẹp.

Nhược:

- implementation phức tạp hơn;
- cần benchmark thực tế.

**Chốt Tier 1:** Global FAISS + adaptive over-fetch + scope filter trước. Chỉ chuyển sang selector/sub-index nếu benchmark chứng minh cần.

---

# 6. SigLIP2 ưu điểm

- Natural-language visual search tốt.
- Không phụ thuộc text xuất hiện trong ảnh.
- Có thể match object + action + scene + attribute trong một câu.
- Custom keyframes đã gắn Qwen/OCR nên result dễ enrich.
- Rất phù hợp single-lane visual mode.

---

# 7. SigLIP2 hạn chế

- Chỉ thấy những custom keyframe đã sample.
- Một action ngắn nằm giữa hai keyframe có thể bị miss.
- Long narrative nhiều step không phù hợp một embedding duy nhất.
- Exact text/named entity không phải điểm mạnh.
- Không dùng raw similarity làm universal confidence.

Giải pháp:

- BTC visual rescue;
- Qwen semantic;
- sequence mode;
- source video exact-frame verification.

---

# 8. SigLIP2 Tier 2

- multiple query variants;
- image-as-query;
- query/frame reranker;
- region-aware rerank;
- hard-negative query expansion;
- temporal neighborhood expansion.

---

# 9. Lane 2 — BTC CLIP Visual Search

## 9.1 Nguồn

Audit BTC:

- ~178,195 BTC keyframes;
- 873 feature `.npy` files;
- OpenAI CLIP ViT-B/32;
- 512D;
- row `i` tương ứng BTC keyframe `n=i+1` của video theo BTC mapping.

BTC data còn có map-keyframe giúp resolve:

```text
n → pts_time → frame_idx
```

---

# 10. BTC CLIP query encoder

Runtime phải dùng đúng CLIP ViT-B/32 text encoder/pretrained variant tương thích feature producer.

Cần freeze:

```text
encoder identity
preprocessing/tokenizer
embedding normalization
similarity metric
```

Không dùng SigLIP query encoder cho BTC index.

---

# 11. BTC CLIP role

Đề xuất:

### Primary role

```text
GLOBAL VISUAL RESCUE
```

Vì BTC keyframe sampling độc lập với custom sampling.

Nếu custom keyframe không chứa cảnh đúng, BTC có thể vẫn có.

### Secondary role

- Compare Mode.
- Manual Hybrid.
- Candidate discovery.
- Cross-check visual result.

Không cần buộc BTC CLIP trở thành primary lane duy nhất.

---

# 12. BTC CLIP ưu/nhược

Ưu:

- index/features đã được BTC cung cấp;
- coverage trên một frame space khác custom;
- độc lập với custom pipeline;
- rất có giá trị rescue.

Nhược:

- CLIP ViT-B/32 semantic capacity thấp hơn các visual encoders mới ở một số query phức tạp;
- vẫn phụ thuộc keyframe sampling;
- không hiểu temporal order;
- không exact text.

---

# 13. BTC CLIP Tier 1

- Build/giữ FAISS index production.
- Validate row count ↔ map-keyframe.
- Store row-map checksum.
- Single Lane mode.
- Global rescue API.
- Result map về BTC frame/time/source video.

---

# 14. BTC CLIP Tier 2

- multimodel rank agreement với SigLIP;
- diversity-aware rescue;
- cross-space nearest temporal mapping BTC ↔ custom;
- query variant ensemble.

---

# 15. Lane 3 — Qwen Semantic Search

## 15.1 Nguồn

Audit raw Qwen:

- 116,587 successful records;
- 873/873 videos;
- 180 custom keyframes chưa có semantic record;
- fields:

```text
video_id
frame_idx
pts_time
objects
attributes
spatial_relations
counts
scene
visible_actions
caption
```

Qwen không cung cấp calibrated confidence cho các semantic strings.

---

# 16. Qwen lane không phải một kỹ thuật search duy nhất

Có thể có ba sub-lane:

```text
QWEN STRUCTURED FACET
QWEN LEXICAL
QWEN DENSE TEXT
```

### Structured

Object/action/scene normalized postings.

### Lexical

FTS/BM25 trên caption/raw semantic text.

### Dense

BGE-M3 embedding trên caption hoặc composed semantic document.

Tier 1 nên hỗ trợ ít nhất Structured + Dense, lexical caption tùy workload.

---

# 17. Qwen semantic normalization

Raw:

```text
motorbike
motorcycle
xe máy
```

Normalized:

```text
object.motorcycle
```

Nhưng phải giữ:

```text
raw_text
normalization_method
normalization_score nếu có
```

Không fake `source_model_score`.

---

# 18. Qwen structured search

Ví dụ query facets:

```text
object.motorcycle
action.riding
attribute.green_shirt
```

Frame candidate support:

```text
motorcycle exact normalized match
riding semantic normalized match
green shirt raw/normalized match
```

Không strict AND mặc định.

Scoring Tier 1:

```text
weighted facet support
+
rarity/IDF-like weight
+
optional caption dense score
```

Sau benchmark có thể thay.

---

# 19. Qwen caption dense search

Build một text per frame:

```text
caption
+ selected structured fields
```

Ví dụ:

```text
objects: motorcycle, person, barrier
attributes: green shirt
scene: road
visible actions: riding
caption: ...
```

Embed bằng text encoder như BGE-M3.

Không nhét mọi raw relation dài nếu làm document quá nhiễu; benchmark variants.

---

# 20. Qwen ưu điểm

- rất giàu object/action/attribute/scene/relation;
- dễ explain;
- custom keyframe mapping rõ;
- hỗ trợ query cấu trúc tốt hơn pure visual embedding;
- useful cho temporal grouping.

---

# 21. Qwen hạn chế

- hallucination/over-description có thể xảy ra;
- vocabulary tự do phân mảnh;
- không có calibrated score;
- một frame không chứng minh temporal action dài;
- 180 custom frames thiếu semantic;
- visible action vẫn chỉ là observation trên selected frame.

Qwen absence không phải hard negative tuyệt đối.

---

# 22. Qwen Tier 1

1. Normalize raw → canonical semantic.
2. Build facet dictionary.
3. Build frame postings.
4. Build Qwen caption/text FTS/dense index.
5. Single lane search.
6. Evidence display raw + normalized.
7. Missing Qwen status explicit.

---

# 23. Qwen Tier 2

- frame-neighborhood semantic aggregation;
- video/region profiles;
- multi-frame temporal action inference;
- reranker on top candidates;
- learned facet weights.

---

# 24. Lane 4 — ASR Search

## 24.1 Nguồn

- 873 video represented;
- 107,540 segments;
- 859 video có ASR;
- 14 zero-ASR retained.

Canonical segment:

```text
video_id
start_ms
end_ms
text
language/provenance
```

---

# 25. ASR phải là hybrid text lane

Tier 1 đề xuất hai sub-lane:

```text
ASR LEXICAL
ASR DENSE
```

sau đó rank-fuse trong ASR family hoặc expose separately trong Compare.

---

# 26. ASR lexical

Công nghệ Tier 1:

```text
SQLite FTS5 / BM25
```

Tốt cho:

- tên riêng;
- số;
- phrase cụ thể;
- exact term;
- thuật ngữ chuyên môn.

Ưu:

- explainable;
- nhẹ;
- deterministic;
- highlight matched token.

Nhược:

- paraphrase kém;
- lỗi ASR có thể phá exact token.

---

# 27. ASR dense

Tier 1:

```text
BGE-M3 dense embeddings
+
FAISS
```

Tốt cho:

- semantic topic;
- paraphrase;
- Vietnamese natural query;
- câu mô tả dài.

Nhược:

- exact entity/number có thể thua lexical;
- raw cosine không comparable với other lane;
- cần maintain vector row map.

---

# 28. BGE-M3 vai trò

Dùng cho text-text semantic search:

```text
query ↔ ASR
query ↔ OCR text/aggregates
query ↔ Qwen caption/semantic docs
query ↔ media metadata/profile
```

Không dùng để compare trực tiếp với image embeddings.

BGE-M3 sparse/multi-vector có thể thử Tier 2; dense Tier 1 đơn giản hơn để kiểm soát.

---

# 29. ASR result expansion

Một segment hit nên map thêm:

```text
nearest custom keyframe
nearest BTC keyframe
video timeline
```

nhưng raw result vẫn là segment thời gian.

UI có thể mở source video ở midpoint/start segment.

---

# 30. ASR context windows

Một câu ASR quá ngắn có thể thiếu nghĩa.

Tier 1 có thể index:

```text
single segment
```

và derived windows:

```text
prev + current + next
```

hoặc fixed semantic windows.

Benchmark cả hai.

Không overwrite raw segments.

---

# 31. ASR ưu/nhược

Ưu:

- cực mạnh với news/education/documentary;
- topic/entity/event rõ;
- timeline có sẵn;
- semantic query tốt.

Nhược:

- không thấy visual-only event;
- zero-ASR videos;
- transcript error;
- lời nói có thể mô tả thứ không hiện trên frame đúng thời điểm.

---

# 32. ASR Tier 2

- BGE-M3 sparse retrieval;
- semantic window embeddings;
- entity index;
- query-dependent context expansion;
- cross-encoder rerank Top-N.

---

# 33. Lane 5 — OCR Search

## 33.1 Nguồn audit

OCR shard pairs:

```text
embeddings_shard_XXX.npy
metadata_shard_XXX.json
```

Metadata có dạng:

```text
text
video_id
keyframe_id/frame_idx
bbox
score/confidence
vector_idx
```

OCR text có lỗi tiếng Việt:

- mất dấu;
- sai ký tự;
- font nghệ thuật;
- noise background;
- O/0, l/1...

Nhưng vẫn rất giá trị cho named text/overlay/signage.

---

# 34. OCR lane phải có ba retrieval legs

```text
OCR EXACT/LEXICAL
OCR FUZZY N-GRAM
OCR DENSE SEMANTIC
```

Không nên chỉ dùng embedding.

---

# 35. OCR exact/lexical

Tốt cho:

```text
2024
THPT
HTV
UBND
```

Công nghệ:

- SQLite FTS5;
- normalized raw text;
- optional quoted exact phrase.

---

# 36. OCR fuzzy/trigram

Do OCR lỗi chính tả, cần normalized search.

Derived representations:

```text
lowercase
unicode normalized
optional diacritic-stripped form
alphanumeric cleaned form
character n-grams/trigrams
```

Ví dụ:

```text
Hồ Chí Minh
OCR: Ho Chi Mnh
```

Trigram/fuzzy vẫn có overlap.

Tier 1 implementation có thể:

- SQLite auxiliary n-gram table;
- trigram postings;
- edit-distance rerank Top lexical candidates.

Không cần fuzzy toàn corpus brute-force mỗi query.

---

# 37. OCR dense

Nếu embeddings đã có và xác nhận model/space:

- validate model identity;
- query encode bằng đúng model;
- search existing shards/index.

Nếu audit chưa đủ xác nhận embedding model:

**không đoán model.**

Phương án an toàn:

- lexical/fuzzy OCR vẫn chạy;
- build canonical BGE-M3 OCR embeddings derived từ raw OCR text nếu cần một space chuẩn mới;
- không phá existing embeddings.

---

# 38. OCR confidence filtering

Audit gợi ý filtering low confidence nhưng production threshold không nên hardcode chỉ từ lý thuyết.

Tier 1:

```text
keep raw all
mark confidence
soft penalty low confidence
filter obvious empty/noise
```

Sau benchmark mới chọn threshold.

Lý do: một OCR confidence thấp vẫn có thể chứa entity duy nhất cần tìm.

---

# 39. OCR bbox use

Bounding box phục vụ:

- highlight text trên thumbnail;
- xác minh visible text;
- detect repeated fixed logo/ticker zones;
- later dedup persistent overlay.

Không chỉ lưu text.

---

# 40. OCR duplicate suppression

TV overlay có thể lặp qua hàng chục frames.

Derived clustering:

```text
same video
near time
similar normalized text
similar bbox
```

→ một OCR track/cluster.

UI có thể collapse cluster, nhưng raw observations giữ nguyên.

Tier 2.

---

# 41. OCR ưu/nhược

Ưu:

- exact visible entities;
- news headline/lower third;
- ingredient list;
- signs/locations;
- numbers.

Nhược:

- noisy spelling;
- repeated overlays;
- short garbage tokens;
- không hiểu action/scene.

---

# 42. Lane 6 — BTC Object Detection

## 42.1 Nguồn

Audit BTC:

- ~178,195 object JSON;
- detection class names;
- scores;
- bounding boxes;
- entity/class IDs.

Mỗi file map 1:1 vào BTC keyframe `n`.

---

# 43. BTC Object search

Tier 1 không cần vector DB.

Materialize:

```text
object_label → postings of btc_frame_id
```

kèm:

```text
confidence
bbox
```

Query object normalized:

```text
motorbike → Motorcycle
person → Person
```

---

# 44. Object confidence policy

Không global threshold cứng quá sớm.

Có thể:

- store all above source extraction threshold;
- rank by detector score;
- branch/object-specific threshold later;
- combine repeated evidence.

Absence trong detector không phải proof object không tồn tại.

---

# 45. BTC Object relation Tier 2

BBox cho phép derive simple relations:

```text
left/right
above/below
inside/overlap
near
```

Nhưng chỉ nên dùng:

- deterministic geometry;
- explicit derived flag;
- không gọi đó là Qwen-level semantic relation.

---

# 46. BTC Object ưu/nhược

Ưu:

- structured;
- bbox;
- calibrated-ish detector scores within model;
- independent visual evidence;
- explainable.

Nhược:

- closed label vocabulary;
- generic labels;
- object miss;
- không action/narrative;
- BTC frame space riêng.

---

# 47. Lane 7 — BTC Media-info

## 47.1 Nguồn

873 JSON với:

```text
title
description
keywords
author
publish_date
length
watch_url
...
```

---

# 48. Media-info role

Không phải frame truth.

Vai trò tốt:

```text
Program identity
video-level topic prior
channel/source filter
metadata lexical search
video discovery
```

Ví dụ:

- `60 Giây Official` → strong program prior;
- `Món Ngon Mỗi Ngày` → cooking program prior.

---

# 49. Media-info search

Tier 1:

```text
SQLite FTS5 on title/description/keywords/author
```

Optional dense:

```text
BGE-M3 metadata embedding
```

Tier 2 nếu benchmark chứng minh hữu ích.

---

# 50. Media-info hạn chế

Một description của news video có thể chứa nhiều story.

Không dùng:

```text
metadata term absent → frame absent
```

Không dùng metadata để xác định exact temporal segment trừ khi có timestamped chapters thật sự.

---

# 51. Lane 8 — Taxonomy / Program / Topic routing

Taxonomy không phải retrieval lane frame-level theo nghĩa thông thường, nhưng là routing lane.

Input:

```text
query branch candidates
```

Output:

```text
video bitset / region postings
```

Tier 1:

- Program bitsets;
- verified L25 subject bitsets;
- soft topic memberships có status.

---

# 52. Lane 9 — Region Search

Sau region materialization:

```text
ASR region summary
Qwen aggregate
OCR aggregate
facet postings
```

Region rank nằm giữa video và frame.

Không chặn single-lane frame search nếu region chưa có.

Tier 2 cho nhiều series, Tier 1 ưu tiên L21/L22 nếu cần news retrieval.

---

# 53. Text index architecture Tier 1

```text
SQLite FTS5
  ├── ASR
  ├── OCR
  ├── Media-info
  └── optional Qwen captions

FAISS BGE-M3
  ├── ASR semantic
  ├── Qwen semantic docs
  └── OCR semantic derived/index if needed
```

Lý do:

- lexical và dense phục vụ lỗi khác nhau;
- đơn giản;
- rebuildable;
- dễ trace.

---

# 54. FTS5/BM25 ưu điểm

- exact term tốt;
- no embedding compute at query beyond tokenizer;
- highlight;
- explainable;
- SQL filtering dễ;
- suitable metadata corpus.

Nhược:

- semantic paraphrase thấp;
- Vietnamese word segmentation/tokenization có thể cần normalization;
- OCR typo cần auxiliary fuzzy layer.

---

# 55. BGE-M3 dense ưu điểm

- multilingual semantic search;
- dùng chung text semantic space cho ASR/Qwen/OCR derived text;
- dễ FAISS;
- natural queries tốt.

Nhược:

- exact string không luôn tốt;
- cần encode all text collections;
- model/version contract;
- raw score không fusion trực tiếp với visual scores.

---

# 56. BGE-M3 sparse — Tier 2

Có thể thử như một text retrieval leg.

Ưu:

- lexical-semantic sparse representation;
- có thể bổ sung BM25.

Nhược:

- tăng complexity;
- cần benchmark xem có hơn BM25+dense không.

Không cần để blocker V1.

---

# 57. BGE-M3 multi-vector — Tier 2/3

Có tiềm năng cho reranking/late interaction.

Nhưng:

- index/runtime phức tạp hơn;
- chưa cần khi corpus text nhỏ-vừa và đã có dense+lexical.

Chỉ triển khai sau ablation.

---

# 58. FAISS index types

## IndexFlatIP — Tier 1 baseline

Ưu:

- exact nearest-neighbor;
- deterministic;
- dễ validate;
- corpus hiện tại đủ nhỏ để baseline rất giá trị.

Nhược:

- scan toàn vectors;
- scaling lớn hơn sẽ tốn compute.

Đề xuất:

**Luôn có FlatIP baseline cho evaluation.**

---

# 59. HNSW — Tier 2

Ưu:

- ANN nhanh;
- good recall/speed trade-off.

Nhược:

- cần tune;
- approximate;
- filtering/scoping implementation phức tạp hơn;
- cần measure Recall loss so với Flat.

Không bật chỉ vì “ANN nhanh hơn”.

---

# 60. IVF/PQ — Tier 3 cho corpus hiện tại

Chưa ưu tiên.

Dùng khi vector corpus tăng rất lớn hoặc memory/latency benchmark yêu cầu.

Đổi lấy approximation/compression complexity.

---

# 61. SQLite FTS5 + FAISS — stack chốt Tier 1

Vai trò:

```text
SQLite
→ metadata, mapping, filtering, FTS

FAISS
→ dense vector retrieval

Bitset
→ video pruning

Postings
→ structured facets
```

Ưu điểm lớn:

- ít thành phần vận hành;
- local-first;
- transparent;
- dễ benchmark/rebuild;
- phù hợp architecture hiện có.

---

# 62. Qdrant — Tier 2 alternative

Có thể hữu ích nếu sau benchmark cần:

- payload filtering trực tiếp trong vector search;
- named vectors;
- multi-stage hybrid queries;
- unified dense/sparse service;
- persistent vector DB server.

Ưu:

- query/filter ergonomics tốt;
- quản lý vector collections dễ.

Nhược:

- thêm service/dependency;
- migration/build complexity;
- không tự tăng retrieval quality nếu data/query strategy không đổi.

**Không chọn làm V1 default.**

---

# 63. OpenSearch / Elasticsearch-style engine — Tier 2/3

Có thể mạnh nếu cần:

- production-scale text search;
- BM25/fuzzy/query DSL;
- distributed serving;
- hybrid search.

Nhược:

- operational overhead lớn hơn nhu cầu hiện tại;
- duplicate metadata/index stack;
- debug/search behavior phức tạp.

Không ưu tiên V1.

---

# 64. Vespa — Tier 3

Mạnh cho:

- sophisticated ranking pipelines;
- tensor/vector + lexical + structured filters;
- large-scale serving.

Nhưng architecture/ops learning cost cao.

Chỉ cân nhắc nếu bài toán scale/ranking complexity vượt xa current scope.

---

# 65. Milvus — Tier 3

Mạnh ở distributed vector DB.

Không cần cho V1 nếu FAISS local đáp ứng.

---

# 66. LanceDB / embedded vector stores — Tier 2 experiment

Có thể tiện cho unified columnar+vector data exploration.

Nhưng project đã có SQLite + FAISS foundations; switching cần benchmark tangible benefit.

---

# 67. Parquet — storage Tier 2, không search engine

Có thể dùng cho:

- analytics snapshots;
- large normalized tables;
- offline batch/Arrow workflows;
- reproducible export.

Không thay SQLite hot metadata query trong V1.

---

# 68. RRF — Fusion Tier 1

Khi đã benchmark riêng lanes, fusion V1 nên dùng Reciprocal Rank Fusion.

```text
RRF(doc) = Σ 1/(k + rank_lane(doc))
```

Ưu:

- không cần raw scores cùng scale;
- robust;
- simple/explainable;
- dễ ablation.

Nhược:

- bỏ qua magnitude raw score;
- `k` và grouping entity cần chọn;
- lanes chất lượng thấp vẫn có thể contribute noise.

---

# 69. Fusion entity phải xác định rõ

Có thể fuse ở:

```text
frame
video
temporal cluster
region
```

Không fuse blindly BTC frame ID với custom frame ID vì khác frame space.

Đề xuất:

1. canonicalize về `video_id + timestamp`;
2. temporal-cluster nearby hits;
3. fuse cluster/video support;
4. giữ representative frames của từng space.

---

# 70. Weighted RRF — Tier 2

Sau benchmark lane reliability:

```text
weighted RRF = Σ w_lane / (k + rank)
```

Weights phải từ evaluation, không từ cảm giác.

Có thể query-dependent sau này.

---

# 71. Score normalization — Tier 2

Nếu muốn dùng raw scores:

- per-lane calibration;
- percentile/rank normalization;
- z-score theo query distribution;
- logistic calibration từ GT.

Không dùng min-max ad hoc rồi coi là probability.

---

# 72. Cross-encoder reranker — Tier 2

Text candidates:

```text
query + candidate text
↓
reranker
```

Có thể dùng multilingual reranker trên Top 20–100.

Good for:

- ASR;
- OCR semantic;
- Qwen caption;
- video/region profile.

Không rerank toàn corpus.

---

# 73. Visual reranker — Tier 3

Cross-modal reranking bằng larger vision-language model có thể tăng quality nhưng:

- latency lớn;
- implementation phức tạp;
- cần benchmark.

Không blocker.

---

# 74. LLM rerank — Tier 3 / diagnostic

Không nên dùng LLM free-form để rerank hàng trăm frames production mặc định.

Có thể dùng:

- debug;
- explainability;
- top few candidates;
- hard query experiment.

Không coi là core retrieval engine.

---

# 75. Sequence retrieval technologies

Sequence không cần model mới.

Core:

```text
per-step independent lane retrieval
+
group by video
+
sort by timestamp
+
ordered temporal matching
```

Có thể dùng:

- two-pointer for 2 steps;
- dynamic programming/beam for 3–5 steps;
- interval constraints.

Chi tiết ở file 04.

---

# 76. Temporal region technologies

Signals:

```text
ASR continuity/topic change
shot boundaries
Qwen semantic change
OCR lower-third/headline changes
keyframe gaps
```

Tier 1 cho news có thể rule/heuristic.

Tier 2:

- embedding change-point detection;
- learned boundary ranker.

Không cần LLM per frame.

---

# 77. Nearest keyframe lookup technology

Không cần vector DB.

Per video sorted arrays:

```text
timestamps[]
```

binary search:

```text
nearest_before
nearest_after
nearest_absolute
```

O(log N).

Đây là Data Hub utility, dùng mọi lane.

---

# 78. Exact frame extraction technology

Source video authority:

```text
ffprobe/metadata
ffmpeg extraction
```

Mapping:

```text
video_id + frame_idx/timestamp
→ exact JPEG preview
```

Không phụ thuộc keyframe tồn tại.

File 04 mô tả caching/media path.

---

# 79. Media serving stack Tier 1

Existing direction:

- HTTP Range video streaming;
- source resolver;
- exact-frame API;
- timeline seek;
- frame stepping.

Không load toàn video vào browser memory trước khi seek.

---

# 80. Index Registry mandatory

Mỗi vector index phải có metadata:

```text
index_id
lane
model_id
model_revision
embedding_dim
normalization
metric
row_count
row_map_checksum
source_manifest_checksum
created_at
```

Nếu mismatch → fail closed lane.

Không “thử load xem chạy không”.

---

# 81. Query encoder registry

Tương tự:

```text
lane
model_id
processor_config
max_length
normalization
output_dim
```

Startup validate encoder compatible index.

Đây là cách tránh lỗi kiểu SigLIP preprocessing khác dẫn đến Top-K tào lao.

---

# 82. Lane health endpoint

Mỗi lane trả:

```text
OK
DEGRADED
UNAVAILABLE
```

và reason:

```text
INDEX_MISSING
ROW_MAP_MISMATCH
ENCODER_MISMATCH
MODEL_LOAD_FAILED
DATA_COVERAGE_PARTIAL
```

UI hiển thị badge.

---

# 83. Latency instrumentation

Per lane:

```text
query_encode_ms
filter_ms
search_ms
map_result_ms
rerank_ms
total_ms
```

Không chỉ tổng API latency.

---

# 84. Quality instrumentation

Per query/lane:

```text
result_count
unique_videos
score distribution
top1-top2 margin
GT rank if available
```

Giúp phát hiện encoder/index mismatch.

Ví dụ toàn scores gần nhau bất thường → warning.

---

# 85. Lane-specific query variants

### SigLIP

- original query;
- concise visual rewrite.

### BTC CLIP

- original/English visual rewrite if needed.

### ASR

- original narrative;
- spoken-content terms.

### OCR

- exact text variant;
- normalized/fuzzy variant;
- semantic variant.

### Qwen

- facet query;
- caption semantic query.

Không force same string mọi lane.

---

# 86. Translation policy

Nếu visual model/search quality tốt hơn với English query, translation có thể là derived query variant.

Nhưng:

```text
original Vietnamese query preserved
translation version recorded
```

Compare:

```text
original vs translated
```

trước khi default.

---

# 87. Query expansion Tier 2

Dựa trên controlled dictionary:

```text
xe máy → motorcycle, motorbike
chảo → pan, frying pan
```

Không free expansion vô hạn.

Per lane expansion can differ.

---

# 88. Facet rarity weighting

Object `person` quá phổ biến.

Object `lion dance costume` hiếm hơn.

Postings có document frequency giúp weight:

```text
idf-like rarity
```

Tier 1 cho structured Qwen/Object lane có thể hữu ích.

Nhưng rare hallucinated term có thể overweight, nên cap weights.

---

# 89. Video profile retrieval

Derived profile per video:

```text
program/topic memberships
ASR summary/topics
Qwen dominant objects/actions/scenes
OCR dominant entities
media metadata
```

Tier 1 dùng cho video rerank, không canonical truth.

Embedding profile bằng BGE-M3 là Tier 2/possibly Tier 1 nếu dễ build.

---

# 90. Region profile retrieval

Tương tự video profile nhưng temporal.

Rất có giá trị cho news.

Build sau region materialization.

---

# 91. Technology tiers tổng hợp

## Tier 1 — NÊN TRIỂN KHAI

```text
SQLite canonical/runtime metadata
SQLite FTS5/BM25
OCR fuzzy/trigram auxiliary index
FAISS IndexFlatIP baseline
SigLIP2 custom text-to-image search
BTC CLIP ViT-B/32 search
BGE-M3 dense text embeddings
Qwen normalized facet postings + dense caption search
ASR lexical + dense
OCR lexical/fuzzy + dense where model contract known
BTC object postings
Media-info FTS
video bitsets
rank-based RRF after lane benchmark
ffmpeg exact-frame resolver
```

---

# 92. Tier 2 — SAU BENCHMARK

```text
FAISS HNSW
BGE-M3 sparse
BGE reranker Top-N
weighted RRF
score calibration
adaptive K
query expansion dictionary
image-as-query
Qdrant as optional vector service
region embeddings
OCR track clustering
bbox-derived simple relations
learned lane selection
```

---

# 93. Tier 3 — EXPERIMENTAL / KHÔNG ƯU TIÊN

```text
Vespa migration
Milvus distributed cluster
OpenSearch full migration
IVF-PQ unless scale demands
ColBERT-style late interaction full corpus
large VLM online reranking all frames
LLM agent autonomous retrieval loops
end-to-end learned fusion without ablation
```

Không phải vì các công nghệ này “xấu”, mà vì chưa có evidence chúng giải quyết bottleneck hiện tại tốt hơn stack đơn giản.

---

# 94. Final stack recommendation

**Chốt V1 production architecture:**

```text
DATA / METADATA
SQLite
JSONL canonical
optional Parquet analytics export

LEXICAL
SQLite FTS5/BM25
OCR trigram/fuzzy auxiliary

TEXT SEMANTIC
BGE-M3 dense
FAISS FlatIP baseline

CUSTOM VISUAL
SigLIP2 matching encoder
FAISS

BTC VISUAL
CLIP ViT-B/32 matching encoder
FAISS

STRUCTURED SEMANTIC
Qwen normalized postings
BTC object postings
video bitsets

FUSION
RRF

RERANK (later)
multilingual cross-encoder Top-N

MEDIA
source video + HTTP Range + ffmpeg exact-frame extraction
```

---

# 95. Vì sao stack này được chốt?

Không vì “công nghệ mới nhất”, mà vì:

1. Từng lane dễ benchmark riêng.
2. Mapping transparent.
3. Raw data không bị khóa vào một DB vendor.
4. Index có thể rebuild.
5. Fusion không đòi calibration sớm.
6. Dễ giữ BTC/custom frame spaces riêng.
7. Dễ trace error.
8. Có đường nâng cấp lên vector DB/reranker sau.

---

# 96. Những công nghệ không được thay thế lẫn nhau

```text
BM25 != BGE
BGE != SigLIP
SigLIP != CLIP index compatibility
Qwen != OCR
OCR != ASR
Taxonomy != retrieval evidence
Media-info != frame semantics
```

Kiến trúc mạnh vì **cộng các evidence độc lập**, không vì chọn “model thắng tất cả”.

---

# 97. Benchmark matrix bắt buộc

Mỗi lane:

```text
Recall@1/5/20/50/100
video recall
frame/temporal recall
first correct rank
latency p50/p95
coverage
failure reason
```

Text hybrid:

```text
lexical only
dense only
lexical+dense RRF
```

Visual:

```text
SigLIP only
BTC CLIP only
both independent
```

---

# 98. Technology decision rule

Một Tier 2 technology chỉ được promote nếu cải thiện một trong:

```text
Recall
First correct rank
Latency
Robustness
Operator usability
Operational simplicity
```

và không gây regression lớn ở metric khác.

Không promote vì benchmark synthetic duy nhất hoặc “được cộng đồng dùng”.

---

# 99. Search lane Definition of Done

Mỗi lane phải có:

```text
[ ] documented source data
[ ] documented ID space
[ ] documented query encoder/preprocessing
[ ] validated index row map
[ ] health check
[ ] standalone API
[ ] standalone UI mode
[ ] latency metrics
[ ] benchmark results
[ ] canonical evidence output
[ ] failure taxonomy
[ ] no fake/mock data in production
```

---

# 100. Lane priority implementation order

Đề xuất:

```text
1. SigLIP2 custom
2. BTC CLIP
3. ASR lexical+dense
4. OCR lexical/fuzzy (+ dense if contract verified)
5. Qwen structured+dense
6. BTC Objects
7. Media-info
8. region/profile lanes
```

Có thể parallelize sau khi Data Hub contract ổn.

Lý do không phải quality ranking tuyệt đối, mà để sớm có:

- hai independent visual baselines;
- text baseline;
- OCR baseline;
- semantic structured lane;
- compare dashboard.

---

# 101. Integration order

```text
standalone lane
↓
canonical output
↓
Compare Mode
↓
scope filtering
↓
Manual Hybrid
↓
RRF
↓
Sequence
↓
Auto Brain routing
↓
Rescue policy
↓
Tier 2 rerank/ANN
```

Không đảo thứ tự bằng cách build learned fusion trước standalone lane tests.

---

# 102. Quyết định chốt cuối file

1. **SigLIP2 và BTC CLIP luôn giữ index/query encoder riêng.**
2. **BGE-M3 chỉ dùng text semantic spaces.**
3. **ASR = lexical + dense hybrid.**
4. **OCR = lexical + fuzzy + dense, không dense-only.**
5. **Qwen = structured facet + text semantic, raw không bị overwrite.**
6. **BTC Objects = structured evidence/postings, absence không hard-negative.**
7. **Media-info = video prior/search, không frame truth.**
8. **FAISS FlatIP là baseline Tier 1; ANN chỉ sau benchmark.**
9. **SQLite FTS5 + FAISS + bitsets/postings là stack V1 chốt.**
10. **RRF là fusion Tier 1 sau khi standalone lanes đã được benchmark.**
11. **Qdrant và vector DB khác là Tier 2, không rewrite ngay.**
12. **Exact frame luôn quay về source video.**

---

# 103. Dependency sang các file khác

- Query modes/lane selection: `02_QUERY_BRAIN_SEARCH_MODES.md`
- Data identity/index registry: `01_DATA_HUB_MAPPING.md`
- Temporal chain/video/frame neighborhood: `04_TEMPORAL_MEDIA_INSPECTOR.md`
- Benchmark/promotion gates/milestones: `05_IMPLEMENTATION_EVALUATION_ROADMAP.md`

---

# 104. Definition of Done cho Search Stack V1

```text
[ ] SigLIP standalone PASS
[ ] BTC CLIP standalone PASS
[ ] ASR lexical PASS
[ ] ASR dense PASS
[ ] OCR lexical/fuzzy PASS
[ ] OCR dense path verified hoặc explicitly unavailable
[ ] Qwen normalized structured PASS
[ ] Qwen dense text PASS
[ ] BTC Object postings PASS
[ ] Media-info search PASS
[ ] All lane outputs map correctly to Data Hub
[ ] Compare Mode benchmark available
[ ] FlatIP baseline archived
[ ] Index/encoder compatibility startup gate PASS
[ ] RRF ablation available before default fusion
```

Khi tất cả mục này hoàn thành, hệ thống có một **retrieval substrate độc lập, explainable và đủ an toàn để Auto Brain/Fusion phát triển phía trên mà không phải viết lại từng lane**.
