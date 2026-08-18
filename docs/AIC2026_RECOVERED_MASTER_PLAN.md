# AIC 2026: Bản Kế Hoạch Kiến Trúc & Remake Tổng Thể (Master Architecture Plan)

> **Triết lý cốt lõi**: *"Independent Evidence, Shared Identity, Late Fusion"*  
> **Phiên bản**: V2.0 Clean Recovered Master  
> **Trạng thái**: Authoritative Implementation Blueprint  
> **Phạm vi**: Toàn bộ 873 video giải đấu AIC 2026, tích hợp Visual, Whisper ASR, Qwen VLM, Scene OCR, SQLite Data Hub và React UI.

---

## 1. BỐI CẢNH & NGUYÊN TẮC THIẾT KẾ CỐT LÕI

Hệ thống truy xuất video AIC 2026 được xây dựng để giải quyết bài toán tìm kiếm khung hình chính xác (Exact Physical Frame Resolution) trong các dạng bài thi: **KIS (Known Item Search)**, **QA (Question Answering)** và **TRAKE (Temporal Action/Event Retrieval)**.

### 3 Nguyên Tắc Vàng (Core Pillars):
1. **Independent Evidence (Bằng chứng độc lập)**: Mỗi phương thức dữ liệu (Visual CLIP, Lời thoại ASR, Chữ màn hình OCR, Mô tả Qwen Caption) phải được truy xuất qua một **Làn độc lập (Isolated Retrieval Lane)**. Điều này giúp hệ thống biết chính xác từng nguồn đóng góp bao nhiêu điểm và nguồn nào bị fail khi debug.
2. **Shared Identity (Định danh khóa chung)**: Tất cả mọi phân mảnh dữ liệu (từ câu thoại, hộp chữ OCR, vector nhúng đến ảnh keyframe) đều quy về một khóa định danh duy nhất:
   $$\text{Key} = (\text{video\_id}, \text{frame\_idx})$$
3. **Late Fusion (Hợp nhất muộn bằng RRF)**: Không cố nén toàn bộ câu hỏi phức tạp vào 1 vector duy nhất. Sau khi các làn độc lập trả về danh sách ứng viên (ranked lists), hệ thống dùng **Reciprocal Rank Fusion (RRF)** để dung hợp thứ hạng:
   $$\text{RRF\_Score}(d) = \sum_{m \in \text{Lanes}} \frac{w_m}{k + \text{Rank}_m(d)} \quad (k = 60)$$

---

## 2. BẢN ĐỒ DỮ LIỆU TẬP TRUNG (MASTER DATA ASSETS)

Toàn bộ hệ thống kế thừa kho dữ liệu đã được kiểm toán sạch 100% (tham chiếu qua `DATA_REGISTRY`):

```text
KHO DỮ LIỆU TẬP TRUNG AIC 2026 (100% GROUND TRUTH)
├── 1. Corpus Video Authority:      873 video MP4 (G:\...\data_extracted\video)
├── 2. ASR Whisper Master:          107,540 câu thoại / 873 video (F:\...\asr_segments.jsonl)
├── 3. Custom Keyframes Space:      116,767 frames chất lượng cao (G:\...\output\keyframes)
├── 4. Qwen VLM Visual Captions:    116,587 bản ghi mô tả thị giác (G:\...\output_llm\shard_000.jsonl)
├── 5. BTC Keyframes & Map:         178,195 frames + 873 CSV ánh xạ (G:\...\data_extracted\map-keyframes)
├── 6. Media-Info YouTube Metadata: 873 file JSON title, tags, description (G:\...\media-info-aic25-b1.zip)
└── 7. Scene OCR Text Shards:       Embeddings .npy + Bounding Boxes JSON (ocr_single_text_retrieval)
```

---

## 3. KIẾN TRÚC TỔNG THỂ 4 TẦNG TINH GỌN (4-TIER TARGET ARCHITECTURE)

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                            TẦNG 4: OPERATOR WORKSPACE (UI)                          │
│   • SearchWorkspace.tsx: Tìm kiếm đa chế độ (Free / Structured / Hybrid / Timeline)  │
│   • Evidence Inspector: Hiển thị minh chứng điểm số từng làn (Visual, ASR, OCR, Cap) │
│   • Exact Physical Player: Giải mã frame vật lý chính xác 100%                       │
│   • Candidate Submission Builder: Xuất payload KIS / QA / TRAKE chuẩn thể lệ         │
└──────────────────────────────────────────▲───────────────────────────────────────────┘
                                           │ (HTTP REST / WebSocket: /api/v1/search)
┌──────────────────────────────────────────┴───────────────────────────────────────────┐
│                     TẦNG 3: QUERY BRAIN, PRUNING & LATE FUSION                       │
│   • Query Intent Classifier & Router: Nhận diện đề tài (Toán/Sử L25, Món ăn L26,     │
│     Thời sự L21/L22, Đua xe L23, Múa lân L24, Ký sự L28/L29, Chân dung L30).        │
│   • Late Fusion Engine: Xếp hạng dung hợp Reciprocal Rank Fusion (RRF, k=60).        │
│   • Temporal Windowing & Sequence Aggregator: Hỗ trợ truy vấn chuỗi thời gian TRAKE. │
└──────────────────────────────────────────▲───────────────────────────────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         │ (Visual Lane)                   │ (Audio Lane)                    │ (Text/OCR Lane)
┌────────┴────────────────────────┐ ┌──────┴─────────────────────────┐ ┌─────┴─────────────────────────┐
│     TẦNG 2: VISUAL PROVIDER     │ │      TẦNG 2: ASR PROVIDER      │ │    TẦNG 2: OCR & CAP PROVIDER   │
│ • Dense Similarity: CLIP ViT-32 │ │ • FTS5 BM25 trên 107.5k câu    │ │ • Trigram BM25 trên Scene OCR  │
│ • FAISS Index: IndexFlatIP      │ │   thoại Whisper Master         │ │ • FTS5 trên 116.5k Qwen Caps   │
│ • Vector cache: (116.7k x 512)  │ │ • Filter theo time range [a,b] │ │ • YouTube Metadata Tags        │
└────────▲────────────────────────┘ └──────▲─────────────────────────┘ └─────▲─────────────────────────┘
         │                                 │                                 │
┌────────┴─────────────────────────────────┴─────────────────────────────────┴─────────────────────────┐
│                        TẦNG 1: UNIFIED DATA HUB (SQLite + FAISS)                              │
│   • aic2026_data_hub.db (SQLite FTS5 Single-Source-of-Truth):                                 │
│     - Bảng `videos`: video_id, duration_sec, series_id, title, author, description, tags.   │
│     - Bảng `keyframes`: keyframe_id, video_id, frame_idx, pts_time, laplacian_score.         │
│     - Bảng `asr_segments` (FTS5): segment_id, video_id, start_sec, end_sec, text.            │
│     - Bảng `qwen_captions` (FTS5): video_id, frame_idx, objects, attributes, actions, text.   │
│     - Bảng `ocr_boxes` (FTS5): box_id, video_id, frame_idx, bbox, text, score.                │
│   • FAISS Indices: `visual_clip.index` (Visual) + `text_dense.index` (OCR/Caption Embeddings) │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. CHI TIẾT CÁC LÀN TRUY XUẤT ĐỘC LẬP (RETRIEVAL LANES)

### 4.1. Visual Retrieval Lane (`VisualProvider`):
* **Mục tiêu**: Tìm kiếm các cảnh quay thông qua mô tả thị giác (bối cảnh, màu sắc, góc máy).
* **Công nghệ**: OpenAI CLIP **ViT-B/32** (hoặc SigLIP2) + Chỉ mục **FAISS `IndexFlatIP`** (Inner Product / Cosine Similarity).
* **Dữ liệu nguồn**: 873 file vector `.npy` (512D float16).

### 4.2. Audio Voice Retrieval Lane (`AsrProvider`):
* **Mục tiêu**: Tìm kiếm câu nói của MC, lời giảng bài, phỏng vấn nhân chứng, lời thoại tiếng Việt.
* **Công nghệ**: **SQLite FTS5 Full-Text Search (BM25 Ranking)** kết hợp hỗ trợ tiếng Việt không dấu/có dấu.
* **Dữ liệu nguồn**: 107,540 câu thoại Whisper Medium đã gộp chuẩn từ 873 video.

### 4.3. Scene OCR Retrieval Lane (`OcrProvider`):
* **Mục tiêu**: Tìm kiếm các từ khóa hiển thị trên màn hình (bảng tên bác sĩ, biển số xe, dòng tin tức ticker, tên đường).
* **Công nghệ**: **Trigram FTS5 BM25** (cho phép tìm kiếm mờ Fuzzy matching để vượt qua lỗi sai chính tả) + Lọc ngưỡng `confidence >= 0.6`.
* **Dữ liệu nguồn**: `ocr_single_text_retrieval` (`metadata_shard_*.json` + `embeddings_shard_*.npy`).

### 4.4. Visual Caption & Metadata Lane (`CaptionProvider`):
* **Mục tiêu**: Tìm kiếm các hành động chi tiết và bối cảnh phức tạp mà CLIP có thể bỏ sót.
* **Công nghệ**: SQLite FTS5 trên tập mô tả sinh bởi mô hình ngôn ngữ thị giác Qwen VLM + YouTube Metadata.
* **Dữ liệu nguồn**: 116,587 bản ghi JSONL trong `output_llm/shard_000.jsonl`.

---

## 5. BỘ LỌC CHỦ ĐỀ & PHÂN TUYẾN SERIES (SERIES ROUTING & PRUNING)

Dựa trên kết quả kiểm toán 10 Series, hệ thống áp dụng bộ định tuyến thông minh (Query Intent Routing):

| Loại Query | Đặc trưng từ khóa | Series ưu tiên (Boosted) | Series loại trừ (Pruned) |
|---|---|---|---|
| **Giáo dục & Ôn thi** | `toán`, `lịch sử`, `địa lý`, `thầy giáo`, `bài giảng`, `đề thi` | **`L25`** | L26, L24 |
| **Ẩm thực & Nấu ăn** | `nấu`, `xào`, `kho`, `nguyên liệu`, `thịt bò`, `nước mắm` | **`L26`**, `L27` | L25, L23 |
| **Thể thao & Đua xe** | `đua xe đạp`, `vòng đua`, `áo vàng`, `nước rút`, `vận động viên`| **`L23`** | L26, L25 |
| **Lễ hội & Múa lân** | `múa lân`, `lân sư rồng`, `mai hoa thung`, `trống lân`, `tên anh đường`| **`L24`** | L21, L22 |
| **Bản tin Thời sự** | `dịch sởi`, `cháy rừng`, `tai nạn giao thông`, `thời tiết`, `công an` | **`L21`**, **`L22`** | L26, L25 |
| **Ký sự Sông nước** | `sông mê kông`, `đồng bằng sông cửu long`, `phù sa`, `rừng tràm` | **`L28`**, **`L29`** | L24, L26 |
| **Gương nhân ái** | `người tốt việc tốt`, `sửa xe miễn phí`, `lớp học tình thương` | **`L30`** | L23, L24 |

---

## 6. LỘ TRÌNH TRIỂN KHAI REMAKE (4 BƯỚC THỰC THI)

### 📌 Bước 1: Khởi Tạo Unified Data Hub (`src/aic2026/db/hub.py`)
* Xây dựng script `build_data_hub.py` tự động quét toàn bộ `DATA_REGISTRY` và nạp vào 1 file database duy nhất: `F:\AIC_WORK\aic2026_data_hub.db`.
* Tạo bảng FTS5 cho ASR (107.5k câu), Qwen (116.5k mô tả) và OCR.
* Xây dựng FAISS Vector Index nhị phân nạp nhanh trong 2 giây.

### 📌 Bước 2: Refactor 4 Retrieval Providers (`src/aic2026/retrieval/providers/`)
* Chuẩn hóa 4 module độc lập kế thừa từ `BaseProvider`:
  * `VisualProvider`: Query FAISS Index `visual_clip.index`.
  * `AsrProvider`: Query SQLite FTS5 table `asr_segments`.
  * `OcrProvider`: Query SQLite FTS5 table `ocr_boxes` (Trigram BM25).
  * `CaptionProvider`: Query SQLite FTS5 table `qwen_captions`.

### 📌 Bước 3: Hoàn Thiện Fusion Orchestrator & API Server
* Viết lại `retrieval/orchestrator.py`: Tiếp nhận 4 danh sách kết quả, áp dụng bộ lọc Series/Pruning và tính điểm RRF.
* Nối vào FastAPI Server (`search/api.py`) theo đúng chuẩn `openapi-retrieval-v1.yaml`.

### 📌 Bước 4: Kiểm Thử Tích Hợp Frontend & Chấm Điểm Benchmark
* Khởi động FastAPI server và Frontend React (`npm run dev`).
* Kiểm thử trực quan trên giao diện: Bấm tìm kiếm $\rightarrow$ Xem bảng điểm minh chứng 4 làn $\rightarrow$ Nhấp nhảy frame chính xác $\rightarrow$ Bấm xuất KIS / QA / TRAKE candidate.
* Chạy bộ đánh giá benchmark KIS/QA với 178 unit tests bảo vệ 100%.

---

## 7. KẾT LUẬN

Bản kế hoạch **AIC 2026 Recovered Master Plan** này hợp nhất toàn bộ trí tuệ, kinh nghiệm kiểm toán và các tài sản dữ liệu đắt giá nhất của dự án. Với kiến trúc **Unified Data Hub + 4 Làn Độc Lập + Late Fusion RRF**, hệ thống sẽ đạt tốc độ phản hồi dưới **500ms**, triệt tiêu toàn bộ lỗi sai lệch frame, và tối ưu hóa tối đa khả năng đạt điểm cao trong kỳ thi AIC 2026!
