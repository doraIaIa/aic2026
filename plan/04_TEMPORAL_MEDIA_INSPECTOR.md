# 04 — TEMPORAL RETRIEVAL & MEDIA INSPECTOR
## Sequence search, before/after, partial matches, nearest keyframe, exact-frame extraction và operator video inspection

> **Trạng thái:** Design freeze candidate  
> **Phạm vi:** Các query có thứ tự thời gian, tìm quanh một anchor, mapping từ result sang video/frame, preview lân cận, exact-frame authority và media-serving strategy.  
> **Nguyên tắc:** **Keyframe dùng để tìm. Source video dùng để xác minh.**

---

# 1. Tại sao Temporal Retrieval phải là first-class feature?

Nhiều query BTC không chỉ mô tả “một frame có gì”, mà mô tả diễn biến:

```text
cảnh A → sau đó → cảnh B
```

hoặc:

```text
trước khi X xảy ra, có Y
```

hoặc:

```text
một người bước vào phòng, sau đó ngồi xuống, rồi nhận một vật
```

Flat text-to-image retrieval xử lý kém vì nó cố nhồi toàn bộ narrative vào một embedding duy nhất.

Kiến trúc đúng là:

```text
query sequence
↓
chia thành step
↓
search từng step độc lập
↓
group theo video
↓
kiểm tra thứ tự timestamp
↓
rank chuỗi
```

---

# 2. Temporal Query Modes

Hệ thống nên có bốn mode:

```text
A. BEFORE / AFTER
B. ORDERED SEQUENCE 2–5 steps
C. SEARCH AROUND ANCHOR
D. SAME-EVENT / NEARBY
```

Không ép tất cả vào cùng một UI.

---

# 3. BEFORE / AFTER Mode

UI:

```text
BEFORE
[ người phụ nữ đứng trước bảng thông báo ]

AFTER
[ xe tải đi ngang qua ]

Same video        ☑
Strict order      ☑
Max gap           [60] sec
Min gap           [0] sec

[SEARCH]
```

Backend tạo:

```text
step A hits
step B hits
```

sau đó tìm pair:

```text
tA < tB
min_gap <= tB - tA <= max_gap
```

---

# 4. Không hardcode 60 giây thành chân lý

60s là **seed hợp lý để thao tác**, không production truth.

UI nên hỗ trợ:

```text
15s
30s
60s
120s
Custom
Unlimited
```

Default có thể 60s cho dạng “sau cảnh A là cảnh B”, nhưng phải benchmark trên query thật.

Lý do:

- montage/cut nhanh: 5–15s;
- story transition: 30–60s;
- documentary/news: có thể dài hơn;
- keyframe sampling làm hit timestamp lệch event thật.

---

# 5. Ordered Sequence Mode

Ví dụ:

```text
S1: person entering kitchen
S2: putting ingredients into pan
S3: finished dish on plate
```

Constraint:

```text
same_video = true
strict_order = true
max_gap_1_2 = 60s
max_gap_2_3 = 60s
```

Có thể thêm:

```text
max_total_span = 180s
```

để tránh chuỗi đúng thứ tự nhưng cách nhau quá xa.

---

# 6. Mỗi step có lane riêng

Ví dụ query mixed modality:

```text
STEP 1
OCR: "ĐẠI HỌC CẦN THƠ"

STEP 2
SigLIP/Qwen: person riding motorcycle

STEP 3
ASR: "tai nạn giao thông"
```

Sequence engine không cần biết lane hoạt động nội bộ thế nào.

Nó chỉ nhận canonical hits:

```text
video_id
start/end time hoặc point timestamp
rank/score
lane
```

---

# 7. Step Result Contract

Frame hit:

```json
{
  "step_id": "S1",
  "video_id": "L21_V001",
  "kind": "FRAME",
  "timestamp_ms": 14200,
  "frame_idx": 426,
  "lane": "siglip_custom",
  "rank": 3,
  "raw_score": 0.82
}
```

ASR interval hit:

```json
{
  "step_id": "S2",
  "video_id": "L21_V001",
  "kind": "INTERVAL",
  "start_ms": 17000,
  "end_ms": 21000,
  "lane": "asr_dense",
  "rank": 2
}
```

Temporal engine canonicalize interval thành:

```text
start
end
representative timestamp
```

nhưng vẫn giữ interval gốc.

---

# 8. Two-step matching algorithm

Với A và B:

1. Group hits theo `video_id`.
2. Sort A timestamps.
3. Sort B timestamps.
4. Two-pointer hoặc binary search để tìm B đầu tiên sau từng A trong gap window.
5. Tạo pair candidates.
6. Rank pairs.

Complexity rất thấp sau khi Top-K từng step đã nhỏ.

Không cần brute-force toàn corpus frame pairs.

---

# 9. 3–5 step matching

Dùng dynamic programming hoặc beam search.

State:

```text
(step_index, last_timestamp, accumulated_score, path)
```

Transition chỉ cho hit:

```text
same video
correct order
within gap
```

Beam giữ top `B` partial paths mỗi step.

Ưu điểm:

- tránh combinatorial explosion;
- hỗ trợ partial chain;
- dễ thêm gap penalty.

---

# 10. Temporal pair score

Không chỉ dùng semantic scores.

Một seed scoring model:

```text
pair_score =
  rank_support(A)
+ rank_support(B)
+ temporal_proximity_bonus
+ multi-lane_agreement_bonus
- excessive_gap_penalty
```

Không coi đây là calibrated probability.

---

# 11. Temporal proximity function

Ví dụ heuristic:

```text
delta = tB - tA

0–10s    strong bonus
10–30s   medium bonus
30–60s   small bonus
>60s     reject nếu max_gap=60
```

Nhưng event-dependent.

Better Tier 2:

- learn/tune from GT;
- branch-specific gap priors.

---

# 12. Partial Match Policy

Bắt buộc trả:

```text
FULL MATCH
ONLY BEFORE / PREFIX
ONLY AFTER / SUFFIX
```

Với 3 step:

```text
S1+S2+S3
S1+S2
S2+S3
S1 only
S2 only
S3 only
```

UI ưu tiên full chain nhưng không giấu partial.

---

# 13. Tại sao partial cực quan trọng?

Possible failure:

- keyframe sampling miss một step;
- visual encoder miss;
- OCR lỗi;
- ASR không có;
- Qwen thiếu semantic;
- gap threshold hơi hẹp;
- step decomposition chưa chuẩn.

Partial match cho operator một anchor để mở video và xem quanh đó.

---

# 14. Sequence Result UI

```text
VIDEO L26_V361        sequence score 0.91

S1  04:12.2   [thumb]
       ↓ +26.8s
S2  04:39.0   [thumb]
       ↓ +16.1s
S3  04:55.1   [thumb]

[OPEN AT S1] [PLAY SPAN] [PIN CHAIN]
```

Partial:

```text
ONLY BEFORE
L21_V015 @ 09:44

[OPEN +60s WINDOW]
```

---

# 15. Search Around Anchor

Khi operator click một frame:

```text
anchor video = L21_V001
anchor time  = 14.2s
```

UI:

```text
Search:
○ BEFORE
○ AFTER
○ AROUND

Window:
[60] seconds

Query:
[ truck driving past ]
```

Scope tự động:

```text
same video
selected time window
```

Đây là feature rất mạnh cho query dạng “sau đó”.

---

# 16. Anchor có thể đến từ bất kỳ lane

```text
SigLIP frame
BTC CLIP frame
OCR hit
ASR segment
Qwen frame
```

Data Hub convert thành:

```text
video_id + time interval/point
```

Temporal search không phụ thuộc source frame space.

---

# 17. BTC và custom keyframe proximity

Một event có thể có:

```text
BTC keyframe @ 13.0s
CUSTOM keyframe @ 14.2s
```

Không ép chúng thành một frame.

Timeline view có thể cluster:

```text
same video
|delta time| <= tolerance
```

nhưng giữ representatives:

```text
BTC representative
CUSTOM representative
```

---

# 18. Nearest Keyframe Service

Cho `video_id` + target time:

```text
nearest custom
nearest BTC
nearest before
nearest after
```

Implementation:

```text
per-video timestamps sorted
binary search
```

Không cần AI.

---

# 19. Khi target +3s không có custom keyframe

Ví dụ anchor:

```text
14.2s
```

User muốn xem:

```text
+3s → 17.2s
```

Custom keyframes có thể chỉ có:

```text
16.4s
18.1s
```

Hệ thống có hai lựa chọn rõ ràng:

```text
NEAREST KEYFRAME
→ 18.1s
```

hoặc:

```text
EXACT VIDEO FRAME
→ trích frame thật tại ~17.2s
```

UI không được giả rằng nearest keyframe = exact +3s frame.

---

# 20. Hai loại navigation phải tách trên UI

### Keyframe navigation

```text
Prev KF
Next KF
Nearest +3s KF
Nearest +10s KF
```

### Exact video navigation

```text
-10 frames
-3 frames
-1 frame
+1 frame
+3 frames
+10 frames

-10 sec
-3 sec
+3 sec
+10 sec
```

Hai khái niệm khác nhau.

---

# 21. Physical frame navigation

Nếu exact-frame mapping xác định FPS/time base:

```text
current frame_idx = F
```

thì:

```text
+3 frames = F + 3
+10 frames = F + 10
```

Backend resolve/trích chính xác frame.

Không tìm “keyframe id + 3”.

---

# 22. Time navigation

```text
current_timestamp + 3s
```

Backend seek/extract target time/frame.

Nếu CFR mapping đáng tin:

```text
frame ≈ round(time * fps)
```

Nhưng exact-frame authority nên dùng media resolver/time-base logic hiện có thay vì assume mọi video tuyệt đối CFR.

---

# 23. Source Video = exact-frame authority

Thứ tự trust:

```text
source video / decoded frame
        ↑
physical frame mapping
        ↑
keyframe metadata
        ↑
retrieval result
```

Competition candidate cuối phải quay về source video.

---

# 24. Click result behavior

Khi click thumbnail:

1. Resolve `video_id`.
2. Resolve timestamp/frame.
3. Open inspector.
4. Seek gần target.
5. Hiển thị exact-frame preview độc lập.
6. Hiển thị source lane/evidence.
7. Load neighborhood asynchronously.

Không block toàn UI chờ full video load.

---

# 25. Vấn đề video nặng và seek

Lo lắng của nhóm là hợp lý:

- browser có thể chưa buffer tới cuối;
- direct local/network video có thể seek chậm;
- MP4 indexing/codec/GOP ảnh hưởng random seek;
- Drive virtual filesystem có latency.

Giải pháp không phải “trích trước mọi frame”.

Giải pháp là media backend hỗ trợ random access có kiểm soát.

---

# 26. Tier 1 Media Serving

```text
Browser
  │
  ├── GET /media/{video}/stream  (HTTP Range)
  │
  ├── GET /media/{video}/info
  │
  ├── GET /media/{video}/frame/{frame_idx}
  │
  └── GET /media/{video}/preview?start=...&duration=...
```

HTTP Range cho phép browser yêu cầu phần byte cần thiết thay vì tải toàn bộ file.

Exact JPEG API dùng ffmpeg backend.

---

# 27. Không phụ thuộc browser video để xác minh exact frame

Browser `<video>` phù hợp playback/seek theo time.

Nhưng exact frame preview nên gọi backend:

```text
/frame/{frame_idx}
```

Lợi ích:

- deterministic;
- frame stepping;
- candidate capture;
- không lệ thuộc rounding của player time.

---

# 28. Neighborhood Strip

Khi result mở:

```text
-10s   -3s    anchor   +3s   +10s
[img]  [img]  [img]    [img] [img]
```

Có thể hiển thị:

- nearest existing keyframes ngay lập tức;
- exact-frame thumbnails load lazy nếu user yêu cầu.

---

# 29. Hybrid Neighborhood Strategy

Để tránh lag:

### Instant layer

Dùng keyframes đã có:

```text
nearest BTC/custom around target
```

### Exact layer

Khi user click:

```text
+3s exact
```

backend mới extract.

Đây là trade-off tốt giữa tốc độ và chính xác.

---

# 30. Exact-frame cache

Backend cache JPEG đã trích:

Key:

```text
video_id + frame_idx + extraction_version
```

Storage:

```text
cache/exact_frames/L21_V001/00000426.jpg
```

Có thể LRU/size-limited.

Không cần precompute toàn corpus.

---

# 31. Preview Clip Cache — Tier 2

Khi user muốn xem ±10s nhanh:

backend có thể tạo short proxy clip:

```text
anchor - 10s → anchor + 10s
```

Cache theo:

```text
video_id/start/end/profile
```

Ưu:

- playback tức thì sau lần đầu;
- không cần browser random-seek file lớn liên tục.

Nhược:

- encode cost;
- cache management.

Chỉ làm nếu Range streaming vẫn lag trong benchmark.

---

# 32. Low-res proxy video — Tier 2

Có thể pre-create lower-resolution proxy cho operator browsing.

Source original vẫn dùng exact frame.

```text
proxy → navigation
original → authority
```

Không bắt buộc nếu local/Range streaming đủ tốt.

---

# 33. GOP/keyframe seek issue

Video codec thường seek tới decoder keyframe trước target rồi decode forward.

Backend frame extraction phải chấp nhận trade-off:

- fast seek approximate;
- accurate decode exact.

For competition exact frame:

accuracy > preview speed.

Có thể expose:

```text
preview fast
exact accurate
```

---

# 34. Media Info contract

Backend `/info` nên trả:

```text
video_id
duration_ms
width
height
fps representation
time_base if known
frame_count if reliable
codec
source availability
exact_frame_supported
range_stream_supported
```

Không expose absolute sensitive/local path nếu không cần.

---

# 35. Timeline Markers

Inspector nên overlay markers:

```text
SigLIP hits
Qwen hits
OCR hits
ASR intervals
BTC CLIP hits
Sequence step hits
Pinned candidates
```

Mỗi lane có icon/badge riêng.

Operator thấy evidence concentration theo thời gian.

---

# 36. Timeline region shading

Nếu temporal regions tồn tại:

```text
R1 | R2 | R3 | R4
```

UI shade story/topic regions.

Click region → search within region.

Không blocker Phase 1.

---

# 37. Same-video result clustering

Một lane có thể trả 20 frames cùng video trong 2 giây.

UI grouping:

```text
cluster center
member count
span
best rank
```

Expand khi cần.

Raw results không xóa để evaluation.

---

# 38. Temporal cluster definition

Seed:

```text
same video
hits within <= 4 sec
cluster span <= 12 sec
```

Existing unified search đã có temporal merge concepts; thresholds phải benchmark.

Không cho transitive chaining tạo cluster quá dài.

---

# 39. Sequence search over clusters vs raw hits

Tier 1:

- cluster dense duplicate hits first;
- sequence matcher dùng representatives + best ranks.

Lợi ích:

- giảm combinations;
- tránh một shot chiếm beam.

Nhưng có option raw debug.

---

# 40. Full-chain ranking features

```text
step coverage
step ranks
step lane diversity
temporal gaps
total span
region consistency
query step confidence
```

Không cần learned model V1.

---

# 41. Partial-chain ranking

Ưu tiên:

1. nhiều consecutive steps hơn;
2. rank từng step tốt;
3. gaps hợp lý;
4. same region nếu query gợi ý continuity.

Ví dụ 3 steps:

```text
S1+S2 > S1 only
S2+S3 > S2 only
```

nhưng UI vẫn tách group.

---

# 42. Query A/B semantics khác nhau

Không dùng một composed query:

```text
"A then B"
```

làm duy nhất.

Có thể chạy composed query như additional clue, nhưng core sequence phải search A và B độc lập.

---

# 43. Sequence step lane selection

Mỗi step có:

```text
AUTO
SigLIP
Qwen
ASR
OCR
BTC CLIP
Mixed
```

User có thể override.

Ví dụ:

```text
S1 exact text → OCR
S2 visible action → Qwen+SigLIP
```

---

# 44. Sequence with topic/program pruning

Pruning áp dụng trước step retrieval nhưng phải chung scope hoặc carefully union.

SAFE:

```text
priority videos
+
global rescue hits per step
```

Không để Step A prune ra video trước khi Step B có cơ hội cứu.

---

# 45. Sequence rescue

Nếu không có full chain:

1. lấy top partial videos;
2. rerun missing step trong same videos với larger K/broader lanes;
3. expand time window;
4. optional global missing-step rescue.

Ví dụ:

```text
A matched in video X
B missing
```

→ search B within X ±120s around A.

Đây là targeted rescue hiệu quả.

---

# 46. Progressive sequence widening

Profile:

```text
Pass 1: max gap 30s
Pass 2: 60s
Pass 3: 120s
```

Chỉ widen nếu no full chain.

UI hiển thị gap used.

Không âm thầm widen rồi gọi kết quả “strict”.

---

# 47. Same-region constraint

Optional:

```text
same_region = true
```

Chỉ khi regions đáng tin.

Không default trước region evaluation.

---

# 48. Same-shot constraint

Có thể dùng khi query nói action liên tục rất gần.

Nhưng custom/BTC shot definitions có thể khác nguồn.

Cần source-specific shot provenance.

Tier 2.

---

# 49. Spatial + Temporal query

Ví dụ:

```text
A: man left of table
then
B: same man standing
```

Step A dùng Qwen relation.

Step B visual/action.

Identity `same man` khó hơn vì cần person re-identification.

Không nên claim support Tier 1 trừ khi có identity model.

Tier 3/explicitly unsupported initially.

---

# 50. “Same object/person” semantics

Tier 1 sequence chỉ đảm bảo:

```text
same video
correct order
semantic matches
```

Không đảm bảo entity persistence.

UI/Brain phải tránh diễn đạt “same person verified” nếu chưa có ReID.

---

# 51. Exact Frame Resolver input

Nên chấp nhận:

```text
video_id + frame_idx
```

hoặc:

```text
video_id + timestamp_ms + resolve_policy
```

Policy:

```text
NEAREST_PHYSICAL_FRAME
PTS_AWARE
CFR_FALLBACK
```

---

# 52. Exact Frame Resolver output

```json
{
  "video_id": "L21_V001",
  "requested_timestamp_ms": 17200,
  "resolved_frame_idx": 516,
  "resolved_pts_ms": 17200,
  "authority": "SOURCE_VIDEO",
  "method": "PTS_AWARE",
  "jpeg_url": "..."
}
```

Nếu fallback:

```text
method = CFR_FALLBACK
```

UI biết mức authority.

---

# 53. Nearest keyframe output

```json
{
  "space": "CUSTOM",
  "target_ms": 17200,
  "keyframe_id": "...",
  "timestamp_ms": 18100,
  "delta_ms": 900
}
```

Delta phải hiển thị.

Không giả nearest frame ở đúng target time.

---

# 54. Exact vs nearest UI

Ví dụ:

```text
Target: 00:17.200

Nearest custom KF: 00:18.100 (+0.900s)
Nearest BTC KF:    00:17.000 (-0.200s)
Exact source frame: 00:17.200
```

Operator chọn.

---

# 55. Keyboard frame stepping

Đề xuất:

```text
← / →         previous/next exact frame
Shift+←/→     ±10 exact frames
J / L         ±3 sec
Shift+J/L     ±10 sec
K             play/pause
```

Configurable.

Không conflict với browser shortcuts nếu có thể.

---

# 56. Keyframe stepping shortcuts

Separate:

```text
[ / ]         prev/next custom keyframe
Alt+[ / ]     prev/next BTC keyframe
```

Để operator biết đang duyệt sampled frames hay physical frames.

---

# 57. Frame card evidence

Khi click result, side panel:

```text
video_id
frame_idx
time
source space
lane/rank/score
Qwen objects/actions/scenes
OCR text nearby
ASR nearby
BTC objects nearby
```

Chỉ show evidence thực sự mapped.

Không synthesize “all evidence agrees” nếu không có.

---

# 58. ASR neighborhood

Cho target `t`:

```text
ASR overlapping t
previous segment
next segment
```

UI transcript highlight.

Useful để hiểu visual scene context.

---

# 59. OCR neighborhood

Cho target frame/time:

- OCR exact frame nếu mapped;
- OCR nearest sampled frame;
- nearby OCR track/frames.

Label source/time clearly.

---

# 60. Qwen neighborhood

Tương tự custom keyframes:

```text
previous Qwen frame
current nearest
next Qwen frame
```

Useful để infer action manually.

Không tự biến thành temporal inference Tier 1.

---

# 61. BTC object overlay

Nếu inspector đang hiển thị BTC keyframe:

- overlay bounding boxes;
- toggle labels/confidence.

Nếu exact source frame khác BTC keyframe, không copy bbox sang frame khác.

---

# 62. OCR bbox overlay

Nếu source OCR record maps exact keyframe image:

- draw bbox;
- show raw text/confidence.

Nếu showing exact frame at different timestamp:

- do not draw stale OCR bbox.

---

# 63. Result-to-video opening policy

Open at:

```text
max(0, hit_time - pre_roll)
```

Seed pre-roll:

```text
1–2 sec
```

Exact frame preview vẫn focus hit frame.

Playback pre-roll giúp thấy context.

---

# 64. Sequence playback policy

Full chain A→B:

```text
start = A - pre_roll
end   = B + post_roll
```

Nếu span quá dài:

- không auto-load whole clip;
- show jump buttons A/B;
- optional short preview snippets each anchor.

---

# 65. Preview generation strategy

Tier 1:

```text
keyframe thumbnails already exist
exact JPEG on-demand
source range stream on click
```

Tier 2:

```text
short mp4 proxy clips on-demand + cache
```

Không pre-extract every second for 873 videos nếu chưa chứng minh cần.

---

# 66. Thumbnail cache

Could cache:

```text
160px/320px webp/jpeg
```

for UI grid.

Do not force full-resolution keyframes in result cards.

This is derived/rebuildable.

---

# 67. Media errors

Statuses:

```text
VIDEO_NOT_FOUND
VIDEO_UNAVAILABLE
FRAME_OUT_OF_RANGE
EXTRACTION_FAILED
RANGE_UNSUPPORTED
PTS_MAPPING_FAILED
```

UI result vẫn giữ retrieval evidence ngay cả khi media preview failed.

---

# 68. Video duration guard

Before temporal request:

```text
0 <= target_ms <= duration_ms
```

Clamp only for navigation convenience; exact resolver should report if requested frame invalid.

---

# 69. Frame index guard

If frame count reliable:

```text
0 <= frame_idx < frame_count
```

If not, ffmpeg decode result is authority.

---

# 70. Concurrency

Operator may click results rapidly.

Frontend should:

- cancel obsolete preview requests;
- keep latest selected result authority;
- avoid queueing 20 ffmpeg extractions.

Backend:

- small bounded extraction worker pool;
- cache exact frames.

---

# 71. Prefetch policy

When result selected:

Prefetch only:

```text
current exact frame
nearest prev/next keyframe thumbnails
possibly ±1 exact frame
```

Do not prefetch ±10s all frames.

---

# 72. Source video path portability

Inspector gets `video_id`, not absolute Drive path.

Backend resolver:

```text
video_id
↓
source_relpath
↓
configured media root
```

Matches Data Hub contract.

---

# 73. Result provenance

Inspector header:

```text
Retrieved by: SigLIP2
Source frame space: CUSTOM
Index: siglip_custom_v1
Query variant: visual_original
Rank: 4
```

If fused:

```text
Support:
SigLIP rank 4
Qwen rank 8
BTC CLIP nearby rank 12
```

Explainability matters in Compare/failure analysis.

---

# 74. Candidate review states

```text
UNREVIEWED
LIKELY
REJECTED
CONFIRMED
```

State belongs session/evaluation workspace, not canonical frame data.

---

# 75. Candidate builder

When confirmed:

```text
video_id
frame_idx
timestamp
query_id
notes
```

KIS/QA/TRAKE-specific candidate constraints handled by existing product layer.

Exact-frame preview must precede submission confirmation.

---

# 76. Temporal Search Failure Taxonomy

```text
STEP_A_MISS
STEP_B_MISS
PARTIAL_ONLY
ORDER_VIOLATION
GAP_TOO_LARGE
SAME_VIDEO_MISS
KEYFRAME_SAMPLING_MISS
LANE_MISS
SEQUENCE_DECOMPOSITION_ERROR
TEMPORAL_CLUSTER_ERROR
SOURCE_FRAME_MAPPING_ERROR
```

Critical for benchmark.

---

# 77. Media Inspector Failure Taxonomy

```text
VIDEO_RESOLVE_ERROR
RANGE_STREAM_ERROR
SEEK_ERROR
EXACT_FRAME_ERROR
FRAME_TIME_MISMATCH
CACHE_ERROR
STALE_SELECTION
```

Separate from retrieval failure.

---

# 78. Sequence evaluation metrics

```text
Full-chain Recall@K
Video Recall@K
Partial-chain Recall
Correct-order rate
Gap-valid rate
First correct chain rank
Anchor rank
Latency
```

Do not evaluate sequence only by whether each step appears somewhere in Top-K independently.

---

# 79. Exact-frame evaluation

For known video/frame pairs:

```text
requested frame_idx
resolved frame_idx
pixel/source correctness spot-check
PTS delta
```

Media resolver regression tests mandatory.

---

# 80. Nearest-keyframe evaluation

Unit tests with sorted timestamps:

```text
nearest before
nearest after
nearest absolute
boundary at 0
boundary at duration
exact match
```

No AI needed; must be deterministic.

---

# 81. Tier 1 implementation scope

Build now:

1. BEFORE/AFTER 2-step manual mode.
2. Ordered 2–5 step manual sequence.
3. Same-video + strict-order.
4. Configurable max/min gap.
5. Full + partial result groups.
6. Anchor search within same video/time window.
7. Nearest BTC/custom keyframe service.
8. Exact-frame source resolver.
9. Result click → video seek.
10. ±3s/±10s navigation.
11. ±1/±3/±10 exact frame navigation.
12. Neighborhood keyframe strip.
13. Exact JPEG cache.
14. Timeline lane markers.
15. Sequence trace/failure taxonomy.

---

# 82. Tier 2

- Auto sequence decomposition from natural query.
- Progressive gap widening.
- On-demand short preview clips.
- Low-res proxy video if needed.
- Region-aware chain scoring.
- Learned/tuned temporal gap priors.
- OCR/Qwen temporal tracks.
- image-as-anchor search.
- sequence targeted rescue automation.

---

# 83. Tier 3

- person/object ReID across steps;
- learned end-to-end temporal VLM ranking;
- full clip embedding search;
- dense per-second video embedding corpus;
- online video understanding model for every query.

Không cần V1.

---

# 84. Performance design principle

Đừng tối ưu bằng cách precompute mọi frame.

Tối ưu bằng:

```text
candidate retrieval
→ sparse on-demand media access
→ caching
```

Search metadata/vector phải nhanh; expensive decode chỉ xảy ra ở vài candidate người dùng mở.

---

# 85. Competition workflow — single result

```text
Search
↓
Top frame
↓
click
↓
nearest keyframe instantly visible
↓
exact frame loads
↓
video seeks to hit
↓
operator ±frames / ±seconds
↓
confirm
```

---

# 86. Competition workflow — before/after

```text
Input A + B
↓
search each
↓
full pair rankings
↓
if good pair:
  play A→B span
else:
  inspect only-A top videos
  search B after anchor
↓
confirm exact frame
```

---

# 87. Competition workflow — “only before” rescue

```text
A found @ 05:40 in V123
B missing
↓
operator clicks A
↓
Search AFTER anchor
window +60/+120s
lanes: SigLIP + Qwen + BTC CLIP
↓
B candidate appears
```

This turns partial match into actionable workflow.

---

# 88. Competition workflow — no keyframe at target

```text
candidate event target = 17.2s
nearest custom = 18.1s
nearest BTC = 17.0s
↓
operator chooses exact
↓
backend extracts source frame at target/physical frame
↓
step ±1/±3 frames
```

No need pre-existing keyframe.

---

# 89. Data Hub dependencies

Required tables/services:

```text
videos
btc_keyframes
custom_keyframes
asr_segments
qwen_semantics
ocr observations
index row maps
nearest keyframe service
media resolver
```

Defined in `01_DATA_HUB_MAPPING.md`.

---

# 90. Query Brain dependency

Sequence Brain passes:

```text
steps[]
preferred lanes per step
constraints
scope
```

Temporal engine does not call LLM internally.

Defined in `02_QUERY_BRAIN_SEARCH_MODES.md`.

---

# 91. Search lane dependency

Each lane must support:

```text
candidate video scope
optional time range scope
Top-K
canonical hit output
```

Time-range filtering is particularly useful for anchor rescue.

---

# 92. API proposals

```text
POST /search/sequence
POST /search/around
GET  /media/{video_id}/info
GET  /media/{video_id}/stream
GET  /media/{video_id}/resolve-frame
GET  /media/{video_id}/frames/{frame_idx}
GET  /mapping/{video_id}/nearest-keyframes?time_ms=...
```

Exact route names can adapt to existing Phase 4 API.

---

# 93. Sequence response example

```json
{
  "full_matches": [
    {
      "video_id": "L26_V361",
      "steps": [
        {"step_id": "S1", "timestamp_ms": 252200},
        {"step_id": "S2", "timestamp_ms": 279000}
      ],
      "gaps_ms": [26800],
      "score": 0.91
    }
  ],
  "partial_matches": {
    "only_before": [],
    "only_after": []
  },
  "trace": {}
}
```

Score is internal ranking score, not probability unless calibrated later.

---

# 94. Acceptance Gate — Temporal Engine

PASS khi:

```text
[ ] 2-step order matching deterministic
[ ] 3–5 step beam/DP tested
[ ] same-video constraint works
[ ] min/max gap works
[ ] full and partial outputs both available
[ ] no transitive temporal chain bug
[ ] raw per-step hits preserved
[ ] lane-specific evidence preserved
[ ] anchor search works
[ ] targeted missing-step rescue possible
```

---

# 95. Acceptance Gate — Mapping

```text
[ ] BTC/custom frame spaces not confused
[ ] every result maps to valid video
[ ] nearest-keyframe returns correct delta
[ ] Qwen result uses custom frame identity
[ ] BTC CLIP result uses BTC frame identity
[ ] ASR interval maps to timeline correctly
```

---

# 96. Acceptance Gate — Media Inspector

```text
[ ] click result opens correct video
[ ] player seeks near correct timestamp
[ ] exact frame endpoint returns correct physical frame
[ ] ±1/±3/±10 frame stepping works
[ ] ±3s/±10s navigation works
[ ] source video path hidden/resolved safely
[ ] large-file seeking does not require whole-file download
[ ] stale async requests do not replace current selection
[ ] exact frame cache works
```

---

# 97. Acceptance Gate — Operator UX

```text
[ ] user understands keyframe vs exact frame
[ ] partial sequence result clearly labeled
[ ] time gap shown
[ ] lane evidence shown
[ ] nearest keyframe delta shown
[ ] one-click global/anchor rescue available
[ ] keyboard navigation usable
```

---

# 98. Những điều không được làm

Không:

```text
keyframe_id + 3 = frame +3
```

Không:

```text
nearest keyframe = exact timestamp
```

Không:

```text
BTC keyframe n == custom keyframe n
```

Không:

```text
browser currentTime = exact competition frame authority
```

Không:

```text
full chain absent → return nothing
```

Không:

```text
pre-extract every video frame before proving need
```

---

# 99. Quyết định chốt

1. **Sequence Search là mode chính thức, không experimental phụ.**
2. **A/B hoặc 2–5 steps được search độc lập rồi ghép theo timeline.**
3. **Same-video + strict order là core constraints.**
4. **Max gap configurable; 60s chỉ là default seed.**
5. **Full và partial matches đều phải xuất.**
6. **Anchor-based before/after refine là tính năng production.**
7. **Nearest keyframe và exact video frame là hai chức năng khác nhau.**
8. **Nếu frame target không có trong keyframe dataset, trích on-demand từ source video.**
9. **Không cần precompute mọi physical frame.**
10. **HTTP Range + exact-frame backend + cache là Tier 1 media strategy.**
11. **Preview proxy clip là Tier 2 nếu random seek thực tế còn chậm.**
12. **Source video luôn là exact-frame authority cuối.**

---

# 100. Definition of Done

```text
[ ] Manual BEFORE/AFTER usable
[ ] Manual 2–5 step Sequence usable
[ ] mixed modality steps usable
[ ] partial matches usable for rescue
[ ] result timeline grouped by video
[ ] anchor search works
[ ] nearest BTC/custom keyframes works
[ ] exact frame extraction works
[ ] video seek works without whole-file preload
[ ] ±seconds and ±physical-frame controls work
[ ] evidence/timeline overlay works
[ ] temporal failures measurable
[ ] exact-frame tests PASS
```

Khi hoàn thành, hệ thống không chỉ “tìm Top-K frame”, mà trở thành một **temporal evidence workstation**: tìm một cảnh, tìm cảnh trước/sau nó, dò chuỗi sự kiện, mở đúng video tại đúng mốc, rồi xác minh frame vật lý từ nguồn gốc.
