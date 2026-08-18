# Báo Cáo Audit Kỹ Thuật: Thư Mục OCR Text Retrieval (`ocr_single_text_retrieval`)

> **Nguồn thông tin**: Tài liệu trao đổi & kiến trúc trích xuất từ thành viên nhóm (Haibara).
> **Thời gian thực hiện**: 2026-08-18 | **Phạm vi**: Kiến trúc dữ liệu OCR, cấu trúc Shards, đặc tính chất lượng text và phương án tích hợp hệ thống AIC 2026.

---

## 1. TỔNG QUAN VỀ THƯ MỤC `ocr_single_text_retrieval`

Thư mục **`ocr_single_text_retrieval`** là bộ dữ liệu trích xuất chữ trong ảnh (Scene Text / On-Screen OCR) do thành viên nhóm (Haibara) xây dựng nhằm phục vụ bài toán **Text-to-Video Search** dựa trên chữ hiển thị trên màn hình (biển hiệu, tiêu đề bản tin, phụ đề, bảng tên nhân vật, địa danh).

### Kiến trúc phân tán theo Shards:
Bộ dữ liệu được chia nhỏ thành các cặp file Shard (`XXX = 000, 001, 002,...`) gồm:
1. `embeddings_shard_XXX.npy`: Chứa các vector đặc trưng ngữ nghĩa (Dense Embeddings) của từng đoạn OCR text.
2. `metadata_shard_XXX.json`: Chứa dữ liệu gốc (Raw Text, Video ID, Keyframe ID, Tọa độ Bounding Box và Điểm tin cậy OCR).

```text
ocr_single_text_retrieval/
├── embeddings_shard_000.npy   <──>   metadata_shard_000.json
├── embeddings_shard_001.npy   <──>   metadata_shard_001.json
├── embeddings_shard_002.npy   <──>   metadata_shard_002.json
└── ...
```

---

## 2. GIẢI MÃ CẤU TRÚC KỸ THUẬT TỪNG FILE

### 2.1. File Vector Nhúng: `embeddings_shard_XXX.npy`
* **Định dạng**: File ma trận nhị phân NumPy (`.npy`).
* **Cấu trúc Ma trận**: Ma trận 2 chiều `Shape: (M, D)` trong đó:
  * `M`: Số lượng đoạn text OCR được phát hiện trong shard đó.
  * `D`: Kích thước chiều của vector embedding (thường là 512, 768 hoặc 1024 chiều tùy thuộc vào Text Encoder như `text-embedding-3-small`, `bge-m3`, `sentence-transformers` hoặc `CLIP Text Encoder`).
* **Nguyên tắc ánh xạ**: Hàng thứ $i$ trong file `.npy` tương ứng chính xác $1:1$ với phần tử thứ $i$ trong file `metadata_shard_XXX.json`.
* **Mục đích sử dụng**: Nạp vào chỉ mục **FAISS / Cosine Similarity** để so khớp ngữ nghĩa vector giữa câu query của operator với các đoạn chữ OCR trong video.

---

### 2.2. File Siêu Dữ Liệu: `metadata_shard_XXX.json`
* **Định dạng**: File JSON chứa mảng các bản ghi (List of Objects).
* **Schema cấu trúc của từng bản ghi**:

| Trường dữ liệu (Field) | Kiểu dữ liệu | Ý nghĩa kỹ thuật | Ví dụ minh họa |
|---|---|---|---|
| `text` | `string` | Chuỗi văn bản thô do mô hình OCR nhận diện được. | `"60 GIAY SANG"`, `"TP. HO CHI MINH"` |
| `video_id` | `string` | Mã định danh video chứa khung hình. | `"L21_V001"` |
| `keyframe_id` / `frame_idx` | `string` / `int` | Tên keyframe hoặc chỉ số khung hình chính xác. | `"001.jpg"` hoặc `15` |
| `bbox` | `list[float]` | Tọa độ hộp bao chữ trên ảnh `[ymin, xmin, ymax, xmax]` hoặc `[x, y, w, h]`. | `[0.12, 0.45, 0.20, 0.85]` |
| `score` / `confidence` | `float` | Điểm số độ tin cậy của thuật toán OCR detector & recognizer (0.0 $\rightarrow$ 1.0). | `0.925` |

*Cấu trúc JSON mẫu mô phỏng:*
```json
[
  {
    "vector_idx": 0,
    "video_id": "L21_V001",
    "keyframe_id": "015.jpg",
    "pts_time": 0.5,
    "text": "60 GIAY",
    "bbox": [0.05, 0.80, 0.15, 0.95],
    "ocr_score": 0.942
  },
  {
    "vector_idx": 1,
    "video_id": "L21_V001",
    "keyframe_id": "120.jpg",
    "pts_time": 4.0,
    "text": "SUY THOAI KINH TE",
    "bbox": [0.85, 0.10, 0.92, 0.50],
    "ocr_score": 0.871
  }
]
```

---

## 3. ĐÁNH GIÁ CHẤT LƯỢNG TEXT & ĐẶC TÍNH "SAI CHÍNH TẢ"

### 3.1. Nguyên nhân gây sai chính tả trong OCR video tiếng Việt:
Theo ghi nhận từ thực tế của Haibara (*"text hơi ngu, sai chính tả từa lưa"*), các mô hình OCR tiêu chuẩn thường gặp các lỗi sau trên video truyền hình:
1. **Mất dấu tiếng Việt / Sai tổ hợp ký tự**: Nhầm lẫn các ký tự có dấu phức tạp như `ế`, `ề`, `ặ`, `ở` thành ký tự không dấu hoặc ký tự đặc biệt (`ê` $\rightarrow$ `e`, `đ` $\rightarrow$ `d`).
2. **Nhiễu nền đồ họa & Font nghệ thuật**: Chữ trên logo, banner tin tức động hoặc chữ chạy chân trang (ticker) thường bị dính nền hoặc biến dạng khi nén video.
3. **Nhầm lẫn số và chữ cái**: Nhầm `0` với `O`, `1` với `l`/`I`, `5` với `S`.

---

### 3.2. Chiến lược xử lý & Tối ưu hóa truy vấn:

Mặc dù text OCR có tỷ lệ lỗi chính tả, nhưng **vẫn mang giá trị định vị cực kỳ cao** nếu áp dụng đúng chiến thuật:

#### 1. Chiến thuật Sparse Search (BM25 / SQLite FTS5 với Trigram Tokenizer) - *Khuyên dùng*:
* Đúng như Haibara đã nhận định (*"nma dùng bm25 cũng oke á"*): Khi sử dụng BM25 kết hợp với bộ tách từ **N-gram / Trigram**, hệ thống có thể tìm kiếm xấp xỉ (Fuzzy matching) hiệu quả.
* Ví dụ: Query `"Hồ Chí Minh"` vẫn khớp tốt với text OCR bị lỗi `"Ho Chi Mnh"` nhờ trùng khớp phần lớn các trigram.

#### 2. Chiến thuật Lọc Điểm Tin Cậy (Confidence Thresholding):
* Lọc bỏ toàn bộ các bounding box có `ocr_score < 0.5` hoặc đoạn text có độ dài quá ngắn ($< 2$ ký tự vô nghĩa) để giảm thiểu nhiễu giả (false positives).

#### 3. Chiến thuật Hợp nhất Đa phương thức (Reciprocal Rank Fusion - RRF):
* Tuyệt đối không dùng OCR như nguồn độc lập duy nhất.
* Cần xếp hạng kết hợp:
  $$\text{Score}_{\text{Final}} = \text{RRF}(\text{Visual CLIP}) + \text{RRF}(\text{Whisper ASR}) + \text{RRF}(\text{BM25 OCR})$$

---

## 4. HƯỚNG DẪN ĐỒNG BỘ THƯ MỤC TỪ GOOGLE DRIVE

Nếu thư mục `ocr_single_text_retrieval` được Haibara chia sẻ qua Google Drive nhưng chưa xuất hiện trên máy cục bộ (`G:\`):

1. **Bước 1**: Mở Google Drive trên trình duyệt Web.
2. **Bước 2**: Vào mục **"Được chia sẻ với tôi" (Shared with me)**.
3. **Bước 3**: Tìm thư mục `ocr_single_text_retrieval`.
4. **Bước 4**: Nhấp chuột phải $\rightarrow$ Chọn **"Thêm lối tắt vào Drive" (Add shortcut to Drive)** $\rightarrow$ Chọn thư mục đích là `AIC_2026`.
5. **Bước 5**: Ứng dụng *Google Drive for Desktop* sẽ tự động đồng bộ thư mục này về đường dẫn:
   `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\ocr_single_text_retrieval\`

---

## 5. TỔNG KẾT

| Tiêu chí | Đánh giá |
|---|---|
| **Cấu trúc Shards** | Thiết kế chuẩn: Tách riêng `embeddings_shard.npy` (Dense Search) và `metadata_shard.json` (Text / Coordinates). |
| **Độ chính xác Text** | Có lỗi chính tả tiếng Việt, cần bù đắp bằng BM25 / Fuzzy Matching / Trigram FTS5. |
| **Khả năng tích hợp** | Hoàn toàn tương thích với kiến trúc Pipeline Fusion của AIC 2026. |
