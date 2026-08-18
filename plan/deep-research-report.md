# AIC 2026 — Kế hoạch kiến trúc tổng thể cho hệ thống truy xuất video đa phương thức

## Kết luận nghiên cứu và bộ tài liệu đã tạo

Sau khi ghép toàn bộ những gì hiện có — dữ liệu BTC, ASR, taxonomy, custom keyframes, Qwen, SigLIP2, OCR mới bạn vừa cung cấp và Data Contract V1.1 — mình **không đề xuất xây một search engine duy nhất ngay từ đầu**.

Kiến trúc nên được khóa theo nguyên tắc:

> **Mapping chung ngay từ đầu → từng nguồn tìm kiếm độc lập → benchmark riêng → fusion muộn → luôn giữ đường cứu hộ global.**

Hay ngắn hơn:

> **Independent evidence, shared identity, late fusion.**

Điều này giải quyết đúng bế tắc: Hà muốn SigLIP/OCR/ASR chạy riêng để biết từng nguồn thất bại ở đâu; Triết muốn có tầng chọn chủ đề/cắt tỉa; đồng thời cả hai đều muốn xử lý query chuỗi thời gian và có khả năng triệu hồi video/frame sau khi tìm được candidate. Hai ý tưởng này **không mâu thuẫn** nếu mapping được làm chung nhưng retrieval lanes được giữ độc lập.

Dữ liệu hiện có đủ để xây kiến trúc này. Corpus authority có 873 video và 107.540 ASR segments; taxonomy đã xác định Program-level khá rõ, L25 có subject routing sâu, L26 Cooking quá rộng và L21/L22 News cần region-level topics. fileciteturn0file3 Data Contract V1.1 hiện cũng đã khóa custom-keyframe space ở 116.767 keyframe, Qwen có 116.587 record thành công và 180 frame thiếu semantic được giữ explicit; Qwen↔custom frame nối bằng `(video_id, frame_idx)` chứ không bằng tên ảnh/keyframe ID đơn lẻ. fileciteturn3file0

Mình đã tạo một bộ **7 Markdown file**, chia theo đúng các vấn đề cần triển khai thay vì nhét mọi thứ vào một file khổng lồ:

[**Tải toàn bộ kế hoạch — AIC2026_RETRIEVAL_ARCHITECTURE_PLAN.zip**](sandbox:/mnt/data/AIC2026_RETRIEVAL_ARCHITECTURE_PLAN.zip)

| Tài liệu                                                                                                                              | Nội dung                                                                                                            |
| --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| [README.md](sandbox:/mnt/data/AIC2026_RETRIEVAL_ARCHITECTURE_PLAN/README.md)                                                             | Mục lục và các quyết định kiến trúc quan trọng                                                             |
| [00_MASTER_ARCHITECTURE.md](sandbox:/mnt/data/AIC2026_RETRIEVAL_ARCHITECTURE_PLAN/00_MASTER_ARCHITECTURE.md)                             | **Bản chính:** toàn bộ kiến trúc, dữ liệu, query modes, pruning, technology tiers, quyết định chốt |
| [01_DATA_HUB_MAPPING.md](sandbox:/mnt/data/AIC2026_RETRIEVAL_ARCHITECTURE_PLAN/01_DATA_HUB_MAPPING.md)                                   | Trung tâm dữ liệu, SQLite schema, mapping BTC/custom/Qwen/OCR/ASR                                                 |
| [02_QUERY_BRAIN_SEARCH_MODES.md](sandbox:/mnt/data/AIC2026_RETRIEVAL_ARCHITECTURE_PLAN/02_QUERY_BRAIN_SEARCH_MODES.md)                   | Free Query, Structured, Hybrid, Auto, Compare, pruning, rescue                                                       |
| [03_SEARCH_LANES_TECH_STACK.md](sandbox:/mnt/data/AIC2026_RETRIEVAL_ARCHITECTURE_PLAN/03_SEARCH_LANES_TECH_STACK.md)                     | SigLIP2, BTC CLIP, Qwen, ASR, OCR, BTC Objects, Media-info; Tier 1/Tier 2                                            |
| [04_TEMPORAL_MEDIA_INSPECTOR.md](sandbox:/mnt/data/AIC2026_RETRIEVAL_ARCHITECTURE_PLAN/04_TEMPORAL_MEDIA_INSPECTOR.md)                   | Chuỗi trước/sau, partial matches, nearest frame, preview clip, exact frame                                        |
| [05_IMPLEMENTATION_EVALUATION_ROADMAP.md](sandbox:/mnt/data/AIC2026_RETRIEVAL_ARCHITECTURE_PLAN/05_IMPLEMENTATION_EVALUATION_ROADMAP.md) | Milestones, benchmark, acceptance gates, failure taxonomy                                                            |

## Nguồn dữ liệu nào được tận dụng và OCR mới thay đổi điều gì

Với file OCR mới, hệ thống hiện không chỉ có Visual + ASR + Qwen mà thực sự có gần đủ các “giác quan” cần thiết cho retrieval.

### Bức tranh dữ liệu đầy đủ

```text
                        873 SOURCE VIDEOS
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
       SPEECH                VISUAL              KNOWLEDGE
          │                    │                    │
         ASR         ┌─────────┴─────────┐        Taxonomy
                     │                   │
                  CUSTOM               BTC
                     │                   │
              116,767 KF            ~178k KF
                     │                   │
        ┌────────────┼──────────┐        ├── BTC CLIP
        ▼            ▼          ▼        ├── BTC Objects
      Qwen        SigLIP2      OCR?      └── Map Keyframes
```

BTC cung cấp một bộ visual độc lập rất đáng giữ: khoảng 178.195 keyframes, 873 map-keyframe CSV, media-info cho 873 video, object detection trên BTC keyframes và OpenAI CLIP ViT-B/32 512D features. Map-keyframes còn cung cấp `n`, `pts_time`, `fps`, `frame_idx`, nên BTC keyframe space có thể được định vị chính xác về video/time/frame. fileciteturn0file1

Custom pipeline lại có 116.767 keyframes riêng và Qwen đã phân tích gần như toàn bộ chúng thành `objects`, `attributes`, `spatial_relations`, `counts`, `scene`, `visible_actions`, `caption`. Đây là một frame space độc lập với BTC và phải được giữ độc lập. fileciteturn3file0

OCR bạn vừa cung cấp có giá trị rất lớn vì nó nhắm vào **chữ nhìn thấy trong hình**, như lower-third, headline, bảng tên người, ticker, biển hiệu, tên địa phương, bảng nguyên liệu, logo và text overlay. Audit cũng cho biết dữ liệu được chia thành các cặp `embeddings_shard_XXX.npy` ↔ `metadata_shard_XXX.json`, với OCR text và metadata liên quan tới video/frame/bbox/confidence. fileciteturn0file0

Tuy nhiên, đây là phát hiện quan trọng nhất của mình về OCR:

> **File audit OCR hiện đủ để kết luận “dữ liệu này rất đáng tích hợp”, nhưng chưa đủ để khóa dense OCR mapping.**

Lý do là report đang mô tả một số field dưới dạng:

```text
keyframe_id / frame_idx
score / confidence
embedding dimension = ví dụ 512 / 768 / 1024
```

chứ chưa chứng minh trực tiếp rằng schema thật của **mọi shard** là field nào, embedding thực tế bao nhiêu chiều, model/checkpoint nào tạo các vector, preprocessing gì được dùng và OCR đang tham chiếu tới **BTC keyframes, custom keyframes hay physical source frame**. fileciteturn0file0

Điều này rất quan trọng vì dense retrieval chỉ có nghĩa khi query được encode bằng đúng model/vector space đã tạo corpus embedding. Đây cũng là lý do SigLIP2 query phải dùng đúng SigLIP2 text encoder cùng preprocessing; tài liệu chính thức của Transformers cho SigLIP2 sử dụng lowercase, truncation và fixed `max_length=64`/`padding="max_length"` trong text preprocessing của model, và việc thay preprocessing có thể làm retrieval lệch. citeturn5search2

Do đó, OCR cần một direct audit nhỏ trước khi bật dense lane:

```text
OCR DIRECT AUDIT
│
├── Có bao nhiêu shard?
├── Tổng bao nhiêu record?
├── Exact JSON schema?
├── Exact NPY shape/dtype?
├── Dimension?
├── Embedding model/checkpoint?
├── Query preprocessing?
├── Vector normalized hay chưa?
├── Row i NPY == metadata i?
├── keyframe_id thuộc frame space nào?
└── Có map được → video/time/frame không?
```

Nhưng **OCR lexical search không cần chờ toàn bộ việc này**. Khi text + video identity đã được xác minh, có thể chuẩn bị FTS/BM25 trước.

SQLite FTS5 chính thức hỗ trợ BM25 và `trigram` tokenizer; trigram hỗ trợ substring matching và có tùy chọn xử lý diacritics, nên rất phù hợp để làm một lane OCR fuzzy song song với word search thay vì chỉ exact match. citeturn0search0

Điều mình **không đồng ý hoàn toàn** với audit OCR hiện tại là xóa vĩnh viễn mọi record có confidence `<0.6`. Nên giữ raw OCR đầy đủ và chỉ giảm trọng số record confidence thấp ở runtime. Một dòng chữ quan trọng có thể confidence thấp vì font, overlay hoặc nền phức tạp; xóa khỏi canonical data sẽ mất khả năng cứu lại sau này.

## Kiến trúc hệ thống mình đề xuất chốt

### Trung tâm dữ liệu không phải là một giant JSON

Trung tâm phải đóng vai trò **bản đồ**, không phải “nhồi tất cả dữ liệu vào một vector”.

```text
                         MAPPING.SQLITE
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
          VIDEOS          KEYFRAMES            TEXT
            │                 │                 │
       873 videos       ┌─────┴──────┐     ASR / OCR
                        │            │
                     CUSTOM         BTC
                        │            │
                     Qwen         Objects
                    SigLIP2        CLIP
```

Một result cuối cùng, dù được tìm bởi OCR hay CLIP, phải quy về được một format chung:

```json
{
  "lane": "siglip_custom",
  "video_id": "L21_V001",
  "frame_space": "CUSTOM",
  "frame_idx": 426,
  "timestamp_ms": 14200,
  "entity_id": "CUSTOM:L21_V001:000002",
  "rank": 4
}
```

ASR có thể không có keyframe:

```json
{
  "lane": "asr",
  "video_id": "L21_V001",
  "start_ms": 13100,
  "end_ms": 16800,
  "rank": 2
}
```

Nhưng vì đều có:

```text
video_id
+
time
```

nên chúng vẫn ghép được ở tầng sau.

### BTC và Custom không merge ID

Đây phải là invariant của database:

```text
BTC:L21_V001:002
≠
CUSTOM:L21_V001:000002
```

kể cả hai frame có timestamp gần nhau.

Hai hệ chỉ được liên hệ bằng:

```text
same video
+
nearest timestamp
+
physical frame index nếu có
```

Điều này phù hợp với Data Contract V1.1 hiện tại, vốn đã yêu cầu tách tuyệt đối BTC/custom keyframe spaces. fileciteturn3file0

### Mỗi vector index có “hộ chiếu”

Ví dụ:

```json
{
  "artifact": "siglip_custom_v1",
  "model_id": "google/siglip2-base-patch16-224",
  "model_revision": "...",
  "dimension": "...",
  "normalized": true,
  "distance": "inner_product",
  "preprocessing": {
    "max_length": 64,
    "padding": "max_length",
    "truncation": true
  }
}
```

FAISS là lựa chọn Tier 1 hợp lý cho các dense index độc lập này: dự án chính thức tập trung vào similarity search/clustering trên dense vectors và vẫn đang được duy trì trong năm 2026. citeturn0search4

Nếu query encoder không khớp manifest:

```text
FAIL
```

chứ không:

```text
search đại rồi cho Top-K tào lao
```

### Query Brain nằm trên search engine, không thay search engine

Kiến trúc query:

```text
                              RAW QUERY
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
          WHOLE QUERY SEARCH                  ANALYZE
                 │                                 │
                 │                    object / action / scene
                 │                    OCR / ASR / topic / sequence
                 │                                 │
                 └────────────────┬────────────────┘
                                  ▼
                             SEARCH PLAN
                                  │
                    OFF / SAFE / STRICT prune
                                  │
     ┌────────────┬────────────┬──┴─────┬─────────┬─────────────┐
     ▼            ▼            ▼        ▼         ▼             ▼
  SigLIP       BTC CLIP      Qwen      ASR       OCR       BTC Objects
     │            │            │        │         │             │
     └────────────┴────────────┴────────┴─────────┴─────────────┘
                                  │
                                  ▼
                       CANONICAL CANDIDATES
                                  │
                       temporal join if needed
                                  │
                                  ▼
                              RRF/FUSION
                                  │
                             GLOBAL RESCUE
                                  │
                                  ▼
                               TOP-K
```

BGE-M3 là lựa chọn Tier 1 tốt cho **text semantic retrieval**, chứ không phải thay encoder visual. Paper/model của BGE-M3 thiết kế một model multilingual có dense, sparse và multi-vector retrieval modes và hỗ trợ hơn 100 ngôn ngữ; vì vậy nó phù hợp với ASR/OCR/Qwen caption/Media text tiếng Việt–Anh. citeturn0academia49turn0search5

### LLM và manual input không cần chọn một bỏ một

Câu hỏi trong đoạn chat:

> “LLM tự phân tích hay tạo ô object để tự nhập?”

Kiến trúc chốt là **Hybrid Assisted Query**.

```text
Query:
[ người mặc áo xanh đi xe máy qua barie            ]

             [Analyze]

Object:
[ person × ] [ motorcycle × ] [ barrier × ] [+]

Attribute:
[ green shirt × ] [+]

Action:
[ riding × ] [ passing × ] [+]

Scene:
[ traffic/checkpoint × ] [+]

Program:
[ Auto ▼ ]

Pruning:
[ SAFE ▼ ]

Lanes:
☑ SigLIP
☑ Qwen
☑ BTC CLIP
☐ ASR
☐ OCR
```

LLM/rules chỉ **đề xuất chip**.

Người dùng sửa được.

Quan trọng nhất:

```text
RAW QUERY vẫn được search
```

song song với:

```text
person
motorcycle
barrier
green shirt
passing
```

Điều này giải quyết case nếu decomposition làm mất nghĩa câu gốc, whole-query SigLIP/BGE/Qwen-caption search vẫn giữ một đường retrieval khác.

Nếu muốn dùng một LLM local mới hơn làm query planner về sau, Qwen3.5 hiện là một family multimodal/instruction hiện hành trong năm 2026 và có các checkpoint nhỏ hơn để thử nghiệm; nhưng trong kiến trúc này nó chỉ sinh **validated Query Plan**, không quyết định truth và không được tự xóa video khỏi corpus. citeturn4search0turn4search10

## Các động cơ tìm kiếm và lựa chọn công nghệ

### Technology Tier 1 — nên triển khai trước

| Nhiệm vụ           | Công nghệ chốt                      | Vai trò                                   |
| -------------------- | -------------------------------------- | ------------------------------------------ |
| Central mapping      | **SQLite**                       | authority runtime về ID/time/path/mapping |
| Exact text           | **SQLite FTS5/BM25**             | ASR/OCR/Qwen/Media                         |
| OCR typo             | **FTS5 trigram**                 | lỗi dấu/ký tự/substrings               |
| Semantic text        | **BGE-M3 dense**                 | ASR/OCR/Qwen caption/media                 |
| Custom visual        | **existing SigLIP2 + FAISS**     | primary visual                             |
| BTC visual           | **BTC CLIP ViT-B/32 + FAISS**    | independent/rescue                         |
| Qwen                 | **facet postings + FTS/BGE**     | object/action/scene/relation               |
| BTC Objects          | **inverted postings**            | object support + bbox                      |
| Video pruning        | **873-bit bitset**               | Program/Topic filtering                    |
| Fusion               | **RRF**                          | late fusion theo rank                      |
| Backend              | **Python/FastAPI**               | orchestration/search/media                 |
| Exact media          | **FFmpeg/ffprobe**               | seek/exact-frame/preview                   |
| Full-video transport | **HTTP Range**                   | đọc từng phần video                    |
| Validation           | **schema + checksum + manifest** | fail-closed                                |

SigLIP2 phải giữ đúng text encoder/preprocessing tương ứng với image embeddings hiện có; không thể lấy BGE-M3 hay CLIP query vector để so vào SigLIP space. citeturn5search2

BTC CLIP cũng tương tự: audit xác định BTC features là OpenAI CLIP ViT-B/32 512D, vì vậy lane BTC phải dùng text encoder tương ứng; đồng thời BTC sampling độc lập với custom sampling khiến nó đặc biệt có giá trị làm Global Rescue thay vì bị vứt bỏ. fileciteturn0file1

Qwen không cần chạy lại khi query. Dữ liệu semantic đã tồn tại ở frame level; search nên khai thác postings và text indexes. Raw Qwen không có confidence per object/action/scene, nên normalization chỉ được thêm provenance/normalization score nếu thật sự tính được, không được bịa “Qwen confidence = 0.96”. fileciteturn3file0

RRF là lựa chọn fusion Tier 1 vì:

```text
SigLIP cosine
BTC CLIP cosine
BGE cosine
BM25
OCR confidence
Object confidence
```

không nằm trên cùng một scale. Qdrant hiện cũng hỗ trợ RRF trong hybrid/multi-stage Query API, nhưng điều đó không có nghĩa phải đưa Qdrant vào dependency đầu tiên. citeturn1search8

### Technology Tier 2 — chỉ promotion sau benchmark

**BGE-M3 sparse** đáng benchmark cạnh BM25 để tăng learned lexical retrieval; BGE-M3 multi-vector có thể thử khi cần matching chi tiết hơn. citeturn0academia49turn0search5

**`bge-reranker-v2-m3`** là lựa chọn reranker multilingual hợp lý cho Top-N text/semantic candidates; nó phải đứng **sau** first-stage retrieval, không chạy trên toàn corpus/frame space. citeturn2search0turn2search16

**ColBERTv2/late interaction** có lợi thế token-level matching và compression tốt hơn các late-interaction generation trước, nhưng phải trả giá bằng index/storage/orchestration phức tạp hơn; vì vậy chỉ nên benchmark Tier 2. citeturn1academia48

**Qdrant local** đáng cân nhắc nếu sau này việc duy trì nhiều FAISS/FTS/named vector indexes trở nên khó. Query API hiện hỗ trợ multi-stage `prefetch`, dense+sparse, RRF/DBSF và multivector, nên nó là một hướng hợp nhất tốt nhưng chưa cần thiết để chứng minh Idea3 V1. citeturn1search8turn2search14

**Temporal grounding model/Video-LLM** cũng chỉ nên nhận **candidate clips/regions** sau retrieval. Nghiên cứu video grounding dài năm 2026 cho thấy search/candidate discovery là nút thắt lớn; paper ExtremeWhenBench báo cáo retrieve-then-ground vượt rõ monolithic Video-LLM trong benchmark của họ. citeturn3academia50 Các benchmark 2026 về conditional multi-event grounding cũng củng cố nhu cầu biểu diễn nhiều event + điều kiện thời gian thay vì xem query như một caption phẳng. citeturn3search5

### Technology Tier 3 — nghiên cứu sau

Tier này mới gồm re-encode toàn bộ custom frames bằng checkpoint SigLIP2 lớn hơn, learned fusion/learning-to-rank, fine-tuning, agentic iterative search hay Video-LLM verifier. Chỉ nên bắt đầu khi logs cho biết failure cụ thể mà Tier 1/Tier 2 không giải quyết được; SigLIP2 bản thân có nhiều kích thước encoder và được thiết kế cho multilingual image-text retrieval, nhưng thay checkpoint đồng nghĩa phải re-encode corpus trong cùng space. citeturn0academia48

**Chốt stack ban đầu:**

```text
SQLite Central Mapping
        +
FTS5 / BM25 / Trigram
        +
BGE-M3 Text Retrieval
        +
FAISS SigLIP2 Custom
        +
FAISS BTC CLIP
        +
Qwen Facet/Text Search
        +
BTC Object Postings
        +
SAFE Program/Topic Pruning
        +
Temporal Sequence Join
        +
RRF Late Fusion
        +
Global Rescue
        +
FFmpeg Media Inspector
```

## Chuỗi thời gian, frame và các tính năng ứng chiến

Mình **đề xuất làm Sequence Mode chính thức**, không bỏ nó.

Đây không phải feature quá “viển vông”; nó có thể được implement bằng search + join thời gian, chưa cần Video-LLM.

Ví dụ:

```text
QUERY:
"sau cảnh A là cảnh B rồi tới cảnh C"

         ↓ split manually / assisted

STEP A
[ person entering kitchen ]
SigLIP + Qwen

       ↓ 0–60s

STEP B
[ person putting food into pan ]
Qwen + SigLIP

       ↓ 0–60s

STEP C
[ finished dish on plate ]
SigLIP + Qwen
```

Mỗi step chạy độc lập:

```text
A → Top-K
B → Top-K
C → Top-K
```

Sau đó:

```text
GROUP BY video_id
ORDER BY timestamp
```

và tìm:

```text
tA < tB < tC
```

Đối với 3–5 step, dùng dynamic programming/beam search trên hit list đã sắp timestamp; không cần brute-force mọi combination.

Điểm rất đáng giữ từ cuộc thảo luận của hai bạn là:

> **Không chỉ in full match.**

UI nên có:

```text
FULL
A→B ONLY
B→C ONLY
SINGLE A
SINGLE B
SINGLE C
```

Nếu search không tìm được cả trước lẫn sau, “chỉ match trước” hoặc “chỉ match sau” vẫn có thể dẫn operator tới đúng video.

Khoảng `60s` mà Hà đưa ra hợp lý như một **preset thử nghiệm**, không nên hard-code thành chân lý:

```text
Gap:
[10s] [30s] [60s] [120s] [Custom]
```

Soft mode giảm điểm khi hai cảnh cách quá xa; Strict mode mới loại cứng.

Sequence còn có thể cross-modal:

```text
A = OCR "Đại học Cần Thơ"
B = visual motorcycle entering gate
```

hay:

```text
A = ASR "ngân hàng nhà nước"
B = visual chart
C = OCR "lãi suất"
```

Đây là lợi ích trực tiếp của việc mọi nguồn cùng quy về `video_id + timestamp`.

### Không cần “trích sẵn mọi frame +3s/+10s”

Bạn bè bạn đã chạm đúng một điểm: custom keyframe `401` và `402` không có nghĩa là cách nhau đúng một lượng thời gian cố định.

Khi người dùng bấm:

```text
+3s
```

tool nên:

```text
current = 14.20s
target  = 17.20s

↓
find nearest existing keyframe
```

và hiển thị:

```text
nearest KF = 17.34s
Δ = +3.14s
```

Nếu cần **đúng frame tại 17.20s**, lúc đó backend mới decode từ source video.

FFmpeg hỗ trợ seek với `-ss`; tài liệu chính thức giải thích seek có thể bắt đầu từ seek point gần trước mục tiêu và accurate seeking sẽ decode/discard phần trung gian khi cần. Vì vậy exact frame nên thuộc backend/media service, không dựa vào browser player để suy frame. citeturn6search0

### Filmstrip trước, video sau

Thay vì click Top-K rồi bắt full video nặng load:

```text
-10s | -3s | -1s | TARGET | +1s | +3s | +10s
```

hiển thị nearest keyframes ngay.

Sau đó mới:

```text
[Preview ±10s]
```

backend tạo/cache một clip nhỏ quanh target.

Cuối cùng:

```text
[Open Source Video]
```

mới stream source MP4. HTTP Range Requests cho phép client yêu cầu một byte range thay vì phải nhận toàn bộ representation, phù hợp với media-serving kiểu này. citeturn6search4

Controls nên phân biệt rõ:

```text
TIME:
-10s -3s -1s  Play  +1s +3s +10s

PHYSICAL FRAME:
-10f -3f -1f        +1f +3f +10f

KEYFRAME:
Prev KF | Next KF
```

Đừng gọi `+3 keyframes` là `+3 frames`.

## Roadmap thực hiện và điểm phải khóa trước khi bắt đầu coding lớn

Thứ tự mình đề xuất **khác với việc nhảy thẳng vào Auto Idea3**:

```text
SOURCE REGISTRY
      ↓
OCR DIRECT AUDIT
      ↓
UNIFIED MAPPING
      ↓
SINGLE SEARCH LANES
      ↓
COMPARE MODE
      ↓
STRUCTURED/HYBRID QUERY
      ↓
SEQUENCE ENGINE
      ↓
SAFE PRUNING
      ↓
MANUAL HYBRID + RRF
      ↓
QUERY BRAIN / LLM ASSIST
      ↓
GLOBAL RESCUE
      ↓
TIER-2 RERANK / TEMPORAL GROUNDING
```

### Việc đầu tiên còn thiếu là audit OCR trực tiếp

Không phải chạy OCR lại.

Chỉ cần đọc các shard thật và trả lời:

```text
Embedding model là gì?
Dimension thật bao nhiêu?
Metadata field thật là gì?
OCR keyframe là BTC hay Custom?
Có timestamp/frame_idx không?
Row NPY và metadata có match 1:1 không?
```

Sau đó mới đưa OCR vào Central Mapping chính thức. Audit hiện tại chứng minh dataset đáng dùng nhưng chưa khóa các identity này. fileciteturn0file0

### Sau đó build Mapping trước Search

Acceptance gate:

```text
873/873 videos                    PASS

CUSTOM
116,767 keyframes                 PASS
116,587 Qwen mapped               PASS
180 Qwen missing explicit         PASS

BTC
keyframe ↔ map ↔ CLIP             PASS
keyframe ↔ objects                PASS

ASR
segment ↔ video/time              PASS

OCR
vector ↔ metadata                 PASS
OCR frame space identified        PASS

unknown video_id                  0
orphan keyframe                   0
encoder/index mismatch            0
```

Data Contract V1.1 đã đặt đúng triết lý raw immutable → canonical machine data → runtime indexes, nên không cần phá đi viết lại từ đầu. fileciteturn3file0

### Sau Mapping, tuyệt đối làm single-lane trước

Cùng một tập query BTC/GT:

| Query |    SigLIP | BTC CLIP | Qwen |  ASR |  OCR |
| ----- | --------: | -------: | ---: | ---: | ---: |
| Q1    | correct#3 |      #17 |   #1 | miss | miss |
| Q2    |      miss |       #5 |  #20 |   #1 |   #7 |
| …    |        … |       … |   … |   … |   … |

Đo:

```text
Video Recall@K
Frame/Time Recall@K
First Correct Rank
MRR nếu GT phù hợp
Latency
Unique correct results contributed by lane
```

Sau đó mới biết:

> SigLIP fail vì query? sampling? encoder?
> Qwen fail vì semantic?
> OCR fail vì typo?
> ASR fail vì cảnh không nói?
> BTC cứu được bao nhiêu case custom bỏ sót?

Đây chính là cách biến cuộc tranh luận hiện tại thành **thực nghiệm có số liệu**.

### Cuối cùng mới bật fusion và Auto mode

Ablation:

```text
SigLIP only

BTC CLIP only

Qwen only

ASR only

OCR only

SigLIP + Qwen

SigLIP + BTC

ASR BM25 + BGE

OCR BM25 + trigram

All RRF

All RRF + SAFE pruning

All RRF + SAFE pruning + Rescue

All + reranker
```

Cross-encoder reranker như `bge-reranker-v2-m3` chỉ nên được promotion khi Top-N reranking thật sự nâng first-correct-rank/Recall đủ rõ để đáng với độ phức tạp bổ sung. citeturn2search0turn2search16

Mục tiêu cuối cùng không phải “có nhiều AI nhất”, mà là:

```text
QUERY
 ↓
đúng scope
 ↓
GT video không bị prune
 ↓
đúng vùng thời gian
 ↓
đúng frame lọt Top-K
 ↓
operator xác minh nhanh
```

Và nếu sai, hệ thống phải trả lời được **sai ở tầng nào**.

Bộ Markdown phía trên đã được viết theo đúng triết lý đó: `00_MASTER_ARCHITECTURE.md` là bản tổng thể; năm file còn lại tách riêng Data Hub, Query Brain, Search Lanes, Temporal/Media và Implementation/Evaluation để hai bạn có thể phát triển từng phần mà không lại rơi vào tình trạng “mỗi người đang nói về một tầng khác nhau”.
