# 01 — DATA HUB & UNIFIED MAPPING

## Trung tâm dữ liệu chung cho BTC + Custom + Qwen + OCR + ASR + Taxonomy

> **Vai trò tài liệu:** định nghĩa cách mọi nguồn dữ liệu được đăng ký, định danh, liên kết và đưa vào runtime mà không làm mất dữ liệu gốc.
> **Nguyên tắc:** **Raw immutable → Canonical normalized → Runtime rebuildable.**

---

# 1. Tại sao Data Hub là việc phải làm trước Search Engine?

Hiện hệ thống đã có nhiều nguồn mạnh nhưng chúng đang được sinh ra bởi các pipeline khác nhau:

```text
BTC keyframes
BTC map-keyframes
BTC CLIP
BTC objects
BTC media-info

Custom keyframes
Custom SigLIP2
Qwen semantics
Custom OCR

Whisper ASR
Taxonomy / Program / Topic
Source videos
```

Nếu xây từng search script độc lập mà không có mapping chung, rất nhanh sẽ xuất hiện các lỗi:

- SigLIP trả `embedding_index=125` nhưng UI không biết ảnh nào.
- Qwen trả `frame_idx=426` nhưng OCR chỉ biết `000002.jpg`.
- BTC object `155.json` bị hiểu nhầm là custom keyframe 155.
- ASR hit đúng 14.2s nhưng kết quả visual chỉ biết ordinal keyframe.
- sequence engine không thể so `t1 < t2` vì lane A/B dùng timestamp format khác nhau.
- click result không resolve được source video/exact frame.
- fusion không biết hai hits từ BTC/custom thực ra nằm gần cùng thời điểm trong một video.

Data Hub giải bài toán này bằng cách biến tất cả kết quả thành các **entity có identity rõ ràng**.

---

# 2. Data Hub không phải “copy tất cả vào một database”

Thiết kế đúng:

```text
                    DATA HUB
                       │
      ┌────────────────┼─────────────────┐
      │                │                 │
 CANONICAL IDs     METADATA/JOIN      ARTIFACT REGISTRY
      │                │                 │
      └────────────────┼─────────────────┘
                       │
                       ▼
               RUNTIME INDEXES
```

Dữ liệu lớn vẫn có thể nằm ở file gốc:

```text
MP4
JPEG
NPY
FAISS
raw JSONL
```

SQLite không cần nuốt toàn bộ vector/image/video bytes.

SQLite chỉ cần biết:

> **Cái gì là gì, nằm ở đâu, thuộc video/frame/time nào, và index row nào tham chiếu tới nó.**

---

# 3. Ba tầng dữ liệu

## 3.1 Tầng A — RAW / SOURCE AUTHORITY

Không sửa trực tiếp.

Ví dụ:

```text
source videos
BTC keyframe JPEGs
BTC map CSV
BTC object JSON
BTC CLIP NPY
BTC media-info JSON

output_llm/shard_000.jsonl
custom keyframe metadata source
OCR metadata/vector shards
ASR output artifacts
```

Raw dùng để:

- audit;
- reproduce;
- rebuild canonical/index;
- debug sai lệch.

### Quy tắc

- Không đổi key raw Qwen để “khớp schema”.
- Không clean OCR rồi overwrite raw text.
- Không rewrite BTC CSV.
- Không merge hai frame spaces vào một file raw mới rồi bỏ nguồn cũ.

---

## 3.2 Tầng B — CANONICAL MACHINE DATA

Đây là dữ liệu đã được chuẩn hóa về:

- stable IDs;
- relative paths;
- integer milliseconds;
- explicit frame space;
- schema version;
- provenance;
- missing status.

Canonical files là input để build runtime.

Ví dụ:

```text
video_catalog.jsonl
btc_keyframe_catalog.jsonl
custom_keyframe_catalog.jsonl
asr_segments.jsonl
qwen_semantics_normalized.jsonl
ocr_text_catalog.jsonl
media_info_catalog.jsonl
taxonomy_nodes.jsonl
video_memberships.jsonl
```

---

## 3.3 Tầng C — DERIVED RUNTIME

Có thể xóa và rebuild.

```text
mapping.sqlite
FTS indexes
FAISS indexes
video bitsets
facet postings
region postings
video profiles
query caches
thumbnail caches
```

Nếu runtime corrupted:

```text
delete runtime/
→ rebuild from canonical
```

Không cần inference lại Qwen/OCR/ASR.

---

# 4. Source Registry — danh bạ nguồn dữ liệu

Trước khi build mapping, tạo một registry duy nhất.

Ví dụ:

```json
{
  "source_id": "qwen_raw_v1",
  "source_type": "QWEN_SEMANTICS",
  "scope": "CUSTOM_KEYFRAME",
  "path": "output_llm/shard_000.jsonl",
  "record_count": 116587,
  "schema_version": "qwen_raw_observed_v1",
  "checksum": "...",
  "status": "READY",
  "notes": ["180 custom keyframes missing Qwen"]
}
```

Mỗi nguồn nên có:

```text
source_id
source_type
path/uri
schema_version
record_count
checksum
coverage scope
producer/model
created_at nếu biết
status
notes
```

### Tại sao cần registry?

Để không tồn tại tình huống:

```text
"file này là OCR nào nhỉ?"
"CLIP index này encode bằng model nào?"
"Qwen này chạy prompt version nào?"
"metadata đang map với NPY mới hay cũ?"
```

---

# 5. Identity model — phần quan trọng nhất

# 5.1 Video identity

Organizer ID giữ nguyên:

```text
L21_V001
L26_V361
```

Đây là **canonical identity** xuyên suốt hệ thống.

Không tạo duplicate video entity theo Program/Topic.

---

# 5.2 Video ordinal

Cho 873 video, tạo ordinal deterministic:

```text
0 ... 872
```

Ordinal chỉ dùng cho:

- bitsets;
- compact runtime operations.

Ordinal **không thay thế `video_id`**.

Mỗi ordinal map phải có `ordinal_space_id` để bitset build A không bị load với map build B.

---

# 5.3 Frame identity — không được chỉ có `frame_idx`

`frame_idx=426` chỉ có nghĩa khi đi cùng video.

Canonical physical location:

```text
(video_id, frame_idx)
```

Timestamp dùng làm integrity/time join:

```text
(video_id, timestamp_ms)
```

Nhưng keyframe identity còn phải biết nó đến từ sampling nào.

---

# 5.4 BTC frame space

BTC có keyframe sampling riêng.

Canonical ID đề xuất:

```text
BTC:L21_V001:KF000001
BTC:L21_V001:KF000002
```

Record:

```json
{
  "keyframe_uid": "BTC:L21_V001:KF000002",
  "frame_space": "BTC",
  "video_id": "L21_V001",
  "local_keyframe_no": 2,
  "frame_idx": 90,
  "timestamp_ms": 3000,
  "fps": 30.0,
  "image_relpath": "data_extracted/keyframes/L21_V001/002.jpg",
  "clip_row": 1
}
```

BTC audit cho thấy map-keyframes cung cấp `n`, `pts_time`, `fps`, `frame_idx` và row NPY correspond với keyframe count. Đây là nền để materialize BTC catalog.

---

# 5.5 Custom frame space

Custom sampling phải có namespace riêng.

```text
CUSTOM:L21_V001:KF000001
CUSTOM:L21_V001:KF000002
```

Record nên giữ:

```text
video_id
local keyframe ID
frame_idx
timestamp_ms
shot_id
cluster_id
embedding_index
image_relpath
```

Audit Qwen/custom metadata hiện xác nhận:

```text
116,767 custom keyframes
unique mapping Qwen by (video_id, frame_idx)
```

---

# 5.6 BTC và CUSTOM không cần 1:1

Ví dụ:

```text
BTC:
  13.0s

CUSTOM:
  12.7s
  14.2s
```

Đây là bình thường.

Không tạo fake mapping:

```text
BTC KF 100 = CUSTOM KF 100
```

Nếu cần cross-space comparison, dùng:

```text
same video
+ nearest timestamp
```

với tolerance rõ ràng.

---

# 6. Time model

Canonical time dùng:

```text
integer milliseconds
```

Ví dụ:

```text
14.2s → 14200 ms
```

Lý do:

- tránh float drift;
- dễ SQL range queries;
- dễ sequence gap calculation;
- dễ serialize.

Raw `pts_time` float vẫn có thể giữ trong provenance nếu cần.

---

# 7. Path model

Không canonicalize absolute path như:

```text
/content/drive/MyDrive/AIC_2026/...
```

Canonical chỉ lưu:

```text
output/keyframes/L21_V001/000002.jpg
```

Runtime có:

```text
AIC_ROOT
```

và resolver:

```text
resolve(relpath) = AIC_ROOT / relpath
```

Điều này giữ data portable giữa các môi trường mà không rewrite catalog.

---

# 8. Video Catalog

Bảng/file authority:

```text
video_id
ordinal
series
source_relpath
duration_ms
status flags
```

Có thể chứa summary metadata nhẹ nhưng không nhét topic arrays làm membership truth.

Ví dụ:

```json
{
  "video_id": "L25_V008",
  "ordinal": 214,
  "series": "L25",
  "source_relpath": "data_extracted/video/L25_V008.mp4",
  "duration_ms": 1206980,
  "flags": []
}
```

---

# 9. Media-info Catalog

BTC media-info được chuẩn hóa theo video.

```text
video_id PK/FK
author
title
description
keywords_json
publish_date
channel_id
watch_url
thumbnail_url
```

Search index:

- title high boost;
- keywords high/medium boost;
- description lower boost vì dài/nhiễu.

Media-info tạo **video prior**, không tạo frame evidence.

---

# 10. ASR Catalog

Canonical segment:

```json
{
  "segment_uid": "ASR:L21_V001:S000177",
  "video_id": "L21_V001",
  "start_ms": 14000,
  "end_ms": 18000,
  "text": "...",
  "normalized_text": "...",
  "language": "vi"
}
```

### Các join quan trọng

Frame → nearby ASR:

```sql
WHERE video_id = ?
AND end_ms >= frame_time - context_before
AND start_ms <= frame_time + context_after
```

Không cần copy ASR text vào mỗi frame row.

---

# 11. Qwen Catalog

## 11.1 Raw giữ nguyên

Observed raw schema:

```text
video_id
frame_idx
pts_time
objects[]
attributes[]
spatial_relations[]
counts[]
scene[]
visible_actions[]
caption
```

## 11.2 Join key

```text
(video_id, frame_idx)
```

Integrity:

```text
timestamp match
```

## 11.3 Missing Qwen

180 keyframes không Qwen phải tồn tại:

```text
semantic_status = MISSING
```

Không drop frame khỏi catalog.

## 11.4 Normalize nhưng không phá raw

Derived semantic record:

```json
{
  "keyframe_uid": "CUSTOM:L21_V001:KF000002",
  "raw": {
    "objects": ["road", "water"],
    "scene": ["flooded area"]
  },
  "normalized": {
    "objects": [
      {
        "facet_id": "object.road",
        "raw_text": "road",
        "method": "dictionary_exact",
        "normalization_score": 1.0,
        "source_model_score": null
      }
    ]
  }
}
```

Không hiểu `normalization_score` là Qwen confidence.

---

# 12. OCR Catalog

OCR cần audit mapping chi tiết trước khi import production vì audit hiện mô tả metadata có thể là `keyframe_id` **hoặc** `frame_idx`.

Canonical mục tiêu:

```json
{
  "ocr_uid": "OCR:...",
  "video_id": "L21_V001",
  "frame_space": "CUSTOM_OR_EXPLICIT",
  "keyframe_uid": "...",
  "frame_idx": 426,
  "timestamp_ms": 14200,
  "raw_text": "Ho Chi Mnh",
  "normalized_text": "ho chi mnh",
  "accentless_text": "ho chi mnh",
  "bbox": [0.1, 0.8, 0.2, 0.95],
  "ocr_confidence": 0.945,
  "embedding_ref": {
    "shard": 0,
    "row": 231
  }
}
```

### Mapping policy

Priority:

1. explicit `frame_idx` if reliable;
2. `(video_id, keyframe filename/id)` → correct frame-space catalog;
3. timestamp derived from catalog;
4. unresolved → manual/audit queue, không đoán.

### Raw/normalized fields

Giữ đồng thời:

```text
raw_text
unicode_normalized
accentless_text
trigram representation (derived/index only)
```

Không overwrite raw OCR.

---

# 13. BTC Object Catalog

BTC object JSON gắn 1:1 với BTC JPEG keyframe ordinal.

Canonical:

```text
detection_uid
keyframe_uid BTC:...
class_name
class_entity
class_label
confidence
bbox
```

Có thể explode JSON → rows trong SQLite hoặc import lazily + postings.

### Index đề xuất

```text
normalized_object_name → posting list of BTC keyframe_uids
```

Detector confidence dùng để:

- threshold/filter;
- rank support.

Nhưng:

```text
no detection != object absent
```

Không dùng detector miss làm hard negative.

---

# 14. Taxonomy Canonical Model

## 14.1 Nodes

```text
branch_id
branch_type
parent_ids
labels
aliases
description
active
```

## 14.2 Memberships

```text
membership_id
entity_scope VIDEO|REGION
video_id / region_id
branch_id
status VERIFIED|INFERRED|...
confidence
score_type
evidence
prune_override
```

Một video có nhiều membership là bình thường.

### Không lưu taxonomy dạng

```text
News
 └── videos: [873 IDs...]
```

làm canonical truth.

Nested view chỉ generate cho UI/report.

---

# 15. Facet Dictionary

Qwen/OCR/query sẽ tạo nhiều alias.

Ví dụ:

```text
motorbike
motorcycle
xe máy
```

normalize thành:

```text
object.motorcycle
```

Facet record:

```json
{
  "facet_id": "object.motorcycle",
  "namespace": "object",
  "labels": {"vi": "xe máy", "en": "motorcycle"},
  "aliases": ["motorbike", "xe may"],
  "active": true
}
```

Raw text vẫn được giữ trong evidence.

---

# 16. Temporal Regions

Region không phải raw source; region là derived-but-versioned semantic segmentation.

```text
region_id
video_id
start_ms
end_ms
region_type
segmentation_run_id
summary
evidence signals
```

Nếu rebuild boundaries:

```text
segmentation_run_id thay đổi
→ dependent region memberships/postings rebuild
```

---

# 17. SQLite Runtime Schema — phiên bản đề xuất

```sql
CREATE TABLE videos (...);
CREATE TABLE media_info (...);
CREATE TABLE keyframes (...);
CREATE TABLE asr_segments (...);
CREATE TABLE qwen_semantics (...);
CREATE TABLE ocr_texts (...);
CREATE TABLE btc_objects (...);
CREATE TABLE taxonomy_nodes (...);
CREATE TABLE video_memberships (...);
CREATE TABLE temporal_regions (...);
CREATE TABLE region_memberships (...);
CREATE TABLE artifacts (...);
CREATE TABLE indexes (...);
```

---

# 18. SQL indexes tối thiểu

```text
videos(video_id)
keyframes(video_id, timestamp_ms)
keyframes(frame_space, video_id, frame_idx)
asr_segments(video_id, start_ms, end_ms)
ocr_texts(video_id, timestamp_ms)
btc_objects(keyframe_uid, class_name)
video_memberships(branch_id, video_id)
video_memberships(video_id, branch_id)
temporal_regions(video_id, start_ms, end_ms)
region_memberships(branch_id, region_id)
```

---

# 19. FTS tables

Tách logical documents:

```text
fts_asr
fts_ocr
fts_qwen_caption
fts_media
```

Không concat tất cả vào một text document khổng lồ vì sẽ mất ability:

- route query;
- tune lane;
- explain match;
- benchmark modality.

---

# 20. OCR fuzzy auxiliary index

Vì OCR nhiễu, tạo derived field/index cho:

```text
lowercase
unicode normalize
accentless
character trigrams
```

Query OCR có thể chạy:

```text
exact lexical
BM25
trigram fuzzy
BGE semantic
```

rồi combine **bên trong OCR lane** trước khi OCR lane tham gia global fusion.

---

# 21. Vector indexes

Không tạo một index chứa vectors từ model khác nhau.

## 21.1 SigLIP2

```text
index: siglip_custom.faiss
entity: CUSTOM keyframe
row map: siglip_row → keyframe_uid
```

## 21.2 BTC CLIP

```text
index: btc_clip.faiss
entity: BTC keyframe
row map: clip_row → BTC keyframe_uid
```

## 21.3 BGE-M3 text

Có thể tách theo corpus:

```text
bge_asr.faiss
bge_ocr.faiss
bge_qwen_caption.faiss
bge_media.faiss
```

hoặc một BGE text index có explicit `doc_type` + metadata filter, nhưng benchmark/debug đơn giản hơn nếu V1 tách logical lane/index.

---

# 22. Index row maps là mandatory

Một FAISS row không có ý nghĩa nếu không có mapping.

Ví dụ:

```json
{
  "index_id": "siglip_custom_v1",
  "row": 91234,
  "keyframe_uid": "CUSTOM:L26_V123:KF000153"
}
```

Validation:

```text
vector row count == row map count
all keyframe_uid exists
no duplicate row
```

---

# 23. Bitsets cho video-level pruning

873 video → 873 bits.

Một branch bitset khoảng:

```text
ceil(873 / 8) ≈ 110 bytes
```

Ví dụ:

```text
program.education.exam_prep
→ bitset of 88 videos
```

Runtime:

```text
candidate = bitmap(branchA) OR bitmap(branchB)
```

Không cần complex bitmap framework ở V1 nếu fixed bitset đủ.

---

# 24. Postings cho facets

Ví dụ normalized Qwen:

```text
object.motorcycle
→ custom keyframe IDs
```

Có thể có hai mức posting:

```text
frame posting
video posting
```

Frame posting dùng fine retrieval.

Video posting là aggregate để support SAFE pruning/ranking.

---

# 25. Video Search Profile

Derived cache, không canonical truth.

Ví dụ:

```json
{
  "video_id": "L26_V123",
  "program_ids": ["program.cooking"],
  "topic_ids": [],
  "dominant_objects": [],
  "dominant_actions": [],
  "dominant_scenes": [],
  "asr_summary": "...",
  "media_title": "...",
  "qwen_caption_summary": "..."
}
```

Profile hữu ích cho video rerank sau coarse retrieval.

Rebuild nếu underlying semantics/memberships thay đổi.

---

# 26. Mapping one result end-to-end

Ví dụ SigLIP hit:

```text
FAISS row 91234
↓ row map
CUSTOM:L26_V123:KF000153
↓ keyframes table
video_id L26_V123
frame_idx 1530
timestamp_ms 61200
image_relpath ...
↓ Qwen table
objects/actions/scene/caption
↓ ASR range query
nearby transcript
↓ taxonomy
program/topic
↓ source video
exact frame/video seek
```

Đây chính là lý do Data Hub phải tồn tại trước fusion.

---

# 27. Mapping BTC result end-to-end

```text
BTC CLIP row 154
↓ BTC row map
BTC:L21_V001:KF000155
↓ map-keyframes
frame_idx / timestamp
↓ BTC object detections
Person / Car / ...
↓ video
L21_V001
↓ nearby custom frames (optional nearest-time)
↓ ASR / Qwen comparison
↓ source video inspector
```

BTC hit không cần chuyển thành custom keyframe để được coi là valid result.

---

# 28. Nearest-keyframe service

Cần API utility:

```text
nearest_keyframe(video_id, timestamp_ms, frame_space)
```

Search bằng sorted timestamp index.

Dùng cho:

- sequence preview;
- cross-space comparison;
- +3s/+10s neighbor preview;
- fallback nếu exact desired timestamp không có sampled keyframe.

Output phải gồm delta:

```text
requested: 65.000s
nearest:   64.733s
delta:     -267ms
```

Không giả rằng nearest keyframe là exact desired frame.

---

# 29. Exact-frame resolver

API logic:

```text
(video_id, timestamp_ms)
OR
(video_id, frame_idx)
```

→ source video metadata
→ ffmpeg/existing media resolver
→ JPEG exact frame

Cache key:

```text
video_id + frame_idx + extraction_version
```

---

# 30. Data completeness statuses

Mỗi entity không nên chỉ có exists/not-exists.

Ví dụ custom keyframe:

```text
qwen_status = OK | MISSING | ERROR
ocr_status  = OK | NONE | UNMAPPED | UNKNOWN
siglip_status = OK | MISSING
```

Video:

```text
asr_status = OK | ZERO_ASR | ERROR
```

Điều này ngăn logic:

```text
missing signal → negative evidence
```

---

# 31. Provenance

Mỗi derived artifact cần biết:

```text
built_from
checksum
schema version
normalizer version
model/index version
build timestamp
```

Ví dụ facet posting:

```text
built from qwen_raw checksum X
normalizer V3
facet dictionary checksum Y
```

Nếu dictionary đổi → postings invalid → rebuild.

---

# 32. Build Manifest

Manifest tổng:

```json
{
  "build_id": "...",
  "video_space": "...",
  "btc_keyframe_space": "...",
  "custom_keyframe_space": "...",
  "sources": {},
  "canonical_artifacts": {},
  "runtime_indexes": {}
}
```

Tool startup phải fail-closed nếu:

- ordinal-space mismatch;
- vector/index metadata mismatch;
- checksum incompatible;
- schema version unsupported.

---

# 33. Validation Gate — Video

```text
video_count = 873
unique video_id = 873
ordinal count = 873
ordinal range = 0..872
source_relpath non-empty
```

---

# 34. Validation Gate — Custom keyframes/Qwen

```text
custom keyframes = 116,767
unique keyframe_uid = 116,767
unique (video_id, frame_idx) expected per audit
Qwen success = 116,587
Qwen join success = 116,587
Qwen orphan = 0
Qwen missing explicit = 180
```

---

# 35. Validation Gate — BTC

Cần materializer xác nhận bằng dữ liệu thật:

```text
873 map-keyframe files
873 media-info
873 CLIP feature files
N BTC JPEGs
N map rows
N CLIP rows
object files mapped to BTC keyframe IDs
```

Nếu audit report nói ~178,195, build thực tế phải thống kê exact N và freeze checksum thay vì phụ thuộc “~”.

---

# 36. Validation Gate — OCR

Trước production import phải chạy audit machine-level:

```text
embedding rows == metadata rows per shard
video_id all known
keyframe/frame refs mapped count
unmapped count
confidence field coverage
bbox validity
empty/noise text counts
```

Không lấy ví dụ schema trong report thay cho actual schema nếu actual file có khác biệt.

---

# 37. Validation Gate — ASR

```text
873 videos represented
107,540 segments expected from audit state
start_ms <= end_ms
segment timestamps inside video duration
14 zero-ASR retained
```

---

# 38. Data Hub APIs

Tối thiểu:

```text
get_video(video_id)
get_keyframe(keyframe_uid)
get_keyframes_near(video_id, t, space, window)
get_asr_near(video_id, t, window)
get_qwen(keyframe_uid)
get_ocr_near(video_id, t)
get_btc_objects(keyframe_uid)
get_memberships(video_id)
get_regions(video_id)
resolve_source_frame(video_id, frame_idx/timestamp)
```

Search providers không tự đọc raw filesystem tùy tiện; nên đi qua repository/mapping abstraction hoặc prebuilt index row maps.

---

# 39. Search Lane input từ Data Hub

## SigLIP

```text
FAISS → custom keyframe_uid → Data Hub enrich
```

## BTC CLIP

```text
FAISS → BTC keyframe_uid → Data Hub enrich
```

## Qwen

```text
FTS/BGE/posting → custom keyframe_uid
```

## OCR

```text
FTS/BGE → ocr_uid → frame/video/time mapping
```

## ASR

```text
FTS/BGE → segment_uid → video/time
```

## Objects

```text
posting → BTC keyframe_uid
```

Mọi lane cuối cùng đều ra canonical EvidenceResult.

---

# 40. Không concat mọi modality vào một “document”

Sai:

```text
VIDEO_TEXT = ASR + OCR + Qwen + title + keywords
→ one embedding
```

Vì:

- mất provenance;
- field dài thống trị embedding;
- không biết signal nào hit;
- sequence/frame locality mất;
- không benchmark lane độc lập được.

Có thể tạo **video profile summary** như derived rerank feature, nhưng không thay các source lanes.

---

# 41. Không duplicate taxonomy vào video catalog

Video catalog:

```text
identity + physical metadata
```

Membership table:

```text
video ↔ branch
```

Nếu copy topics vào video row và vẫn có membership table → hai source-of-truth sẽ drift.

---

# 42. Data Hub directory layout đề xuất

```text
retrieval_data/
├── manifest/
│   ├── build_manifest.json
│   ├── source_registry.jsonl
│   └── checksums.sha256
│
├── canonical/
│   ├── videos.jsonl
│   ├── btc_keyframes.jsonl
│   ├── custom_keyframes.jsonl
│   ├── media_info.jsonl
│   ├── asr_segments.jsonl
│   ├── qwen_semantics.jsonl
│   ├── ocr_texts.jsonl
│   ├── taxonomy_nodes.jsonl
│   ├── video_memberships.jsonl
│   └── facet_dictionary.jsonl
│
├── runtime/
│   ├── mapping.sqlite
│   ├── fts/
│   ├── vector/
│   ├── postings/
│   ├── bitsets/
│   └── profiles/
│
└── cache/
    ├── thumbnails/
    ├── exact_frames/
    └── preview_clips/
```

Raw large data có thể nằm ngoài `retrieval_data`; registry chỉ reference relative roots.

---

# 43. Migration strategy từ dữ liệu hiện có

## Step A — Freeze source checksums

Không sửa raw.

## Step B — Materialize BTC keyframe catalog

Từ:

```text
map-keyframes + keyframe directories + CLIP row shape
```

## Step C — Materialize/verify custom keyframe catalog

Đã có nền từ `df_keyframes.pkl`/Contract V1.1.

## Step D — Register Qwen

Join bằng `(video_id, frame_idx)`.

## Step E — OCR machine audit + mapping

Xác định chính xác OCR frame space/key mapping.

## Step F — Import ASR

## Step G — Import BTC media + objects

## Step H — Materialize taxonomy Program + verified branches

## Step I — Build SQLite/FTS

## Step J — Build vector row maps + validate indexes

---

# 44. Data Hub acceptance test — “one video drilldown”

Chọn bất kỳ `video_id`.

UI/dev command phải trả được:

```text
video metadata
media info
ASR count
program/topic memberships
BTC keyframe count
custom keyframe count
Qwen coverage
OCR coverage
BTC object coverage
SigLIP index rows
BTC CLIP index rows
```

---

# 45. Data Hub acceptance test — “one frame drilldown”

Custom frame:

```text
keyframe_uid
→ physical frame
→ timestamp
→ image
→ Qwen
→ OCR nếu có
→ nearby ASR
→ source video
→ exact frame
```

BTC frame:

```text
keyframe_uid
→ map row
→ image
→ CLIP vector row
→ objects
→ nearby ASR
→ source video
```

---

# 46. Cross-space timeline view

Một video timeline có thể hiển thị:

```text
0s ------------------------------------------------ 1200s

BTC KF      |  |    | |      |...
CUSTOM KF    |   | |   |     |...
ASR          ==== ==== =======
OCR            *      **
REGIONS      [------][---------]
```

Đây là abstraction rất mạnh cho:

- debugging;
- sequence search;
- operator inspection;
- sampling-gap diagnosis.

---

# 47. Vì sao không cần merge keyframes?

Hai samplings độc lập thực ra là lợi thế.

Nếu custom sampling miss cảnh đúng nhưng BTC có:

```text
BTC CLIP rescue
```

Nếu BTC sparse ở một đoạn nhưng custom có:

```text
SigLIP/Qwen hit
```

Merge vật lý chỉ làm mất provenance và tạo mapping phức tạp không cần thiết.

Shared timeline là đủ.

---

# 48. Data quality flags

Entity có thể có flags:

```text
ZERO_ASR
QWEN_MISSING
OCR_LOW_CONFIDENCE
OCR_UNMAPPED
BTC_OBJECT_EMPTY
PATH_MISSING
TIMESTAMP_OUT_OF_RANGE
INDEX_ROW_MISSING
MANUAL_REVIEW
```

Search lane dùng flags để xử lý mềm thay vì crash/drop silent.

---

# 49. Logging / trace

Mỗi query trace cần biết:

```text
build_id
query_id
query plan
candidate video count
lane indexes used
index versions
per-lane latency
result IDs
fusion decisions
rescue decisions
```

Nếu một result thay đổi sau rebuild, trace cho biết data/index version khác gì.

---

# 50. Các điều chưa được phép coi là VERIFIED

Dựa trên các audit hiện có, cần phân biệt:

- OCR report mô tả schema/chất lượng, nhưng production mapping coverage thực tế phải audit machine-level.
- BTC audit nói khoảng 178,195 keyframes; build cần exact count/checksum.
- Qwen raw semantic strings chưa phải controlled ontology.
- Taxonomy detailed Topic/Facet chưa đầy đủ toàn corpus.
- Temporal regions chưa materialize production.

Data Hub phải biểu diễn `UNKNOWN/UNVERIFIED`, không tự điền giả để “đủ cột”.

---

# 51. Quyết định chốt của Data Hub

1. **SQLite là relational runtime center**, không phải nơi chứa video/vector bytes.
2. **BTC và CUSTOM là hai frame spaces độc lập.**
3. **`video_id` là common parent identity.**
4. **Physical frame/time là cầu nối temporal.**
5. **Raw sources immutable.**
6. **Canonical files có relative paths + schema/version.**
7. **FAISS indexes có row maps + model manifests riêng.**
8. **FTS indexes tách theo modality.**
9. **Bitsets chỉ dùng video-level pruning.**
10. **Missing modality là status, không phải negative evidence.**
11. **Source video là exact-frame authority.**
12. **Mọi derived artifact phải rebuildable và checksum/provenance được.**

---

# 52. Kết quả cần đạt sau khi hoàn thành Data Hub

Khi Data Hub hoàn thành, team có thể chia task cực rõ:

```text
Dev A → SigLIP provider
Dev B → OCR provider
Dev C → ASR provider
Dev D → Qwen provider
Dev E → BTC provider
```

mà tất cả cùng gọi:

```text
Data Hub identity + canonical result contract
```

Không ai cần tự phát minh cách map lại `video/frame/time` trong từng script.

Đây là điều biến tập hợp các script rời rạc thành **một retrieval platform có thể mở rộng**.
