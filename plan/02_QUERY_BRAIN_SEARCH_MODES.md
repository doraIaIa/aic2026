# 02 — QUERY BRAIN & SEARCH MODES
## Thiết kế cách nhập truy vấn, phân tích truy vấn, chọn lane, pruning, sequence và operator control

> **Trạng thái:** Design freeze candidate  
> **Phạm vi:** Chỉ mô tả Query Workspace + Query Brain + Search Modes + Pruning/Rescue orchestration. Không mô tả chi tiết implementation của từng lane; phần đó nằm trong `03_SEARCH_LANES_TECH_STACK.md`.  
> **Nguyên tắc:** **LLM có thể gợi ý, operator có quyền sửa, retrieval engine mới là nơi quyết định bằng chứng.**

---

# 1. Mục tiêu của Query Brain

Query Brain không phải “một LLM trả đáp án”. Nó là lớp đứng giữa người vận hành và các search lane.

Nhiệm vụ của nó:

1. Giữ nguyên query gốc của BTC/user.
2. Phân tích query thành các thành phần có ích cho retrieval.
3. Nhận diện query có yếu tố thời gian/chuỗi cảnh hay không.
4. Gợi ý Program/Topic để ưu tiên video.
5. Gợi ý object/action/attribute/scene/text/entities.
6. Chọn lane nên chạy.
7. Chọn pruning mode.
8. Chuyển query thành các sub-query độc lập khi cần.
9. Cho operator xem và sửa mọi quyết định quan trọng trước khi search.
10. Ghi lại query plan để benchmark/failure analysis.

Query Brain **không được**:

- tự loại vĩnh viễn video chỉ vì “đoán chủ đề”;
- tự invent object/action không có căn cứ mà không đánh dấu là suggestion;
- thay thế query gốc bằng một bản tóm tắt duy nhất;
- ép mọi query vào cùng một lane;
- biến confidence của LLM thành retrieval truth;
- quyết định hard prune mà không qua routing policy/evaluation gate.

---

# 2. Vấn đề UX cần giải quyết

Nhóm đang có hai nhu cầu tưởng như mâu thuẫn:

### Nhu cầu A — nhập câu BTC nguyên bản

Ví dụ:

```text
Một người mặc áo xanh đi qua cổng chắn bằng xe máy.
```

Hoặc:

```text
Sau cảnh người phụ nữ đứng trước bảng thông báo là cảnh một xe tải đi ngang qua.
```

Ưu điểm:

- nhanh;
- giữ nguyên ý BTC;
- không mất quan hệ giữa các thành phần;
- phù hợp query dài/narrative.

Nhược điểm:

- LLM/parser có thể hiểu sai;
- operator khó biết engine đã search object nào/action nào;
- query có nhiều clause dễ bị “trộn nghĩa”.

### Nhu cầu B — nhập facet thủ công

Ví dụ:

```text
OBJECTS
[tomato] [+]
[pan]    [+]

ACTION
[frying]

SCENE
[kitchen]
```

Ưu điểm:

- kiểm soát tuyệt đối;
- debug dễ;
- rất hữu ích khi operator đã biết object cụ thể;
- có thể chạy từng lane độc lập.

Nhược điểm:

- mất câu gốc/narrative nếu chỉ dùng structured fields;
- tốn thao tác;
- operator có thể bỏ sót semantic relationship.

### Quyết định

**Không chọn một trong hai. Hệ thống phải hỗ trợ cả hai đồng thời.**

Natural query là authority về ý định gốc. Structured facets là lớp chỉnh sửa/override.

---

# 3. Query Workspace tổng thể

UI đề xuất:

```text
┌─────────────────────────────────────────────────────────────────────┐
│ ORIGINAL QUERY                                                      │
│ [ Một người áo xanh đi xe máy qua cổng chắn ...                  ] │
│                                                                     │
│ [ANALYZE] [SEARCH NOW]                                              │
├─────────────────────────────────────────────────────────────────────┤
│ QUERY PLAN                                                          │
│ Program:  [Auto: News ▼]   Topic: [Auto: Traffic ▼]                │
│                                                                     │
│ Objects:     [person ×] [motorcycle ×] [barrier ×] [+]             │
│ Attributes:  [green shirt ×] [+]                                   │
│ Actions:     [riding ×] [passing ×] [+]                            │
│ Scenes:      [road ×] [+]                                           │
│ OCR/Text:    [                    ] [+]                             │
│ ASR hints:   [                    ] [+]                             │
│                                                                     │
│ Temporal:  ○ none   ○ sequence   ○ before/after                    │
│                                                                     │
│ Pruning:   ○ OFF    ● SAFE       ○ AGGRESSIVE                      │
│                                                                     │
│ Lanes: ☑ SigLIP ☑ Qwen ☐ ASR ☐ OCR ☑ BTC CLIP ☐ BTC Object       │
├─────────────────────────────────────────────────────────────────────┤
│ MODE: [AUTO] [MANUAL HYBRID] [COMPARE] [SEQUENCE] [SINGLE LANE]   │
└─────────────────────────────────────────────────────────────────────┘
```

Quan trọng:

- query gốc luôn còn nguyên;
- facets có thể do brain gợi ý hoặc user nhập;
- operator có thể thêm/xóa từng chip;
- tất cả auto suggestions phải có trạng thái `AUTO_SUGGESTED`;
- user-entered facet có trạng thái `USER_PINNED`;
- user-pinned facet không bị Brain tự xóa.

---

# 4. Query Request Contract

Canonical request nên có dạng logic:

```json
{
  "original_query": "...",
  "mode": "AUTO",
  "pruning_mode": "SAFE",
  "program": {
    "selected": [],
    "suggested": []
  },
  "topic": {
    "selected": [],
    "suggested": []
  },
  "facets": {
    "objects": [],
    "attributes": [],
    "actions": [],
    "scenes": [],
    "relations": [],
    "visible_text": [],
    "asr_terms": [],
    "entities": [],
    "negative": []
  },
  "temporal": null,
  "lane_policy": {
    "siglip_custom": "AUTO",
    "btc_clip": "AUTO",
    "qwen": "AUTO",
    "asr": "AUTO",
    "ocr": "AUTO",
    "btc_object": "AUTO",
    "media_info": "AUTO"
  },
  "top_k": {
    "per_lane": 100,
    "final": 50
  }
}
```

`selected` và `suggested` phải tách riêng.

Không dùng một array duy nhất vì sẽ không biết cái nào là quyết định của operator.

---

# 5. Facet model

## 5.1 Object

Vật thể/tangible entity:

```text
person
motorcycle
car
barrier
pan
tomato
microphone
book
```

Nguồn search chính:

- Qwen objects;
- BTC Object Detection;
- SigLIP/CLIP semantic visual;
- OCR/ASR chỉ hỗ trợ nếu object được nhắc bằng chữ/lời.

Generic object như `person`, `table`, `food` không được hard-prune video.

---

## 5.2 Attribute

Đặc điểm:

```text
green shirt
red car
wooden table
large bowl
white uniform
```

Nguồn chính:

- Qwen attributes;
- SigLIP/CLIP visual;
- có thể suy lexical từ caption nhưng phải ghi provenance.

---

## 5.3 Action

Hành động nhìn thấy:

```text
riding
walking
pouring
cutting
stirring
handing object
raising hand
```

Nguồn chính:

- Qwen `visible_actions`;
- SigLIP2 natural-language visual retrieval;
- temporal sequence evidence nếu action cần nhiều frame.

Không biến một object thành action bằng rule đơn giản.

---

## 5.4 Scene

Bối cảnh:

```text
kitchen
classroom
road
news studio
market
riverbank
stage
```

Nguồn:

- Qwen `scene`;
- visual embeddings;
- BTC media-info chỉ là video prior, không phải frame truth.

---

## 5.5 Relation

Quan hệ:

```text
person left of motorcycle
woman behind table
logo top-right
bowl on table
```

Nguồn chính:

- Qwen spatial relations.

BTC object bounding boxes có thể hỗ trợ một số relation hình học đơn giản nhưng không nên suy diễn quá mạnh nếu chưa benchmark.

---

## 5.6 Visible text / OCR

Ví dụ:

```text
Đại học Cần Thơ
2024
Vĩnh Long
NGUYÊN LIỆU
```

Nguồn:

- OCR raw;
- OCR lexical fuzzy;
- OCR embedding.

Không dùng Qwen description thay thế OCR khi query cần exact visible text.

---

## 5.7 ASR terms / spoken content

Ví dụ:

```text
lãi suất
ngân hàng nhà nước
sạt lở
phương trình lượng giác
```

Nguồn:

- Whisper ASR segments;
- lexical + dense retrieval.

---

## 5.8 Entity

Named entity có thể xuất hiện trong:

- ASR;
- OCR;
- Media-info.

Ví dụ:

```text
Cần Thơ
Nguyễn Văn A
Bệnh viện Chợ Rẫy
Mekong
```

Một entity không mặc định có nghĩa là visual object.

---

## 5.9 Negative constraint

Rất hữu ích khi kết quả nhiễu:

```text
NOT cooking
NOT studio
without text overlay
not red
```

Phase đầu nên dùng negative constraints chủ yếu như rerank/penalty, không hard-prune, vì negative evidence thường kém đáng tin hơn positive evidence.

---

# 6. Query Brain pipeline

```text
ORIGINAL QUERY
      │
      ▼
NORMALIZATION
      │
      ▼
TEMPORAL DETECTOR
      │
      ▼
PROGRAM / TOPIC MATCHER
      │
      ▼
FACET EXTRACTOR
      │
      ▼
LANE INTENT ESTIMATOR
      │
      ▼
QUERY PLAN
      │
      ▼
OPERATOR REVIEW / AUTO EXECUTE
```

Không cần mọi bước phải là LLM.

---

# 7. Stage 1 — Query normalization

Mục tiêu:

- Unicode normalization;
- trim whitespace;
- giữ cả raw/original;
- chuẩn hóa dấu câu cho parser;
- language detection nếu cần;
- không tự dịch mất bản gốc.

Lưu:

```text
original_query
normalized_query
```

Nếu tạo bản dịch English cho visual model:

```text
visual_query_translation
```

phải lưu riêng.

---

# 8. Stage 2 — Temporal intent detector

Detector tìm các cue:

```text
sau đó
sau cảnh
trước đó
trước khi
rồi
tiếp theo
cuối cùng
ngay sau
ngay trước
followed by
after
before
then
```

Output:

```text
NONE
ORDERED_SEQUENCE
BEFORE_AFTER
NEAR
SAME_EVENT
```

Nếu uncertain:

```text
TEMPORAL_SUGGESTED
```

và UI cho operator bật/tắt.

---

# 9. Stage 3 — Program / Topic matcher

Nguồn để match:

1. router lexicon;
2. taxonomy labels/aliases;
3. media metadata terms;
4. BGE-style semantic matching;
5. optional LLM suggestion.

Output phải ranked:

```json
[
  {"branch": "program.news", "score": 0.86, "reason": [...]},
  {"branch": "topic.traffic", "score": 0.71, "reason": [...]}
]
```

Không trả đúng một branch duy nhất.

---

# 10. Stage 4 — Facet extractor

Ba cấp thực hiện:

## Tier A — deterministic/rule

Ví dụ:

- số lượng;
- màu phổ biến;
- temporal cue;
- quoted text;
- obvious entity patterns.

Ưu điểm:

- nhanh;
- explainable;
- deterministic.

Nhược:

- coverage thấp.

## Tier B — semantic tagger

Dictionary + semantic matching vào controlled facet dictionary.

Ưu:

- nhất quán với index vocabulary;
- ít hallucination hơn free-generation.

## Tier C — LLM assisted

LLM trả structured decomposition.

Ví dụ:

```json
{
  "objects": ["person", "motorcycle", "barrier"],
  "attributes": ["green shirt"],
  "actions": ["riding", "passing"],
  "scenes": ["road"],
  "temporal": null
}
```

LLM output là **suggestion**, không source truth.

---

# 11. Vì sao không để LLM là parser duy nhất?

Rủi ro:

- cùng query có thể decomposition khác nhau;
- bỏ mất từ quan trọng;
- thêm semantic không được nói;
- khó benchmark regression;
- khó biết vì sao lane fail;
- latency/availability phụ thuộc model.

Chốt:

**LLM là một module gợi ý mạnh, không phải single point of failure.**

---

# 12. Query Plan cần explainable

UI phải hiển thị:

```text
Detected mode: SEQUENCE
Reason: found "sau đó"

Program candidates:
1. News
2. Community

Step A:
objects: woman, board
OCR intent: medium
visual intent: high

Step B:
objects: truck
visual intent: high

Constraint:
same video
A before B
max gap: 60 sec
```

Operator có thể sửa trước Search.

---

# 13. Search Mode 1 — SINGLE LANE

Mục tiêu:

- benchmark;
- debug;
- thi đấu khi operator biết lane phù hợp;
- không bị fusion che lỗi.

Modes:

```text
SigLIP2 only
BTC CLIP only
Qwen only
ASR only
OCR only
BTC Object only
Media-info only
```

Input vẫn có thể dùng original query hoặc facet-specific query.

---

# 14. Search Mode 2 — COMPARE

Chạy cùng query trên nhiều lane nhưng **không fusion**.

UI:

```text
Query: "..."

SIGLIP        BTC CLIP       QWEN          ASR
#1 ...        #1 ...         #1 ...        #1 ...
#2 ...        #2 ...         #2 ...        #2 ...
```

Mục tiêu:

- biết lane nào tìm ra đáp án;
- phát hiện coverage gap;
- xây benchmark;
- quyết định fusion sau này bằng dữ liệu.

Compare Mode phải ghi:

```text
query_id
lane
rank
video_id
time/frame
score
latency
```

Nếu có GT:

```text
correct_video_rank
first_correct_frame_rank
hit@K
```

---

# 15. Search Mode 3 — MANUAL HYBRID

Operator tự chọn lane:

```text
☑ SigLIP
☑ Qwen
☐ ASR
☑ OCR
☐ BTC CLIP
```

và có thể chọn sub-query khác nhau cho mỗi lane.

Ví dụ:

```text
Original:
"người đàn ông đứng cạnh biển có chữ UBND"

SigLIP query:
"man standing beside a sign"

OCR query:
"UBND"

Qwen facets:
person + sign + standing
```

Manual Hybrid là mode rất quan trọng trước Auto vì operator có thể tận dụng hiểu biết của mình mà không phụ thuộc brain hoàn hảo.

---

# 16. Search Mode 4 — AUTO

Brain tự:

1. parse;
2. gợi ý facets;
3. detect temporal;
4. chọn lanes;
5. chọn SAFE pruning;
6. chạy lanes;
7. fusion nếu được bật;
8. rescue nếu cần.

Nhưng UI vẫn phải hiển thị query plan.

Auto không được làm hệ thống thành black box.

---

# 17. Search Mode 5 — GLOBAL RESCUE

Bỏ qua taxonomy routing hoặc mở rộng scope rất rộng.

Dùng khi:

- không tìm thấy gì;
- operator nghi prune sai;
- query visual rõ nhưng topic khó đoán;
- benchmark false-negative.

Recommended rescue lanes:

```text
custom SigLIP global
BTC CLIP global
ASR global
OCR global nếu query có text intent
```

Qwen global cũng có thể dùng nhưng tùy index design.

---

# 18. Search Mode 6 — STRUCTURED FACET SEARCH

Không cần natural query.

UI:

```text
Objects     [tomato] [knife]
Attributes  [red]
Actions     [cutting]
Scene       [kitchen]
Text        []
```

Operator chọn:

```text
ALL strong facets
ANY facets
weighted
```

Nhưng backend không nên thực hiện raw strict AND mặc định.

---

# 19. Weighted support thay vì strict AND

Ví dụ:

```text
object motorcycle
attribute green shirt
action riding
scene road
```

Nếu Qwen bỏ sót `green shirt`, strict AND sẽ xóa đáp án.

Thay vào đó:

```text
motorcycle     strong support
riding         strong support
road           weak support
green shirt    optional/medium
```

Candidate video/frame score dựa trên số evidence families và strength.

---

# 20. Search Mode 7 — SEQUENCE

Sequence là mode độc lập, không chỉ là một option nhỏ của Auto.

Ví dụ:

```text
STEP 1: person entering kitchen
STEP 2: person putting food into pan
STEP 3: finished dish on plate
```

Constraint:

```text
same_video = true
strict_order = true
max_gap_1_2 = 60s
max_gap_2_3 = 60s
```

Mỗi step có thể dùng lane khác nhau.

Chi tiết ranking/matching nằm trong `04_TEMPORAL_MEDIA_INSPECTOR.md`.

---

# 21. BEFORE / AFTER quick mode

UI có thể đơn giản hơn Sequence full:

```text
BEFORE
[ woman standing before a board ]

AFTER
[ truck driving past ]

Max gap: [60] sec
Same video: ☑
```

Kết quả phải chia:

```text
BOTH MATCH
ONLY BEFORE
ONLY AFTER
```

Không bỏ partial match.

---

# 22. Tại sao phải trả partial match?

Trong bài toán “mò kim đáy bể”:

- step A có thể search rất tốt;
- step B có thể bị keyframe sampling miss;
- model visual có thể miss một scene;
- temporal gap có thể hơi vượt threshold.

Nếu chỉ trả chain hoàn chỉnh thì operator mất những anchor rất có giá trị.

Do đó:

```text
Tier A result: full chain
Tier B result: prefix/only-before
Tier C result: suffix/only-after
```

operator có thể mở video từ anchor để kiểm tra bằng mắt.

---

# 23. Query decomposition cho Sequence

Auto Sequence Brain phải giữ cả:

```text
original_sequence_query
```

và:

```text
steps[]
```

Ví dụ:

```json
{
  "original": "Sau cảnh A là cảnh B",
  "steps": [
    {
      "id": "S1",
      "text": "A",
      "facets": {...}
    },
    {
      "id": "S2",
      "text": "B",
      "facets": {...}
    }
  ],
  "constraints": {
    "same_video": true,
    "strict_order": true,
    "max_gap_ms": 60000
  }
}
```

Không rewrite original thành một caption duy nhất.

---

# 24. Lane intent classification

Brain nên gán mức ưu tiên:

```text
OFF
LOW
MEDIUM
HIGH
REQUIRED
```

Ví dụ query:

```text
"cảnh có chữ Đại học Cần Thơ"
```

```text
OCR           REQUIRED
SigLIP        MEDIUM
Qwen          LOW
ASR           LOW
BTC CLIP      LOW
```

Query:

```text
"người đàn ông đang khuấy nồi"
```

```text
Qwen          HIGH
SigLIP        HIGH
BTC CLIP      MEDIUM
BTC Object    MEDIUM
OCR           OFF
ASR           LOW
```

Query:

```text
"bản tin nói về lãi suất ngân hàng"
```

```text
ASR           REQUIRED/HIGH
Media-info    MEDIUM
OCR           MEDIUM
Visual        LOW
```

---

# 25. Lane selection không đồng nghĩa hard filter

Nếu brain đánh `OCR=OFF`, operator vẫn có thể bật.

Nếu brain đánh Topic Traffic, SAFE mode không được xóa tất cả non-Traffic video.

Brain chỉ lập plan.

Retrieval policy mới thực thi.

---

# 26. Pruning Mode — OFF

```text
scope = all 873 videos
```

Dùng cho:

- benchmark baseline;
- compare lane;
- query khó;
- kiểm tra taxonomy false-negative;
- global rescue.

OFF phải luôn tồn tại.

Không được xóa mode này sau khi Auto tốt lên.

---

# 27. Pruning Mode — SAFE

Đây nên là mặc định cho Auto.

SAFE tạo:

```text
priority pool
+
global escape pool
```

Ví dụ:

```text
873
│
├── taxonomy priority = 80 videos
│
└── global rescue = top 32–100 tùy lane/query
```

Sau search:

```text
final candidates = union(priority evidence, rescue evidence)
```

SAFE có thể giảm compute mà vẫn giữ đường cứu.

---

# 28. Pruning Mode — AGGRESSIVE

Chỉ sau khi evaluation chứng minh branch đủ an toàn.

Có thể:

```text
873 → exact branch candidate set
```

Nhưng phải có:

- routing score cao;
- margin đủ;
- branch reliability tốt;
- evidence từ nhiều family;
- GT recall gate PASS;
- branch không nằm trong ambiguous deny list.

Không bật global mặc định khi chưa benchmark.

---

# 29. Program pruning và Topic pruning khác nhau

Program thường ổn định hơn:

```text
Cooking
Exam prep
Cycling
News
Travel
```

Topic có thể thay đổi theo region trong video, đặc biệt news.

Do đó:

```text
Program → video-level prior/prune
Topic   → video-level hoặc region-level tùy branch
```

L21/L22 không nên gắn một topic duy nhất cho toàn video.

---

# 30. Object không phải taxonomy hard-prune mặc định

Ví dụ hơn 400 video cooking có thể chứa:

```text
bowl
pan
person
knife
vegetable
```

Nếu query `pan`, object này không giúp prune mạnh theo video.

Object postings có ích để:

- support candidate;
- frame-level filter;
- region/frame rank;
- evidence voting.

Không nên dùng generic object để loại 800 video chỉ bằng absence.

---

# 31. Evidence voting cho candidate video

Video candidate có thể nhận support:

```text
program match
media metadata match
ASR match
OCR match
Qwen facet match
BTC object match
SigLIP hit
BTC CLIP hit
```

Mỗi family độc lập giúp confidence mạnh hơn.

Ví dụ:

```text
video A:
Qwen motorcycle ✓
BTC Object motorcycle ✓
SigLIP top hit ✓
```

mạnh hơn:

```text
video B:
program traffic ✓
```

---

# 32. Candidate pool policy

Thay vì một `K` cố định cho mọi query, hỗ trợ profiles:

```text
FAST
BALANCED
DEEP
```

Ví dụ seed:

```text
FAST:
video pool 30–50
per lane K 50
final 20

BALANCED:
video pool 80–150
per lane K 100
final 50

DEEP:
pruning OFF/very broad
per lane K 200+
final 100
```

Các con số là seed benchmark, không production truth.

---

# 33. Natural Query phải được search trực tiếp ở visual lanes

Một lỗi thiết kế cần tránh:

```text
original query
↓
LLM objects only
↓
SigLIP search "person motorcycle barrier"
```

Có thể làm mất relation/narrative.

SigLIP/CLIP nên có ít nhất hai query variants:

```text
Q_original
Q_visual_rewrite
```

rồi compare/fuse rank ở trong lane nếu cần.

Không xóa original query.

---

# 34. Structured facets cũng có query variant riêng

Ví dụ:

```text
objects: tomato, knife
action: cutting
scene: kitchen
```

visual composer có thể tạo:

```text
"a person cutting a tomato with a knife in a kitchen"
```

Nhưng phải lưu:

```text
composer = deterministic_template_v1
```

hoặc:

```text
composer = llm_visual_rewrite_v1
```

để benchmark.

---

# 35. OCR query input

OCR UI nên hỗ trợ:

```text
Exact/fuzzy text:
[ Đại học Cần Thơ ]

Semantic meaning:
[ university name ]
```

Nếu user đặt text trong dấu ngoặc kép hoặc chọn `Exact text`, lexical/fuzzy lane được ưu tiên.

Nếu user chỉ mô tả “bảng nguyên liệu”, semantic OCR/Qwen/visual có thể hỗ trợ.

---

# 36. ASR query input

ASR mode nên có:

```text
Spoken content
[ ngân hàng nhà nước điều chỉnh lãi suất ]

Match:
○ lexical
○ semantic
● hybrid
```

Named entity/number queries thường cần lexical mạnh.

Narrative/topic queries thường hưởng lợi từ dense semantic.

---

# 37. Search within selected videos

Một feature rất hữu ích:

```text
Scope:
○ Entire corpus
○ Current video
○ Selected videos
○ Current result videos
```

Workflow:

1. search `motorcycle`;
2. chọn vài video;
3. search tiếp `barrier` chỉ trong các video đó;
4. search action `passing`;
5. xem timeline overlap.

Đây là cách operator “thu hẹp bằng tay” mà không cần brain hoàn hảo.

---

# 38. Incremental object search

Theo đúng nhu cầu nhóm:

```text
Object 1: motorcycle
↓
result videos
↓
Object 2: barrier
↓
within same selected videos
↓
Object 3: green shirt
```

UI phải có option:

```text
[Search globally]
[Refine current result set]
[Search same videos only]
```

Không tự hiểu mọi lần nhập thêm object là strict intersection.

---

# 39. Temporal refine từ một anchor result

Khi click một result frame:

```text
ANCHOR = L21_V001 @ 14.2s
```

operator có thể:

```text
Search BEFORE anchor [-60s, 0]
Search AFTER anchor  [0, +60s]
Search AROUND anchor [-30s, +30s]
```

với query mới.

Đây là một dạng sequence search cực nhanh trong thi đấu.

---

# 40. Query history

Mỗi query plan cần lưu:

```text
query_id
original_query
normalized_query
mode
facets user-entered
facets auto-suggested
branch suggestions
selected lanes
pruning mode
K
results
latency
operator actions
```

Lợi ích:

- quay lại query cũ;
- benchmark;
- reproducibility;
- failure analysis.

---

# 41. Search Session

Một session có thể chứa:

```text
queries[]
pinned videos[]
pinned frames[]
rejected videos[]
confirmed candidates[]
notes
```

Operator không nên mất trạng thái khi đổi mode.

---

# 42. Pinned evidence

Khi operator thấy một frame có khả năng đúng:

```text
PIN
```

Sau đó:

- giữ frame dù rerun query;
- dùng frame làm temporal anchor;
- compare với result khác;
- mở source video;
- candidate builder.

---

# 43. Positive/negative feedback

Có thể hỗ trợ:

```text
LIKE / relevant
DISLIKE / irrelevant
```

Phase đầu chỉ dùng cho local rerank/session, chưa học model online.

Ví dụ:

- relevant frame → boost nearby same-video frames;
- irrelevant video → session-level suppress;
- không modify global canonical data.

---

# 44. Query by image / result-as-query — Tier 2

Một result frame có thể dùng làm visual query để tìm cảnh tương tự.

Use cases:

- tìm cùng người/set/khung cảnh;
- tìm cảnh tiếp nối visual;
- tìm duplicate/repeat graphics.

Đây là Tier 2 vì cần UI và cross-index handling nhưng có giá trị cao.

---

# 45. Brain confidence phải tách loại

Không một field `confidence` chung.

Nên có:

```text
temporal_intent_confidence
program_router_score
topic_router_score
facet_extraction_confidence
lane_intent_confidence
```

Nếu LLM không cung cấp calibrated probability, score chỉ ghi đúng loại:

```text
score_type = heuristic
score_type = semantic_similarity
score_type = model_logit
```

---

# 46. Branch score không phải membership score

Phải phân biệt:

```text
Query → Branch score
```

và:

```text
Video → Branch membership confidence
```

Hard prune chỉ có thể cân nhắc khi cả hai đủ mạnh.

---

# 47. Explainable routing trace

Mỗi search cần trace:

```text
query
↓
program.news score 0.84
  reason: keyword "bản tin" + semantic match
↓
SAFE priority pool 60 videos
↓
lanes:
ASR HIGH
OCR MEDIUM
SigLIP LOW
↓
rescue enabled
```

Nếu GT miss, trace cho biết lỗi nằm ở đâu.

---

# 48. Auto Brain fallback

Nếu brain parse lỗi/timeout:

```text
fallback = original-query multi-lane search
```

Ví dụ:

```text
SigLIP original
BTC CLIP original
ASR original
OCR original if text-like
```

Không để Brain failure làm Search API failure.

---

# 49. Lane failure fallback

Nếu SigLIP unavailable:

- vẫn chạy Qwen/BTC CLIP/etc.

Nếu OCR unavailable:

- UI báo lane unavailable;
- không tạo fake result.

Search overall:

```text
OK
PARTIAL
ERROR
```

phù hợp unified orchestrator hiện có.

---

# 50. Compare Mode failure taxonomy

Per lane:

```text
NO_HIT
CORRECT_VIDEO_WRONG_FRAME
CORRECT_REGION_WRONG_FRAME
SEMANTIC_MISS
SAMPLING_MISS
MAPPING_ERROR
INDEX_ERROR
QUERY_ENCODING_ERROR
FILTERED_OUT
```

Không chỉ ghi “miss”.

---

# 51. Brain evaluation dataset

Cần một tập query annotated thủ công:

```text
query
expected temporal mode
expected useful lanes
expected objects
expected actions
expected topic hints
```

Không cần facet annotation tuyệt đối hoàn hảo.

Mục tiêu là regression test Brain.

---

# 52. Search mode evaluation

Mỗi query BTC nên chạy ít nhất:

```text
SigLIP only
BTC CLIP only
Qwen only
ASR only
OCR only
Manual/Auto hybrid
```

Nếu query không phù hợp lane (ví dụ OCR query không có text), vẫn ghi `NOT_APPLICABLE` thay vì xem miss là failure ngang nhau.

---

# 53. Ablation bắt buộc

Khi fusion được build:

```text
all lanes
minus SigLIP
minus BTC CLIP
minus Qwen
minus ASR
minus OCR
minus taxonomy pruning
minus rescue
```

Đo:

- Recall;
- first correct rank;
- latency;
- candidate count.

Nhờ đó mới biết nguồn nào thực sự có giá trị.

---

# 54. Query mode shortcuts

Competition UI nên keyboard-first.

Ví dụ proposal:

```text
Ctrl+Enter    Search
Alt+1         SigLIP
Alt+2         Qwen
Alt+3         ASR
Alt+4         OCR
Alt+5         BTC CLIP
Alt+C         Compare
Alt+S         Sequence
Alt+G         Global Rescue
```

Key bindings có thể đổi sau UX test.

---

# 55. Auto-Analyze vs Auto-Search

Tách hai nút:

```text
ANALYZE QUERY
```

chỉ tạo plan.

```text
SEARCH
```

thực thi plan.

Có option:

```text
Auto-run after analyze
```

cho operator muốn nhanh.

---

# 56. Query Template Library

Có thể lưu template:

```text
VISUAL OBJECT
OCR ENTITY
NEWS ASR
COOKING ACTION
BEFORE/AFTER
3-STEP SEQUENCE
```

Không phải AI feature nhưng tăng tốc thao tác.

---

# 57. Program selector

UI không nên ép chọn Program trước query.

Cho ba kiểu:

```text
Program = AUTO
Program = USER SELECTED
Program = ALL
```

Nếu user chắc chắn `Cooking`, có thể chọn.

Nếu không chắc, AUTO/ALL.

---

# 58. Topic selector

Tương tự Program nhưng multi-select:

```text
Traffic
Weather
Economy
Education
...
```

Topic nên mặc định soft support.

---

# 59. Hard filter explicit của operator

Nếu operator chủ động chọn:

```text
ONLY Cooking videos
```

thì hệ thống có thể hard-filter vì đây là user command, không phải model guess.

Trace phải ghi:

```text
filter_source = USER_EXPLICIT
```

---

# 60. Negative Program/Topic

Có thể hỗ trợ:

```text
Exclude Cooking
Exclude News
```

Đây cũng là explicit operator filter.

---

# 61. Query variant management

Một query có thể sinh:

```text
original
visual_en
visual_compact
asr_semantic
ocr_lexical
facet_caption
```

Tất cả phải có ID:

```text
Q123:original
Q123:visual_v1
Q123:ocr_exact
```

để debug.

---

# 62. Không dùng cùng một preprocessing cho mọi lane

Query Brain chỉ cung cấp semantic intent.

Mỗi lane adapter chịu trách nhiệm:

```text
SigLIP tokenizer/processor
CLIP tokenizer
BGE tokenizer
FTS normalization
OCR trigram normalization
```

Không centralize tokenization sai cách.

---

# 63. Result normalization không làm mất lane-specific score

Canonical result có:

```text
lane
raw_score
rank
```

Fusion dùng rank/normalized score riêng.

Không overwrite raw score.

---

# 64. Search response structure

```json
{
  "query_plan": {...},
  "scope": {...},
  "lane_results": {
    "siglip_custom": [...],
    "qwen": [...],
    "asr": [...]
  },
  "fused_results": [...],
  "rescue_results": [...],
  "trace": {...},
  "status": "OK"
}
```

Compare Mode có thể không có `fused_results`.

---

# 65. Search result grouping

UI cần ít nhất ba views:

```text
BY FRAME
BY VIDEO
BY TIMELINE
```

BY VIDEO giúp sequence/refine.

BY TIMELINE giúp xem multiple hits trong cùng video.

---

# 66. Video-level grouping score

Không đơn giản dùng max frame score duy nhất.

Có thể lưu:

```text
best_rank
best_frame_score
number_of_hits
diversity_of_evidence
number_of_lanes
```

Phase đầu dùng heuristic/rank aggregation, benchmark sau.

---

# 67. Diversity control

Nếu Top-50 đều đến cùng một shot/video, operator khó khám phá.

UI có option:

```text
Diversity:
○ off
○ per video max 5
○ per temporal cluster max 3
```

Không áp dụng mặc định cho tất cả benchmark vì có thể giảm frame recall.

---

# 68. De-duplication

Các frames rất gần nhau có thể coi thành một temporal cluster cho UI.

Nhưng raw results vẫn giữ đầy đủ để evaluation.

```text
presentation dedup != retrieval deletion
```

---

# 69. Auto rescue trigger

Tier 1 trigger đơn giản:

```text
if fused confidence weak
or candidate diversity low
or top lanes disagree strongly
→ run global rescue
```

Tuy nhiên “confidence weak” ban đầu nên heuristic, không giả calibrated.

---

# 70. Manual rescue luôn có nút

```text
SEARCH ENTIRE CORPUS
```

hoặc:

```text
RUN GLOBAL VISUAL RESCUE
```

Không bắt user sửa pruning mode thủ công nhiều bước.

---

# 71. Brain profile FAST/BALANCED/DEEP

### FAST

- minimal parser;
- few lanes;
- SAFE priority pool nhỏ;
- no expensive rerank.

### BALANCED

- full deterministic+semantic brain;
- 3–5 relevant lanes;
- SAFE pruning;
- RRF;
- conditional rescue.

### DEEP

- broad lanes;
- pruning OFF/very safe;
- sequence expansion;
- reranker if available;
- large K;
- rescue always/near-always.

---

# 72. Recommended default UX

Competition default:

```text
Mode      = AUTO
Pruning   = SAFE
Profile   = BALANCED
Fusion    = RRF if validated, otherwise show lane tabs + fused beta
Rescue    = conditional + manual button
```

Nhưng single-lane/compare luôn ở một click.

---

# 73. Tier 1 Query Brain implementation

Nên build trước:

1. Original query preservation.
2. Rule temporal detector.
3. Program/topic lexical + semantic matcher.
4. Structured facet editor.
5. Simple LLM-assisted decomposition interface (optional provider).
6. Lane intent rules.
7. OFF/SAFE pruning.
8. Single Lane.
9. Compare Mode.
10. Manual Hybrid.
11. 2–5 step Sequence input thủ công.
12. Query trace/session history.

---

# 74. Tier 2 Query Brain

Sau benchmark:

- automatic sequence decomposition;
- learned lane selection;
- query expansion/synonyms from failure logs;
- image-as-query;
- feedback-based session rerank;
- adaptive K per query;
- branch-specific routing thresholds;
- learned rescue trigger.

---

# 75. Tier 3 / Experimental

Chưa ưu tiên:

- LLM agent tự search nhiều vòng không kiểm soát;
- end-to-end learned router/fusion không explainable;
- online reinforcement learning từ operator clicks;
- autonomous query reformulation loop không giới hạn;
- hard pruning bằng single neural score.

Lý do: khó debug và chưa có evidence rằng cần thiết.

---

# 76. Acceptance Gate — Query Workspace

PASS nếu:

```text
original query không bao giờ mất
structured facets chỉnh được
user-pinned facet phân biệt auto facet
mode switch không mất query
scope switch hoạt động
pruning OFF luôn có
selected lanes hiện rõ
```

---

# 77. Acceptance Gate — Brain

Trên test query set:

```text
temporal intent detection benchmarked
program/topic candidates inspectable
facet decomposition inspectable
lane suggestions reproducible theo version
parser failure có fallback
no silent hard prune
```

Không đặt mục tiêu “100% facet đúng” trước khi search lane benchmark.

---

# 78. Acceptance Gate — Compare Mode

```text
same query chạy độc lập nhiều lane
raw rank/score preserved
latency per lane available
result mapping về video/time/frame đúng
failure status per lane rõ
```

---

# 79. Acceptance Gate — Manual Hybrid

```text
operator chọn lane bất kỳ
lane-specific query override được
fusion có thể bật/tắt
results vẫn xem riêng từng lane
```

---

# 80. Acceptance Gate — Sequence UI

```text
2–5 steps
same-video option
strict-order option
max-gap configurable
mixed lane per step
full/partial results separate
anchor opens correct video/timestamp
```

---

# 81. Acceptance Gate — Pruning safety

Bắt buộc đo:

```text
GT video survival rate
before/after pruning Recall
false-negative prune count
candidate count reduction
```

Không enable AGGRESSIVE production nếu chưa qua gate.

---

# 82. Failure taxonomy của Query Brain

```text
BRAIN_TEMPORAL_MISCLASSIFICATION
BRAIN_PROGRAM_MISROUTE
BRAIN_TOPIC_MISROUTE
BRAIN_OBJECT_MISS
BRAIN_ACTION_MISS
BRAIN_HALLUCINATED_FACET
BRAIN_WRONG_LANE_SELECTION
BRAIN_QUERY_REWRITE_LOSS
PRUNING_FALSE_NEGATIVE
SEQUENCE_DECOMPOSITION_ERROR
```

Phân biệt Brain failure với Search Lane failure.

---

# 83. Versioning

Mỗi query plan lưu:

```text
brain_version
temporal_detector_version
facet_dictionary_version
router_lexicon_version
routing_policy_version
llm_provider/model/prompt_version nếu dùng
```

Không benchmark một Brain thay đổi âm thầm.

---

# 84. Privacy / source integrity

Query Brain không được ghi ngược auto-classification vào canonical source data.

Ví dụ:

```text
brain đoán L21_V001 = traffic
```

không tự thêm membership canonical.

Canonical membership phải đi qua materialization/audit workflow riêng.

---

# 85. API boundaries đề xuất

```text
POST /query/analyze
POST /search/lane/{lane}
POST /search/compare
POST /search/hybrid
POST /search/sequence
POST /search/auto
POST /search/rescue
```

Có thể map vào unified `/api/v1/search` hiện có bằng `mode`, nhưng contract nội bộ vẫn nên tách service responsibilities.

---

# 86. Query Brain không giữ state trong model

Session state nằm backend/store:

```text
selected videos
pinned frames
history
manual facets
```

Không dựa vào LLM conversation memory để tái tạo search state.

---

# 87. Proposed end-to-end flow — query thường

```text
1. User paste BTC query
2. Brain analyze
3. UI hiện Program/Topic/Facets/Lanes
4. User sửa nếu cần
5. SAFE scope tạo priority pool
6. Relevant lanes chạy độc lập
7. Canonicalize results
8. Show lane tabs
9. Optional RRF fused tab
10. Conditional rescue
11. User click frame
12. Media Inspector mở source video đúng timestamp
```

---

# 88. Proposed end-to-end flow — object-first

```text
1. User chọn Structured
2. nhập motorcycle
3. Qwen/BTC Object/SigLIP chạy
4. group theo video
5. user chọn/refine current videos
6. nhập barrier
7. search same videos
8. nhập action passing
9. timeline intersection/proximity
10. inspect source video
```

---

# 89. Proposed end-to-end flow — sequence

```text
1. User paste query "A sau đó B"
2. Temporal detector = BEFORE_AFTER
3. Brain đề xuất A/B
4. User chỉnh
5. Step A search → hits
6. Step B search → hits
7. group by video
8. temporal matcher tìm A(t1) < B(t2)
9. rank full chains
10. show only-A and only-B separately
11. click anchor → source video
```

---

# 90. Proposed end-to-end flow — no result

```text
AUTO result weak
↓
show diagnostic:
- priority pool size
- lane hit counts
- top videos
↓
[RUN GLOBAL RESCUE]
↓
SigLIP global + BTC CLIP global + relevant text lane global
↓
merge candidate discoveries
↓
inspect
```

---

# 91. Quyết định chốt

1. **Natural query và structured facets cùng tồn tại.**
2. **Original BTC query luôn được giữ nguyên.**
3. **LLM là assistant, không phải authority.**
4. **Single Lane + Compare được build trước Auto/Fusion.**
5. **Manual Hybrid là production feature, không chỉ debug.**
6. **Sequence là first-class search mode.**
7. **Partial temporal matches phải được hiển thị.**
8. **OFF/SAFE/AGGRESSIVE pruning luôn tách rõ.**
9. **SAFE là default candidate cho Auto; AGGRESSIVE cần GT gate.**
10. **Object absence không phải hard-negative mặc định.**
11. **Operator có thể search within selected videos.**
12. **Brain/Router phải versioned + traceable.**
13. **Global Rescue không được bỏ.**
14. **Mọi mode đều trả canonical evidence về cùng video/time/frame mapping.**

---

# 92. Dependency sang các tài liệu khác

- Data identities, mapping, SQLite, index row map: `01_DATA_HUB_MAPPING.md`
- Implementation của SigLIP/CLIP/Qwen/ASR/OCR/Object/Media lanes: `03_SEARCH_LANES_TECH_STACK.md`
- Sequence ranking, exact frame, neighborhood preview, video seek: `04_TEMPORAL_MEDIA_INSPECTOR.md`
- Milestones, benchmark, gates, failure explorer: `05_IMPLEMENTATION_EVALUATION_ROADMAP.md`

---

# 93. Definition of Done cho Query Brain & Modes

Phần này được coi là đủ để bước sang production integration khi:

```text
[ ] Natural query hoạt động mà không mất query gốc
[ ] Structured facet editor hoạt động
[ ] User-pinned và auto-suggested facets tách biệt
[ ] Single lane modes hoạt động
[ ] Compare Mode hoạt động
[ ] Manual Hybrid hoạt động
[ ] Sequence manual 2–5 steps hoạt động
[ ] OFF/SAFE pruning hoạt động
[ ] Global Rescue hoạt động
[ ] Query trace đầy đủ
[ ] Brain failure có fallback
[ ] GT pruning safety benchmark tồn tại
[ ] Auto mode chỉ orchestration các component đã benchmark
```

Khi các checkbox trên PASS, Query Brain mới thực sự là **bộ điều phối có kiểm soát**, thay vì một LLM “đoán query rồi hy vọng search đúng”.
