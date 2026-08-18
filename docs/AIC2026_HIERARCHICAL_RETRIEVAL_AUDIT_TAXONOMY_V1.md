# AIC 2026 — Canonical Corpus Audit + Hierarchical Retrieval Taxonomy V1

> **Consolidated one-file deliverable** theo yêu cầu hiện tại của người dùng.  
> File này gộp nội dung tương đương `CORPUS_AUDIT_REBUILT.md`, `TAXONOMY_V1_DESIGN.md` và `PRUNING_ANALYSIS_V1.md`, đồng thời ghi rõ contract để materialize các JSON/JSONL machine-readable ở bước triển khai tiếp theo.  
> **Build timestamp:** 2026-08-17T21:58:00+07:00  
> **Priority:** CORRECTNESS > RECALL SAFETY > PRUNING VALUE > EXPLAINABILITY > SPEED > TAXONOMY BEAUTY

---

## 0. Executive verdict

**AUDIT_GATE = PASS.** Hai JSONL canonical được parse trực tiếp và reconcile đầy đủ:

- **873 / 873 canonical videos**.
- **107,540 / 107,540 ASR segments**.
- **859 videos có ≥1 ASR segment**.
- **14 zero-ASR-segment videos vẫn được giữ trong corpus**.
- **0 duplicate video_id; 0 duplicate segment_id**.
- **0 metadata↔actual segment-count mismatch**.
- **0 orphan segment; 0 negative timestamp; 0 `end < start`; 0 segment vượt duration; 0 empty transcript; 0 source-path mismatch**.

Do audit PASS, taxonomy được phép tiếp tục.

Program-level routing có thể materialize ngay ở mức **PARTIAL/SAFE**, nhưng không nên gọi production-ready vì:

1. L24 có 13 zero-ASR và nhiều transcript rất ngắn/không mang program identity trực tiếp.
2. L21/L22 bắt buộc cần region-level topic index.
3. Topic chi tiết cho L28/L29/L30 vẫn cần semantic/Qwen hoặc manual validation sâu hơn.
4. Object/action/attribute/scene/visible-text facet chưa có Qwen/OCR production evidence.

**READY FOR QWEN ENRICHMENT: YES.**  
**READY FOR RETRIEVAL V2 MATERIALIZATION: PARTIAL.**

---

## 1. Input authority & provenance

| Input | Vai trò | SHA256 | Evidence tier |
|---|---|---|---|
| `asr_videos(2).jsonl` | Canonical video manifest | `32ae95449539b5bc0ed8e0b34dfc298d7604c74b1a812c91c43347f0e5d942e0` | **TIER 1 / direct parse** |
| `asr_segments(2).jsonl` | Full ASR segments | `c978e8870072bf63c00ecfa8debbfc135dce23ec343e95045921c670c618dc0d` | **TIER 1 / direct parse** |
| `Văn bản đã dán (1)(1).txt` | Master prompt / design contract | `15d1338aed9f732e021b4b39016d77be2464b90bda6900c41b5f7d86ab15ded9` | Constraint |
| `AUDIT_VIDEO_PROGRAM_CLASSIFICATION_AND_OVERLAP(1).md` | Historical audit | `e37eb697750467d824a8087775fccfe28f998b12c8bd21af6fba5b6f0adaf158` | **TIER 3 / WEAK** |
| `Đã dán markdown (2)(1).md` | New audit/design response | `c62455676e5951a8a78c6f1539963e962a276c54e9d21310fc83a94548ee2674` | Design/reference; counts rechecked |

Không có production Qwen semantic JSON trong input:

```text
qwen_semantic = NOT_AVAILABLE
ocr_semantic  = NOT_AVAILABLE_IN_THIS_BUILD
visual_semantic = NOT_AVAILABLE_IN_THIS_BUILD
```

---

## 2. Deterministic corpus audit

| Check | Result | Status |
|---|---:|---|
| Total video rows | **873** | PASS |
| Unique `video_id` | **873** | PASS |
| Duplicate `video_id` | **0** | PASS |
| Total ASR segments | **107,540** | PASS |
| Unique `segment_id` | **107,540** | PASS |
| Duplicate `segment_id` | **0** | PASS |
| Videos with ≥1 ASR segment | **859** | PASS |
| Zero-ASR-segment videos | **14** | PASS / retained |
| Metadata `segment_count` sum | **107,540** | PASS |
| Actual segment rows | **107,540** | PASS |
| Metadata ↔ actual mismatch | **0** | PASS |
| Segment → unknown video | **0** | PASS |
| Negative timestamp | **0** | PASS |
| `end < start` | **0** | PASS |
| Segment beyond video duration | **0** | PASS |
| Empty transcript | **0** | PASS |
| Source-path stem mismatch | **0** | PASS |
| Malformed video rows | **0** | PASS |
| Malformed segment rows | **0** | PASS |
| Unique source-video paths | **873** | PASS |

Không có independent organizer reference-manifest trong input hiện tại để tự tái-enumerate `missing/unexpected IDs` ngoài canonical manifest. Tuy nhiên canonical manifest tự nó có đúng 873 unique IDs và segment set không trỏ ra ngoài manifest.

### 2.1 Series distribution — authority table

| Series | Total | Has ASR | Zero ASR | % Corpus |
|---|---:|---:|---:|---:|
| L21 | **29** | 29 | 0 | 3.32% |
| L22 | **31** | 31 | 0 | 3.55% |
| L23 | **25** | 25 | 0 | 2.86% |
| L24 | **43** | 30 | 13 | 4.93% |
| L25 | **88** | 88 | 0 | 10.08% |
| L26 | **498** | 498 | 0 | 57.04% |
| L27 | **16** | 16 | 0 | 1.83% |
| L28 | **24** | 24 | 0 | 2.75% |
| L29 | **23** | 23 | 0 | 2.63% |
| L30 | **96** | 95 | 1 | 11.00% |
| **TOTAL** | **873** | **859** | **14** | **100.00%** |

### 2.2 Zero-ASR-segment videos

`segment_count=0` chỉ chứng minh Whisper không sinh segment; **không được diễn giải thành “video không có tiếng nói”**.

- `L24_V008`
- `L24_V013`
- `L24_V015`
- `L24_V016`
- `L24_V019`
- `L24_V021`
- `L24_V027`
- `L24_V028`
- `L24_V029`
- `L24_V031`
- `L24_V033`
- `L24_V038`
- `L24_V043`
- `L30_V029`

Phân bố: **L24 = 13**, **L30 = 1 (`L30_V029`)**.

---

## 3. Reconciliation với các audit trước

### 3.1 Audit mới

Audit mới claim 873 video / 107,540 segments / 859 có ASR / 14 zero-ASR. **Bốn con số này đều được direct-parse xác nhận lại.**

### 3.2 Audit lịch sử 859-video

Audit lịch sử không hoàn toàn vô dụng. Program identity theo series nhìn chung là seed tốt. Nhưng nó có hai vấn đề:

1. Nó gọi **859 video có ASR** là “100% dataset”, trong khi canonical corpus là 873. L24=30 và L30=95 trong report cũ thực chất là **ASR-bearing counts**, không phải canonical counts. Khi cộng 13 zero-ASR của L24 và 1 zero-ASR của L30, ta có đúng **L24=43, L30=96**.
2. Cross-taxonomy keyword matrix không thể dùng làm production membership. Ví dụ L25 là Education nhưng keyword matrix từng match gần như toàn bộ L25 vào nhiều category không liên quan. Đây là lexical occurrence, không phải semantic category.

Audit cũ còn có arithmetic inconsistency: `L21=29` và `L22=31` nhưng phần kết luận ghi tổng là 62; canonical arithmetic là **60**.

**Decision:** giữ historical report để hiểu tên/format series và chọn sample; bỏ keyword-derived memberships khỏi production taxonomy.

---

## 4. Semantic validation methodology

Không classify 873 video chỉ bằng transcript đầu tiên. Validation V1 dùng:

- whole-video ASR aggregate;
- sample đầu / giữa / cuối;
- representative/random samples trong từng series;
- repeated program intro/identity across series;
- cross-check với series prior;
- outlier scan để tìm transcript lệch majority.

Representative sample IDs đã đọc:

- **L21:** `L21_V001`, `L21_V016`, `L21_V031`, `L21_V027`, `L21_V023`
- **L22:** `L22_V001`, `L22_V016`, `L22_V031`, `L22_V002`, `L22_V011`
- **L23:** `L23_V001`, `L23_V013`, `L23_V025`, `L23_V002`, `L23_V022`
- **L24:** `L24_V002`, `L24_V023`, `L24_V045`, `L24_V003`, `L24_V024`
- **L25:** `L25_V001`, `L25_V045`, `L25_V088`, `L25_V017`, `L25_V071`
- **L26:** `L26_V001`, `L26_V250`, `L26_V499`, `L26_V101`, `L26_V357`
- **L27:** `L27_V001`, `L27_V009`, `L27_V016`, `L27_V005`, `L27_V015`
- **L28:** `L28_V001`, `L28_V013`, `L28_V024`, `L28_V021`
- **L29:** `L29_V001`, `L29_V012`, `L29_V023`, `L29_V005`, `L29_V006`
- **L30:** `L30_V001`, `L30_V049`, `L30_V096`, `L30_V019`, `L30_V068`

### 4.1 Semantic findings quan trọng

- **L21/L22:** nhất quán là `60 Giây` / multi-topic news; mỗi video chứa nhiều story độc lập.
- **L23:** nhất quán cycling broadcast: tay đua, áo vàng/áo xanh, nước rút, chặng đua, về đích.
- **L24:** series prior và một số transcript dài xác nhận Lion/Dragon Dance competition; nhưng 13 zero-ASR + nhiều clip ngắn/generic khiến individual evidence yếu. Không được hard-prune chỉ dựa ASR của các clip này.
- **L25:** nhất quán exam-prep/lecture và có thể chia sâu sạch theo môn học.
- **L26:** nhất quán Cooking Demonstration / `Món Ngon Mỗi Ngày`.
- **L27:** nhất quán Travel / Local Experience, thường giao với food/culture.
- **L28:** documentary về Mê Kông/miền Tây, kết hợp lịch sử, địa lý, dòng sông, sinh kế; seed `History/Geography` hợp lý nhưng không nên coi đó là topic duy nhất.
- **L29:** seed `Ecology/Biodiversity` **quá hẹp ở tầng Program**. ASR có cả nghề thủ công, sinh kế, văn hóa, con người và môi trường. Program được sửa thành `Mekong Documentary / People-Culture-Environment`; Ecology chuyển xuống Topic.
- **L30:** phần lớn là feature tích cực/cộng đồng/đời sống địa phương, nhưng chủ đề rất đa dạng. `L30_V096` là promotional/meta clip của cuộc thi và được flag OUTLIER.

---

## 5. PROGRAM TREE V1

```text
PROGRAM
├── News / Bản tin
│   └── L21 + L22 = 60
├── Sports
│   └── Cycling Broadcast = L23 = 25
├── Cultural Performance
│   └── Lion / Dragon Dance Competition = L24 = 43
├── Education
│   └── Exam Preparation / Lecture = L25 = 88
├── Cooking
│   └── Cooking Demonstration = L26 = 498
├── Travel / Experience
│   └── Local Travel / Food / Culture = L27 = 16
├── Documentary
│   ├── Mekong History / Geography / Livelihood = L28 = 24
│   └── Mekong People / Culture / Environment = L29 = 23
└── Positive Community & Local-Life Feature
    └── L30 = 96
```

### 5.1 Canonical program membership rule

One leaf = one canonical `video_id`. Không duplicate metadata theo category.

```text
L21_* → program/news
L22_* → program/news
L23_* → program/sports/cycling
L24_* → program/cultural-performance/lion-dragon-dance
L25_* → program/education/exam-prep
L26_* → program/cooking/demonstration
L27_* → program/travel-experience
L28_* → program/documentary/mekong-history-geography
L29_* → program/documentary/mekong-people-culture-environment
L30_* → program/positive-community-local-life-feature
```

Status rule:

- L21/L22/L23/L25/L26/L27/L28/L29: `VERIFIED` bằng ASR aggregate + series identity.
- L24 direct-ASR verified: `L24_V002`, `L24_V003`, `L24_V004`, `L24_V012`, `L24_V017`.
- L24 còn lại: `INFERRED` từ verified series identity nhưng individual ASR yếu/zero/thematic; đưa manual review.
- `L30_V029`: `INFERRED` + `ZERO_ASR`.
- `L30_V096`: `OUTLIER` — promotional/meta-content.
- L30 còn lại: `VERIFIED` ở mức program format rộng `positive/community/local-life feature`.

**Program status summary:**

- VERIFIED = **833**
- INFERRED = **39**
- OUTLIER = **1**

> Numeric confidence trong report này là **heuristic build confidence**, không phải calibrated probability và chưa được dùng làm production threshold.

---

## 6. PROGRAM pruning analysis

`Prune % = 1 - branch_count / 873`.

| Branch | Count | Corpus % | Prune % | Mean conf. | Min conf. | Ambiguous/inferred | Value | Flags |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `program/news` | 60 | 6.87% | **93.13%** | 0.990 | 0.99 | 0 | HIGH | GOOD_PRUNING_BRANCH |
| `program/sports/cycling` | 25 | 2.86% | **97.14%** | 0.990 | 0.99 | 0 | HIGH | GOOD_PRUNING_BRANCH |
| `program/cultural-performance/lion-dragon-dance` | 43 | 4.93% | **95.07%** | 0.682 | 0.62 | 38 | HIGH | HIGH_AMBIGUITY |
| `program/education/exam-prep` | 88 | 10.08% | **89.92%** | 0.990 | 0.99 | 0 | HIGH | GOOD_PRUNING_BRANCH |
| `program/cooking/demonstration` | 498 | 57.04% | **42.96%** | 0.995 | 0.99 | 0 | LOW | TOO_BROAD |
| `program/travel-experience` | 16 | 1.83% | **98.17%** | 0.980 | 0.98 | 0 | HIGH | GOOD_PRUNING_BRANCH |
| `program/documentary/mekong-history-geography` | 24 | 2.75% | **97.25%** | 0.970 | 0.97 | 0 | HIGH | GOOD_PRUNING_BRANCH |
| `program/documentary/mekong-people-culture-environment` | 23 | 2.63% | **97.37%** | 0.950 | 0.95 | 0 | HIGH | GOOD_PRUNING_BRANCH |
| `program/positive-community-local-life-feature` | 96 | 11.00% | **89.00%** | 0.923 | 0.58 | 2 | HIGH | GOOD_PRUNING_BRANCH |

### 6.1 Interpretation

- **Strongest clean routing:** Travel L27, L28/L29 documentary children, Cycling L23, News, Education.
- **Cooking is the only clearly TOO_BROAD program child:** 498/873 = 57.04% corpus; selecting Cooking only prunes **42.96%**.
- **L24 has excellent theoretical pruning (95.07%) but high evidence ambiguity**, nên branch này không nên hard-route solely from weak ASR.
- **L30 prunes 89.00%**, nhưng topic diversity cao nên Program routing ổn hơn Topic hard-routing.

---

## 7. L25 — deep Education subject routing

ASR cho phép chia L25 thành **9 subject branches** với coverage 88/88:

| Subject | Video count | Prune global | Prune within Education |
|---|---:|---:|---:|
| Literature | **10** | 98.85% | 88.64% |
| History | **10** | 98.85% | 88.64% |
| Biology | **10** | 98.85% | 88.64% |
| Chemistry | **10** | 98.85% | 88.64% |
| Physics | **10** | 98.85% | 88.64% |
| English | **10** | 98.85% | 88.64% |
| Geography | **10** | 98.85% | 88.64% |
| Mathematics | **10** | 98.85% | 88.64% |
| Economics & Law | **8** | 99.08% | 90.91% |

Đây là một trong những nhánh pruning tốt nhất: Education 88 → subject 8–10 video.

### 7.1 Exact L25 subject mapping

**Literature (10):** `L25_V001`, `L25_V010`, `L25_V018`, `L25_V027`, `L25_V036`, `L25_V045`, `L25_V054`, `L25_V063`, `L25_V080`, `L25_V081`

**History (10):** `L25_V002`, `L25_V011`, `L25_V019`, `L25_V028`, `L25_V037`, `L25_V046`, `L25_V055`, `L25_V064`, `L25_V072`, `L25_V082`

**Biology (10):** `L25_V003`, `L25_V012`, `L25_V020`, `L25_V029`, `L25_V038`, `L25_V047`, `L25_V056`, `L25_V065`, `L25_V073`, `L25_V083`

**Chemistry (10):** `L25_V004`, `L25_V013`, `L25_V021`, `L25_V030`, `L25_V039`, `L25_V048`, `L25_V057`, `L25_V066`, `L25_V074`, `L25_V084`

**Physics (10):** `L25_V005`, `L25_V014`, `L25_V022`, `L25_V031`, `L25_V040`, `L25_V049`, `L25_V058`, `L25_V067`, `L25_V077`, `L25_V085`

**English (10):** `L25_V006`, `L25_V015`, `L25_V023`, `L25_V032`, `L25_V041`, `L25_V050`, `L25_V059`, `L25_V068`, `L25_V075`, `L25_V086`

**Geography (10):** `L25_V007`, `L25_V016`, `L25_V024`, `L25_V033`, `L25_V042`, `L25_V051`, `L25_V060`, `L25_V069`, `L25_V076`, `L25_V087`

**Mathematics (10):** `L25_V008`, `L25_V017`, `L25_V025`, `L25_V034`, `L25_V043`, `L25_V052`, `L25_V061`, `L25_V070`, `L25_V078`, `L25_V088`

**Economics & Law (8):** `L25_V009`, `L25_V026`, `L25_V035`, `L25_V044`, `L25_V053`, `L25_V062`, `L25_V071`, `L25_V079`

Membership subject hiện được xem là **ASR-semantic VERIFIED** ở mức taxonomy V1; vẫn nên benchmark trên GT query trước khi dùng làm hard route tuyệt đối.

---

## 8. L26 — Cooking faceted sub-routing

L26=498 chiếm 57.04% corpus, vì vậy Program Tree không đủ sâu. Không dùng rigid tree `Food → Meat → Frying`; dùng các dimension multi-label:

```text
COOKING FACETS
├── Ingredient
│   ├── poultry / pork / beef / seafood / egg / tofu
│   ├── vegetables / noodles / rice / fruit / ...
├── Method
│   ├── frying / stir-frying / boiling / steaming / grilling
│   ├── braising / mixing / marinating / chopping / ...
├── Dish Type
│   ├── soup / noodles / rice / salad / snack / main-dish
│   ├── dessert / drink / ...
└── Cooking Stage
    ├── introduction
    ├── ingredient-presentation
    ├── preparation
    ├── cooking
    ├── plating
    └── tasting
```

### 8.1 Vì sao chưa materialize facet bằng keyword

Một lexical probe trên chính L26 cho thấy contamination rất rõ:

- `canh` xuất hiện trong **451** video, nhưng **426** video có cụm `muỗng canh` — đây thường là đơn vị đo tablespoon, không chứng minh `dish_type=soup`.
- `hấp` xuất hiện trong **408** video, nhưng **388** video có `hấp dẫn` — không chứng minh `method=steaming`.

Vì vậy:

```text
SCHEMA_READY = YES
ASR_LEXICAL_MEMBERSHIP = WEAK / NOT_PRODUCTION
QWEN_FRAME_MEMBERSHIP = NOT_AVAILABLE
OCR_MEMBERSHIP = NOT_AVAILABLE_IN_THIS_BUILD
```

Cooking facet nên được materialize sau bằng **ASR semantic context + Qwen visual/frame semantics + OCR**, không bằng single-token hits.

---

## 9. TOPIC GRAPH V1

Program trả lời **“đây là loại chương trình gì?”**; Topic trả lời **“nội dung đang nói về chuyện gì?”**.

Topic là multi-label graph:

```text
TOPIC
├── People & Society
│   ├── community / charity / occupation / livelihood
│   ├── inspirational-people / family / education
├── Traffic & Transportation
│   ├── road / accident / infrastructure / public-transport
├── Food & Cooking
│   ├── cooking / local-food / cuisine
├── Education & Knowledge
│   ├── exam-prep
│   ├── literature / history / biology / chemistry / physics
│   ├── english / geography / mathematics / economics-law
├── Sports & Competition
│   ├── cycling
│   └── cultural-performance-competition
├── Travel & Places
├── Culture & Tradition
│   ├── folk-performance / craft / heritage / local-culture
├── Nature & Environment
│   ├── rivers / wetlands / forests / animals / plants / biodiversity
├── Economy & Business
├── Health
├── Weather & Disaster
├── Law & Security
├── Science & Technology
├── Public Affairs & Policy
└── International Affairs
```

### 9.1 Video-level materialization policy V1

Chỉ materialize khi evidence đủ mạnh:

- L23 → `topic/sports/cycling` VERIFIED.
- L25 → `topic/education/knowledge` + exact subject branch VERIFIED.
- L26 → `topic/food/cooking` VERIFIED.
- L27 → `topic/travel/places` VERIFIED; food/culture secondary membership chỉ thêm khi whole-video evidence đủ.
- L24 → culture/competition membership có thể INFERRED từ series; **không hard-route weak individual ASR**.
- L21/L22 → **không gắn video-level single topic**; topic phải nằm ở REGION.
- L28/L29/L30 → Program route có thể dùng ngay; detailed topic membership nên multi-label và được materialize sau bằng semantic aggregation/Qwen, không ép một label.

---

## 10. FACET INDEX schema

Facet không phải Topic và không ép vào tree. Namespace contract:

```text
object/<value>
attribute/<value>
action/<value>
scene/<value>
spatial_relation/<value>
person_role/<value>
count/<value>
visible_text/<value>
event/<value>

domain/cooking/ingredient/<value>
domain/cooking/method/<value>
domain/cooking/dish_type/<value>
domain/cooking/stage/<value>
```

Proposed record:

```json
{
  "facet_id": "action/riding",
  "namespace": "action",
  "canonical_value": "riding",
  "aliases": ["đang chạy xe", "đạp xe"],
  "scope": "region|keyframe|frame",
  "confidence": 0.0,
  "evidence": {
    "asr": null,
    "qwen_semantic": "NOT_AVAILABLE",
    "ocr": "NOT_AVAILABLE",
    "visual": "NOT_AVAILABLE"
  },
  "status": "SCHEMA_READY|MEMBERSHIP_VERIFIED|MEMBERSHIP_INFERRED|UNKNOWN"
}
```

Không tự bịa object/action membership từ ASR nếu object/action là thông tin hình ảnh.

---

## 11. TEMPORAL REGION strategy — đặc biệt L21/L22

Freeze:

```text
L21/L22.requires_region_level_topic_index = true
```

Một bản tin ~20 phút chứa nhiều story. Gắn toàn video vào Traffic/Sports/Weather làm topic posting sẽ không prune timeline đủ sâu.

### 11.1 `region_strategy_proposal`

**Input signals:**

1. ASR semantic continuity.
2. ASR discourse/transition cues: `tiếp theo`, `sau đây`, `chuyển sang`, `ở phần...`, `cuối cùng`, anchor reset.
3. Temporal gap giữa ASR segments.
4. Shot-boundary clusters.
5. Qwen semantic continuity/change score khi có.
6. OCR lower-third/headline changes khi có.

**Proposed offline flow:**

```text
ASR segments
  → candidate boundaries
  → semantic windows 20–40s
  → change-point score
  → fuse temporal gap + discourse cue + shot boundary + Qwen/OCR
  → snap boundary to safe sentence/shot edge
  → region_type = headline|story|weather|sports|promo|unknown
  → multi-label topics + confidence
  → region postings
```

Không hard-code final min/max duration trước benchmark; seed hợp lý để thử nghiệm là minimum ~15–20s và merge adjacent regions khi semantic continuity cao.

Query `tai nạn giao thông` khi đó đi:

```text
873 videos
→ News = 60
→ Traffic/Accident regions
→ keyframes inside regions only
→ SigLIP/Qwen/ASR/OCR fusion
→ exact-frame verification
```

---

## 12. Leaf, multi-parent & canonical catalog invariants

1. One leaf = one `video_id`.
2. Canonical video record tồn tại đúng một lần.
3. Program/Topic category leaf chỉ giữ reference/posting.
4. Video có thể có nhiều Topic parent.
5. Region không phải taxonomy leaf; region nằm dưới video.
6. Zero-ASR video không được rơi khỏi catalog.

Canonical catalog record:

```json
{
  "video_id": "L25_V011",
  "series": "L25",
  "duration_sec": 0.0,
  "has_asr": true,
  "asr_segment_count": 0,
  "program_branch_ids": ["program/education/exam-prep"],
  "topic_branch_ids": ["topic/education/knowledge", "topic/education/history"],
  "requires_region_index": false,
  "classification_status": "VERIFIED",
  "evidence_summary": {}
}
```

---

## 13. Query routing contract

Không chọn single branch duy nhất. Router trả ranked candidates:

```json
{
  "top_branches": [
    {"branch_id": "program/travel-experience", "score": 0.66},
    {"branch_id": "program/cooking/demonstration", "score": 0.48},
    {"branch_id": "program/positive-community-local-life-feature", "score": 0.27}
  ],
  "top_confidence": 0.66,
  "margin": 0.18,
  "ambiguity": "MEDIUM"
}
```

### 13.1 Three search modes

- **AUTO:** router tự chọn ranked branch set.
- **GUIDED:** UI hiển thị branch + candidate count; người dùng đổi scope ngay.
- **GLOBAL:** search toàn 873, bỏ qua taxonomy.

Menu nên hiển thị ít nhất:

```text
All                                      873
Cooking                                  498
Positive Community / Local-Life           96
Education                                  88
News                                       60
Lion / Dragon Dance                        43
Cycling                                    25
Documentary L28                            24
Documentary L29                            23
Travel / Experience                        16
```

---

## 14. Hard prune vs soft prune

### HARD / aggressive prune

Chỉ dùng khi:

- program/topic evidence rất mạnh;
- ít nhất hai evidence độc lập đồng thuận;
- router confidence cao và margin đủ rộng;
- branch không nằm trong high-ambiguity set;
- GT benchmark chứng minh recall được bảo vệ.

**Candidate hard-route branches sau benchmark:** Education subject, Cycling, clear News program, clear Cooking program query, clear Travel program query.

### SOFT prune

Dùng khi:

- generic object/action;
- ambiguous semantic;
- one weak keyword;
- L24 weak individual ASR;
- L28/L29/L30 topic-level routing;
- query có thể xuất hiện trong nhiều program.

Ví dụ `người cầm dao` không được hard-route Cooking.

### 14.1 Threshold seed — chỉ để benchmark, chưa production

```text
top_score >= 0.88 AND margin >= 0.20 AND >=2 evidence families
    → eligible for hard-prune experiment

0.60 <= top_score < 0.88 OR small margin
    → soft-prune / union top-2 or top-3 branches

top_score < 0.60
    → GLOBAL or very broad union
```

Không hard-code các threshold này trước GT evaluation.

---

## 15. GLOBAL ESCAPE / rescue lane

Taxonomy không được là single point of failure.

```text
FINAL VIDEO CANDIDATES
= PRIMARY hierarchical candidates
+ GLOBAL_ESCAPE candidates
```

Design seed cho corpus chỉ 873 video:

- high-confidence hard route: giữ thêm **global top-32 videos**;
- medium/ambiguous route: giữ thêm **global top-64 videos**;
- low-confidence query: bỏ hard prune, dùng global top-100 hoặc Search All 873;
- deduplicate union trước temporal/keyframe reranking.

Con số 32/64/100 là **benchmark seed**, không phải production constant.

---

## 16. Confidence + provenance contract

```json
{
  "video_id": "L23_V003",
  "branch_id": "topic/sports/cycling",
  "membership_type": "program|topic",
  "confidence": 0.98,
  "evidence": {
    "series_prior": 1.0,
    "asr_program_identity": 0.98,
    "asr_semantic": 0.97,
    "manual_rule": null,
    "qwen_semantic": "NOT_AVAILABLE",
    "ocr": "NOT_AVAILABLE",
    "visual": "NOT_AVAILABLE"
  },
  "status": "VERIFIED"
}
```

Không collapse evidence thành một boolean.

---

## 17. Manual review queue & outliers

**Queue size in this V1 audit: 40 items.**

Composition:

- 14 ZERO_ASR — HIGH.
- 20 L24 low-information ASR clips (<100 transcript chars) — HIGH.
- 5 L24 thematic/ambiguous transcripts — MEDIUM.
- `L30_V096` promotional/meta program outlier — MEDIUM.

Priority examples:

| video_id | reason | priority |
|---|---|---|
| `L24_V008` | ZERO_ASR | HIGH |
| `L24_V013` | ZERO_ASR | HIGH |
| `L24_V015` | ZERO_ASR | HIGH |
| `L24_V016` | ZERO_ASR | HIGH |
| `L24_V019` | ZERO_ASR | HIGH |
| `L24_V021` | ZERO_ASR | HIGH |
| `L24_V027` | ZERO_ASR | HIGH |
| `L24_V028` | ZERO_ASR | HIGH |
| `L24_V029` | ZERO_ASR | HIGH |
| `L24_V031` | ZERO_ASR | HIGH |
| `L24_V033` | ZERO_ASR | HIGH |
| `L24_V038` | ZERO_ASR | HIGH |
| `L24_V043` | ZERO_ASR | HIGH |
| `L30_V029` | ZERO_ASR | HIGH |
| `L24_V005` | LOW_INFORMATION_ASR: transcript <100 chars; mostly generic/subscribe text | HIGH |
| `L24_V006` | LOW_INFORMATION_ASR: transcript <100 chars; mostly generic/subscribe text | HIGH |
| `L24_V007` | LOW_INFORMATION_ASR: transcript <100 chars; mostly generic/subscribe text | HIGH |
| `L24_V009` | LOW_INFORMATION_ASR: transcript <100 chars; mostly generic/subscribe text | HIGH |

Additional L24 low-information IDs:

`L24_V005`, `L24_V006`, `L24_V007`, `L24_V009`, `L24_V010`, `L24_V011`, `L24_V014`, `L24_V020`, `L24_V022`, `L24_V023`, `L24_V024`, `L24_V025`, `L24_V026`, `L24_V030`, `L24_V035`, `L24_V039`, `L24_V040`, `L24_V041`, `L24_V044`, `L24_V045`

L24 thematic/ambiguous IDs:

`L24_V018`, `L24_V032`, `L24_V036`, `L24_V037`, `L24_V042`

Không coi lexical TF-IDF/keyword outlier là proof của wrong program; nó chỉ dùng để tạo review candidate.

---

## 18. Taxonomy quality flags

### GOOD_PRUNING_BRANCH

- Travel / Experience.
- Cycling.
- L28/L29 Documentary children.
- News.
- Education.
- Human/Community Local-Life program branch.

### TOO_BROAD

- Cooking program-level branch: 498 videos.

### HIGH_AMBIGUITY

- L24 at individual-video evidence level.
- Detailed topics inside News before region segmentation.
- Detailed topic memberships for L28/L29/L30 before semantic/Qwen enrichment.

### TOO_SMALL — caution, not automatic rejection

- L25 subject children (8–10 videos) are small but highly useful **if router evidence is specific**.
- Small branch should not be hard-pruned from generic queries.

---

## 19. Search-optimized output layout for later materialization

```text
taxonomy_v1/
├── audit/
│   ├── corpus_audit.json
│   ├── corpus_audit.md
│   └── zero_asr_videos.json
├── catalog/
│   ├── video_catalog_v1.jsonl
│   └── video_ordinals_v1.json
├── program/
│   ├── program_nodes_v1.jsonl
│   ├── program_membership_v1.jsonl
│   └── program_postings_v1.json
├── topic/
│   ├── topic_nodes_v1.jsonl
│   ├── topic_membership_v1.jsonl
│   └── topic_postings_v1.json
├── facets/
│   └── facet_schema_v1.json
├── analysis/
│   ├── pruning_analysis.md
│   ├── taxonomy_quality_report.md
│   ├── ambiguous_videos.jsonl
│   ├── outliers.jsonl
│   └── manual_review_queue.jsonl
└── provenance/
    ├── build_manifest.json
    └── schema_versions.json
```

Phase audit có thể dùng JSON video-ID lists; runtime sau convert sang dense ordinals + bitmap.

---

## 20. Runtime target

```text
QUERY
  ↓
QUERY DECOMPOSITION
  ↓
PROGRAM / TOPIC / FACET ROUTING
  ↓
RANKED BRANCHES
  ↓
AUTO or GUIDED
  ↓
VIDEO BITMAP
  ↓
VIDEO PROFILE RANKING
  ↓
TEMPORAL REGION
  ↓
QWEN / SIGLIP / ASR / OCR
  ↓
FUSION
  ↓
GLOBAL RESCUE
  ↓
TOP-K FRAME
  ↓
SOURCE VIDEO VERIFY
  ↓
EXACT FRAME
```

---

## 21. Mandatory self-critique

### 1. Branch nào prune mạnh nhất?

Trong Program Tree: **Travel L27 (98.17%)**, sau đó L29 documentary (97.37%), L28 documentary (97.25%), Cycling (97.14%). L25 subject routing còn mạnh hơn: 873 → 8–10 video (~98.85–99.08% prune).

### 2. Branch nào quá rộng?

**Cooking = 498 / 873 = 57.04% corpus.** Program-only routing chưa đủ; cần cooking facets.

### 3. Branch nào gần như vô dụng?

Không có Program branch hoàn toàn vô dụng, nhưng một generic Topic kiểu `People & Society` nếu materialize quá rộng sẽ có pruning value thấp. Không nên biến broad topic thành hard filter.

### 4. Branch nào dễ làm mất recall?

L24 weak-ASR, News video-level topics, generic object/action queries, và detailed topics trong L28/L29/L30.

### 5. L26 cần chia sâu thế nào?

Multi-label `Ingredient × Method × Dish Type × Cooking Stage`, materialize bằng contextual ASR + Qwen + OCR/visual; không keyword-only.

### 6. L21/L22 cần region-level ra sao?

Story-boundary detection dựa trên ASR continuity + discourse cues + temporal gaps + shot boundaries + Qwen/OCR change; topic postings phải gắn region.

### 7. Category nào từ audit cũ bị chứng minh sai/nhiễu?

Cross-taxonomy keyword memberships. Việc một Education video chứa từ `thể thao`, `du lịch`, `âm nhạc`, v.v. không biến nó thành các semantic categories đó.

### 8. Series nào không thuần như giả định?

**L29** không thuần Ecology/Biodiversity; nó là documentary rộng về people/culture/livelihood/environment. **L30** cũng đa dạng chủ đề hơn `character story` thuần túy.

### 9. Có video outlier không?

`L30_V096` là rõ nhất ở format: clip quảng bá/thể lệ cuộc thi thay vì feature story. L24 có nhiều low-information/zero-ASR cần visual review nhưng chưa đủ evidence để gọi misfiled outlier.

### 10. Query không rõ topic thì UI nên đưa gì?

Ranked Program branches + candidate counts + `All 873`; cho phép đổi branch ngay và không rerun offline Qwen.

### 11. Taxonomy tốt hơn flat search ở đâu?

Nó giảm candidate sớm bằng high-confidence program/subject postings, giảm số video/timeline cần rerank, nhưng vẫn giữ global rescue để bảo vệ recall.

### 12. Phần nào phải đợi Qwen?

Object/action/attribute/scene/spatial relation/count, visual cooking facets, detailed L28/L29/L30 topics, và hỗ trợ region semantic continuity.

### 13. Qwen mâu thuẫn ASR thì sao?

Không overwrite. Giữ provenance riêng; giảm confidence, mark `AMBIGUOUS`, union candidate branches, đưa manual review nếu conflict ảnh hưởng hard-prune.

### 14. Branch nào hard-route / soft-route?

Hard-route candidates sau benchmark: explicit Education subject, Cycling, clear Cooking/Travel/News program query. Soft-route: L24 weak evidence, detailed documentary/human-interest topics, generic visual facets.

### 15. Global escape nên giữ bao nhiêu?

Seed: top-32 khi route rất chắc, top-64 khi ambiguous; low-confidence thì top-100 hoặc toàn 873. Phải tune bằng Ground Truth.

---

## 22. Final validation

Validation trước khi chốt report:

- [x] 873 unique videos.
- [x] No duplicate canonical video.
- [x] 107,540 unique ASR segments.
- [x] Metadata segment counts reconcile.
- [x] Program mapping covers 873/873 hoặc explicit OUTLIER/INFERRED status.
- [x] L25 subject mapping covers 88/88 exactly once.
- [x] Zero-ASR 14 vẫn trong catalog.
- [x] Program branch counts sum = 873.
- [x] Program postings rule trỏ only valid video IDs.
- [x] No Qwen/OCR/visual results fabricated.
- [x] No keyword-derived L26 facet membership promoted to VERIFIED.
- [x] L21/L22 marked region-required.

---

## 23. Final status summary

```text
CORPUS:
873 / 873

ASR SEGMENTS:
107,540

PROGRAM CLASSIFICATION:
VERIFIED = 833
INFERRED = 39
AMBIGUOUS = 0 as terminal status; ambiguous evidence is represented in review queue
OUTLIER = 1

TOPIC CLASSIFICATION:
VIDEO-LEVEL = PARTIAL / evidence-gated
NEWS TOPICS = REGION-LEVEL REQUIRED
L25 SUBJECTS = 88 / 88 mapped
L26 FACETS = SCHEMA_READY, MEMBERSHIP NOT PRODUCTION

ZERO ASR:
14 retained

MANUAL REVIEW QUEUE:
40 items

BEST PRUNING BRANCHES:
Travel, L28/L29 documentary children, Cycling, Education subjects

HIGH-RISK BRANCHES:
L24 weak/zero-ASR, News video-level topics, broad documentary/human-interest topics

QWEN SEMANTIC:
NOT_AVAILABLE

READY FOR QWEN ENRICHMENT:
YES

READY FOR RETRIEVAL V2 MATERIALIZATION:
PARTIAL
```

---

## 24. Recommended next implementation order

1. Materialize **canonical video catalog + ordinal mapping**.
2. Materialize **Program nodes/membership/postings** với provenance/status.
3. Materialize **L25 subject postings** — đây là deep-pruning branch sạch nhất.
4. Add **router ranked-branch contract + AUTO/GUIDED/GLOBAL**.
5. Build **L21/L22 region segmentation prototype**.
6. Run **Ground Truth recall evaluation** để calibrate hard/soft prune và global-escape K.
7. Sau đó mới materialize **Qwen visual facets**, ưu tiên L26 vì branch quá rộng.

Không nên làm một cây keyword lớn trước Qwen. Không nên hard-prune Topic chi tiết trước khi có GT evaluation.

---

## 25. Bottom line

Canonical corpus hiện **đủ và sạch để xây hierarchical retrieval V1**. Program routing tạo pruning rất lớn trên hầu hết branches; L25 subject routing đặc biệt mạnh. Hai vấn đề kiến trúc chính còn lại là **L26 quá rộng** và **L21/L22 cần region-level topics**.

Thiết kế nên giữ đúng mô hình:

```text
PROGRAM
+ TOPIC GRAPH
+ FACET INDEX
+ TEMPORAL REGION INDEX
+ GLOBAL ESCAPE
```

không phải single tree chọn một đường rồi loại bỏ phần còn lại.