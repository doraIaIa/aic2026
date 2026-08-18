# AIC 2026 — Retrieval Architecture Plan

> **Trạng thái tài liệu:** Architecture planning / design freeze candidate  
> **Ngày:** 2026-08-18  
> **Phạm vi:** Kiến trúc dữ liệu, search modes, query brain, independent retrieval lanes, temporal retrieval, pruning, fusion, media inspection, benchmark và roadmap cho hệ thống AIC 2026.  
> **Nguyên tắc ưu tiên:** **Correctness → Recall safety → Explainability → Operator control → Speed → Architectural elegance.**

---

## 1. Mục tiêu của bộ tài liệu

Bộ tài liệu này không mô tả một “model duy nhất” hay một “search API duy nhất”. Mục tiêu là thiết kế một **workstation tìm kiếm video đa chế độ**, trong đó:

1. Mọi nguồn dữ liệu được **định danh và liên kết chung**.
2. Từng phương pháp tìm kiếm được **giữ độc lập** để benchmark, debug và sử dụng riêng.
3. Người vận hành có thể dùng **query tự nhiên**, **query có cấu trúc**, hoặc **kết hợp cả hai**.
4. Hệ thống hỗ trợ các query dạng **chuỗi thời gian** như “cảnh A, sau đó cảnh B”.
5. Taxonomy chỉ là một lớp **định tuyến/cắt tỉa có kiểm soát**, không phải nguồn chân lý tuyệt đối.
6. Fusion chỉ diễn ra **sau khi** từng lane đã trả kết quả theo một contract chung.
7. **Video nguồn** là authority cuối cùng để xác minh frame.

Kiến trúc được chốt theo khẩu quyết:

> **Independent evidence, shared identity, late fusion.**  
> Nguồn bằng chứng độc lập → cùng dùng một hệ định danh → hợp nhất muộn.

Và:

> **Prune late enough to stay safe, early enough to stay fast.**  
> Cắt đủ muộn để không làm mất đáp án, nhưng đủ sớm để giảm không gian tìm kiếm.

---

## 2. Tình trạng dữ liệu đã audit

### 2.1 Corpus/video

- **873 video** là corpus canonical.
- `video_catalog_v1.jsonl` và `video_ordinals_v1.json` đã có contract cho 873 video.
- Video gốc là nguồn authority để xác minh exact frame.

### 2.2 Custom keyframes + Qwen

Audit Qwen hiện xác nhận:

- **116,767 custom keyframes** trong metadata authority `df_keyframes.pkl`.
- **116,587 Qwen records thành công**.
- Coverage Qwen: **99.8458%**.
- Còn **180 custom keyframes** chưa có Qwen semantic record.
- Qwen phủ **873/873 video**.
- Toàn bộ Qwen success records join chính xác vào custom keyframe metadata bằng `(video_id, frame_idx)`.
- `pts_time` khớp tuyệt đối trong audit.

Qwen raw hiện có:

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

Qwen **không** cung cấp calibrated confidence cho các field trên. Không được tự bịa score.

### 2.3 BTC-provided data

Audit BTC xác định các nguồn chính thức ngoài video:

- BTC keyframes: khoảng **178,195 ảnh** / 873 video.
- Map-keyframes: **873 CSV**, ánh xạ `n ↔ pts_time ↔ fps ↔ frame_idx`.
- Media-info: **873 JSON** với title, description, keywords, author, publish date, URL...
- Object detections: khoảng **178,195 JSON**, có class, confidence, bbox.
- CLIP visual features: **873 `.npy`**, OpenAI CLIP ViT-B/32, 512 chiều, mỗi row tương ứng một BTC keyframe.

**Quyết định:** Không bỏ các nguồn BTC. Chúng tạo một frame space và evidence space độc lập, đặc biệt hữu ích cho global visual rescue và object evidence.

### 2.4 OCR custom/friend dataset

Audit OCR cho thấy dữ liệu OCR được lưu theo shard:

```text
embeddings_shard_XXX.npy
metadata_shard_XXX.json
```

Metadata có các trường dạng:

```text
text
video_id
keyframe_id hoặc frame_idx
bbox
score/confidence
vector_idx
```

OCR hữu ích cho:

- headline/news banner;
- lower thirds/tên người;
- ticker;
- biển hiệu;
- tên trường/địa điểm;
- ingredient graphics;
- logo/text overlay.

Chất lượng OCR tiếng Việt có nhiễu/mất dấu/sai ký tự. Vì vậy lane OCR phải hỗ trợ **lexical + fuzzy/n-gram + dense semantic**, không phụ thuộc exact string duy nhất.

### 2.5 ASR

- Whisper ASR logic union: **873/873 video**.
- **107,540 segments**.
- 859 video có ≥1 segment.
- 14 zero-ASR video vẫn phải tồn tại trong corpus; zero-ASR không đồng nghĩa video không có nội dung.

### 2.6 Taxonomy

Taxonomy audit hiện đủ mạnh để materialize:

- Program/format coarse branches cho corpus.
- L25 subject branches chi tiết.

Nhưng chưa được coi là production truth cho toàn bộ:

- detailed L21/L22 topics cần region-level;
- L26 ingredient/method/stage cần semantic context;
- L28/L29/L30 detailed topics cần enrichment/validation;
- object/action/attribute/scene phải đến từ semantic evidence thay vì suy từ series.

---

## 3. Các file trong bộ kế hoạch

| File | Vai trò |
|---|---|
| `README.md` | Mục lục, trạng thái dữ liệu và các quyết định kiến trúc cốt lõi |
| `00_MASTER_ARCHITECTURE.md` | Bản kiến trúc tổng thể: Data Hub → Query Workspace → Brain → Pruning → Lanes → Temporal → Fusion → Inspector |
| `01_DATA_HUB_MAPPING.md` | Thiết kế trung tâm dữ liệu và mapping BTC/custom/Qwen/OCR/ASR/taxonomy |
| `02_QUERY_BRAIN_SEARCH_MODES.md` | UX nhập query, manual facets, LLM-assisted parsing, single/compare/hybrid/auto/rescue |
| `03_SEARCH_LANES_TECH_STACK.md` | Thiết kế từng lane, encoder đúng vector space, công nghệ Tier 1/2/3 và quyết định stack |
| `04_TEMPORAL_MEDIA_INSPECTOR.md` | Query chuỗi trước/sau, partial matches, timestamp constraints, nearest keyframe, exact frame, media UX |
| `05_IMPLEMENTATION_EVALUATION_ROADMAP.md` | Milestones, dependencies, benchmark, ablation, acceptance gates và failure taxonomy |

**Trạng thái hiện tại:** README và Master Architecture được viết trước để khóa triết lý hệ thống. Các file chuyên đề phải bám các invariant trong Master Architecture, không được tự ý tạo kiến trúc song song.

---

## 4. Quyết định kiến trúc cốt lõi

### D1 — Một video là canonical entity duy nhất

`video_id` là identity chung giữa tất cả nguồn. Video không bị duplicate theo taxonomy.

```text
VIDEO
├── memberships Program/Topic
├── ASR
├── Media-info
├── BTC keyframes
└── Custom keyframes
```

### D2 — BTC frame space và custom frame space phải tách riêng

Không đồng nhất:

```text
BTC keyframe #123 == Custom keyframe #123
```

Hai hệ keyframe chỉ cùng tham chiếu về:

```text
video_id + physical frame index + timestamp
```

Mỗi frame space có `frame_space_id`/`keyframe_space_id` riêng.

### D3 — Shared mapping, independent search lanes

Tất cả lane dùng mapping chung, nhưng index và score không được trộn sớm:

```text
SigLIP2 lane
BTC CLIP lane
Qwen lane
ASR lane
OCR lane
BTC Object lane
Media-info lane
```

Mỗi lane có thể bật/tắt, benchmark và debug độc lập.

### D4 — Canonical result contract chung

Mọi lane phải trả về cùng lớp kết quả tối thiểu:

```text
lane
entity_type
video_id
frame_space
frame/keyframe reference hoặc time range
timestamp_ms
score_raw
rank
evidence
```

Nhờ đó có thể làm Compare, Sequence và Late Fusion mà không merge vector spaces.

### D5 — Không cộng raw scores giữa các model khác nhau

Không cộng trực tiếp cosine của SigLIP, CLIP, BGE-M3, BM25 hay detector confidence.

Fusion V1 ưu tiên **rank-based fusion** như RRF. Score calibration chỉ triển khai sau benchmark.

### D6 — Query encoder phải đúng embedding space

- Custom SigLIP2 image embedding → query phải qua **đúng SigLIP2 text encoder/preprocessing tương ứng**.
- BTC CLIP ViT-B/32 → query phải qua **đúng CLIP ViT-B/32 text encoder**.
- BGE-M3 → dùng cho text↔text: ASR/OCR/Qwen caption/metadata/topic semantics.

Không cross-compare vector ở các space khác nhau.

### D7 — Query Brain là trợ lý lập kế hoạch, không là black box authority

Brain có thể:

- đoán Program/Topic;
- tách object/action/attribute/scene;
- phát hiện OCR/ASR hints;
- phát hiện sequence/temporal intent;
- gợi ý lanes;
- gợi ý pruning mode.

Nhưng operator phải nhìn thấy và sửa được plan trước/hoặc sau khi search.

### D8 — LLM-assisted + structured manual input cùng tồn tại

Không chọn một trong hai.

UI hỗ trợ đồng thời:

1. **Natural query:** giữ nguyên câu BTC.
2. **AI decomposition:** gợi ý facets.
3. **Manual chips/fields:** operator thêm/xóa/sửa object/action/scene/text...
4. **Final effective query plan:** kết hợp natural text + manual overrides.

### D9 — Temporal Sequence là search mode chính thức

Phải hỗ trợ:

```text
A BEFORE B
A THEN B
A → B → C
```

với:

- same-video constraint;
- strict/soft order;
- configurable min/max gap;
- mixed modalities giữa các step;
- both-match;
- only-before;
- only-after;
- timeline evidence.

### D10 — Pruning có 3 mức

```text
OFF
SAFE
AGGRESSIVE
```

- OFF: baseline/benchmark toàn corpus.
- SAFE: ưu tiên candidate branches nhưng vẫn có escape/rescue.
- AGGRESSIVE: hard scope chỉ khi Ground Truth chứng minh recall an toàn.

### D11 — Generic object không phải hard-prune evidence

Các object như `person`, `car`, `table`, `food`, `pan` xuất hiện rộng. Không được cắt corpus chỉ vì một object generic.

Hard prune cần evidence mạnh hơn, ví dụ Program/Topic có độ đặc hiệu cao hoặc nhiều family evidence độc lập.

### D12 — Exact frame chỉ lấy từ source video authority

Keyframe là candidate/evidence, không phải authority cuối.

Kết quả cuối:

```text
candidate keyframe/time
→ source video
→ exact frame resolver
→ frame authority
```

---

## 5. Search modes mục tiêu

### 5.1 Single Lane

Operator chọn một lane để hiểu nó mạnh/yếu ở đâu:

- SigLIP2
- BTC CLIP
- Qwen semantic
- ASR
- OCR
- BTC Objects
- Media-info

### 5.2 Compare Mode

Một query chạy nhiều lane độc lập và hiển thị cạnh nhau.

Mục tiêu:

- biết GT nằm rank bao nhiêu ở từng lane;
- biết failure đến từ search hay fusion;
- quyết định lane nào đáng giữ/tune.

### 5.3 Structured Manual Mode

Operator tự nhập:

```text
Program
Topic
Objects [+]
Attributes [+]
Actions [+]
Scenes [+]
OCR text [+]
ASR phrase [+]
Negative constraints [+]
```

Natural query vẫn được giữ lại làm semantic fallback.

### 5.4 Assisted Mode

Natural query → Brain đề xuất facets/lane plan → operator sửa → search.

### 5.5 Manual Hybrid

Operator tự chọn lane nào tham gia và trọng số/priority logic ở mức đơn giản.

### 5.6 Sequence Mode

2–5 step, mỗi step có thể là natural query hoặc structured facets riêng.

### 5.7 Auto Mode

Brain tự:

- decompose;
- chọn branch;
- chọn lanes;
- chọn sequence nếu cần;
- chọn SAFE pruning;
- fusion;
- rescue.

Auto chỉ triển khai sau khi single/compare modes có benchmark đủ tốt.

### 5.8 Global Rescue

Một lane hoặc nhóm lane chạy rộng ngoài scope pruning để giảm false negative.

---

## 6. Technology tiers — nguyên tắc chung

Chi tiết nằm ở `03_SEARCH_LANES_TECH_STACK.md`, nhưng định hướng chốt:

### Tier 1 — nên triển khai trước

- SQLite canonical runtime metadata + relational joins.
- SQLite FTS5/BM25 cho ASR/OCR/metadata lexical search.
- Fuzzy n-gram/trigram auxiliary index cho OCR nhiễu.
- BGE-M3 dense text retrieval cho ASR/OCR/Qwen caption/metadata semantic search.
- FAISS cho SigLIP2 và BTC CLIP vector indexes.
- Fixed bitset cho video-level branch filtering (873 videos).
- Postings cho frame/region/facet retrieval.
- RRF cho late fusion V1.
- FastAPI orchestration/API.
- Source-video exact-frame resolver.

### Tier 2 — sau benchmark

- BGE-M3 sparse/hybrid retrieval.
- Cross-encoder reranker Top-N.
- HNSW nếu latency/scale benchmark cần.
- Qdrant/Vespa/OpenSearch nếu operational complexity được chứng minh đáng giá.
- learned/calibrated fusion.
- advanced temporal region segmentation.

### Tier 3 — experimental / không ưu tiên đầu tiên

- Neural end-to-end fusion toàn bộ modality.
- ColBERT/late interaction toàn corpus nếu chưa có evidence cần thiết.
- LLM chạy trên toàn corpus hoặc toàn frame online.
- Hard prune bằng LLM-only classification.
- Merge mọi modality thành một “mega embedding”.

---

## 7. Data Hub mục tiêu

Data Hub không phải nơi chứa mọi byte dữ liệu. Nó là nơi **biết mọi byte nằm ở đâu và liên hệ với entity nào**.

```text
VIDEO
│
├── media_info
├── ASR segments
├── taxonomy memberships
│
├── BTC frame space
│   ├── map-keyframe
│   ├── JPEG
│   ├── CLIP row
│   └── Objects
│
└── CUSTOM frame space
    ├── keyframe catalog
    ├── JPEG
    ├── SigLIP row
    ├── Qwen
    └── OCR
```

Canonical paths phải là **relative paths**, không lưu Colab/Windows absolute path làm authority.

---

## 8. Các invariant bắt buộc

1. `video_id` luôn tồn tại trong video catalog.
2. 873 video không được mất do ASR/OCR/Qwen missing.
3. BTC/custom keyframe IDs không được trộn.
4. Mỗi serialized vector index phải có metadata mapping row ↔ entity.
5. Mỗi index phải ghi model/preprocessing/index version.
6. Qwen raw giữ immutable.
7. OCR raw giữ raw text + confidence + bbox; normalized text là derived field.
8. Không fabricate confidence cho Qwen.
9. Không dùng position trong raw JSONL làm timeline order; timeline phải sort bằng timestamp/frame index.
10. Source video là exact-frame authority.
11. Runtime không scan giant raw JSONL trên mỗi query.
12. Derived indexes có thể xóa/rebuild từ canonical sources.
13. Hard prune không bật production nếu chưa qua GT recall gate.

---

## 9. Triết lý benchmark

Không hỏi “model nào hay hơn” bằng cảm giác.

Mỗi BTC query phải có thể chạy:

```text
SigLIP only
BTC CLIP only
Qwen only
ASR only
OCR only
Objects only
Hybrid variants
```

Ghi:

- correct video rank;
- correct frame rank;
- first correct rank;
- Recall@K;
- latency;
- pruning survival;
- sequence success;
- failure reason.

Chỉ fusion những lane đã chứng minh tạo thêm recall/precision hoặc rescue value.

---

## 10. Thứ tự triển khai được chốt

```text
M0  Data contract + Unified Mapping
M1  Independent Search Lanes
M2  Compare Mode + Benchmark Harness
M3  Sequence / Temporal Engine
M4  Taxonomy + SAFE Pruning
M5  Manual Hybrid + RRF
M6  Query Brain / Assisted Mode
M7  Auto Mode + Global Rescue
M8  Competition Hardening / Freeze
```

Không đảo thứ tự bằng cách làm Auto/LLM orchestration trước khi từng lane có benchmark.

---

## 11. Định nghĩa “hoàn thành” cho kiến trúc

Kiến trúc được xem là đủ vững khi:

- từ bất kỳ result nào có thể truy ngược về `video_id + time + source evidence`;
- từng lane search độc lập được;
- Compare Mode cho thấy lane nào hit/miss;
- Sequence Mode chứng minh same-video ordered matching;
- SAFE pruning không làm rơi GT ngoài ngưỡng cho phép;
- Fusion cải thiện so với best single lane trên tập eval;
- Global Rescue cứu được một phần prune/search misses;
- click result mở đúng video/timestamp;
- exact-frame inspector trả frame authority từ source video;
- toàn bộ pipeline có provenance/build manifest để reproduce.

---

## 12. Các tài liệu nguồn nội bộ dùng làm cơ sở

Bộ kế hoạch được xây từ các artifact/audit hiện có trong project, đặc biệt:

- `AIC2026_HIERARCHICAL_RETRIEVAL_AUDIT_TAXONOMY_V1.md`
- `AIC2026_QWEN_OUTPUT_DRIVE_AUDIT_2026-08-17.md`
- `BTC_PROVIDED_DATA_AUDIT_REPORT.md`
- `AUDIT_OCR_FRIEND_DATASET.md`
- `idea3(1).md`
- `README_DATA_CONTRACT_V1_1.md`
- `MIGRATION_NOTES_V1_TO_V1_1.md`
- `RUNTIME_BUILD_NOTES_V1_1.md`
- Project history / existing exact-frame media inspector and unified retrieval foundations.

Các con số trong tài liệu phải được hiểu theo ba mức:

- **VERIFIED/AUDITED:** số liệu có trong artifact audit.
- **DESIGN DECISION:** quyết định kiến trúc của bộ plan.
- **EXPERIMENTAL:** threshold/weight/K cần benchmark trước khi production.

---

## 13. Điều không được làm khi triển khai

- Không overwrite raw Qwen để “cho đẹp schema”.
- Không coi OCR normalized text là raw truth.
- Không dùng one-vector-to-rule-all.
- Không merge BTC/custom keyframe numbering.
- Không tự tạo confidence cho signal không có confidence.
- Không để LLM tự hard prune toàn corpus mà operator không thấy lý do.
- Không bật weighted fusion phức tạp trước khi có ablation.
- Không tối ưu latency bằng cách phá recall mà chưa đo.
- Không tạo nested taxonomy JSON khổng lồ làm runtime index.
- Không phụ thuộc absolute filesystem path trong canonical machine data.

---

## 14. Kết luận ngắn

Kiến trúc AIC 2026 được chốt theo mô hình:

```text
RAW / CANONICAL SOURCES
          ↓
UNIFIED IDENTITY + DATA HUB
          ↓
QUERY WORKSPACE + BRAIN
          ↓
OPTIONAL SAFE PRUNING
          ↓
INDEPENDENT SEARCH LANES
          ↓
TEMPORAL GROUPING / SEQUENCE
          ↓
COMPARE / LATE FUSION
          ↓
GLOBAL RESCUE
          ↓
RESULT CARDS + VIDEO INSPECTOR
          ↓
SOURCE VIDEO EXACT FRAME
```

Đây là nền tảng để vừa **ứng chiến nhanh bằng lane riêng**, vừa có đường nâng cấp rõ ràng đến **Auto multimodal hierarchical retrieval** mà không phải viết lại toàn bộ hệ thống.
