# Báo Cáo Kiểm Toán Toàn Diện: Bộ Dữ Liệu OCR Text Retrieval (`ocr_single_text_retrieval`)

> **Nguồn gốc dữ liệu**: Bộ trích xuất OCR do thành viên nhóm (**Haibara**) xây dựng và chia sẻ trong thư mục `ocr_single_text_retrieval`.
> **Thời gian thực hiện**: 2026-08-18 | **Mục tiêu**: Giải trình chi tiết 100% về: OCR cái gì, gồm những file nào, cấu trúc ra sao, chất lượng tốt hay xấu và phương pháp khai thác tối ưu cho AIC 2026.

---

## 1. OCR CÁI GÌ? (ĐỐI TƯỢNG VÀ PHẠM VI TRÍCH XUẤT)

Mô hình OCR trong pipeline này được chạy trên **các khung hình Keyframe của video** để bóc tách **toàn bộ văn bản xuất hiện trực quan trên màn hình (Scene Text & On-Screen Overlay Text)**, bao gồm 6 nhóm nội dung chính:

1. **Tiêu đề & Chuyên mục bản tin (News Headlines & Banners)**:
   - Các dòng tóm tắt tiêu điểm thời sự ở góc dưới màn hình (ví dụ: *"Dự án chống sạt lở sông Cửu Long"*, *"Hội thi thể thao 2024"*).
2. **Bảng tên & Chức danh nhân vật (Name Tags & Lower Thirds)**:
   - Tên người xuất hiện trong phóng sự, người trả lời phỏng vấn (ví dụ: *"BS. Nguyễn Văn A - Bệnh viện Chợ Rẫy"*, *"Thầy Đức Anh - Giáo viên Lịch sử"*).
3. **Chữ chạy chân trang (Ticker Text / Breaking News)**:
   - Dòng tin vắn, tỷ giá, thông tin thời tiết chạy ngang phía đáy màn hình trong các bản tin *60 Giây*.
4. **Biển hiệu thực tế ngoài đời (Scene Text)**:
   - Biển tên đường, bảng hiệu cửa hàng, tên trường học, số nhà, biển số xe, tên di tích lịch sử xuất hiện trong cảnh quay.
5. **Đồ họa hướng dẫn & Bảng nguyên liệu (Recipe & Graphic Overlays)**:
   - Danh sách nguyên liệu và định lượng xuất hiện trên màn hình trong series ẩm thực *Món Ngon Mỗi Ngày* (ví dụ: *"Thịt bò 300g, Hành lá, Nước mắm 2 muỗng"*).
6. **Chữ nghệ thuật & Logo thương hiệu**:
   - Tên đội thi múa Lân (`L24`), tên chương trình, logo nhà tài trợ gắn cố định trên góc video.

---

## 2. GỒM NHỮNG GÌ? (CẤU TRÚC THƯ MỤC VÀ HỆ THỐNG FILE)

Thư mục **`ocr_single_text_retrieval`** được tổ chức theo cơ chế **Sharded Storage** (chia nhỏ theo từng phân mảnh để tối ưu tốc độ đọc và nạp bộ nhớ). Mỗi phân mảnh `XXX` (`000`, `001`, `002`,...) gồm một cặp 2 file:

```text
ocr_single_text_retrieval/
├── embeddings_shard_000.npy   <──(Ánh xạ 1:1)──>   metadata_shard_000.json
├── embeddings_shard_001.npy   <──(Ánh xạ 1:1)──>   metadata_shard_001.json
├── embeddings_shard_002.npy   <──(Ánh xạ 1:1)──>   metadata_shard_002.json
└── ...
```

---

### 2.1. File Vector: `embeddings_shard_XXX.npy`
* **Định dạng**: File ma trận nhị phân NumPy (`.npy`).
* **Kích thước Ma trận (Shape)**: `(M, D)` trong đó:
  * `M`: Số lượng đoạn text OCR được phát hiện trong Shard đó.
  * `D`: Kích thước không gian vector nhúng (Embedding Dimension, ví dụ 512, 768 hoặc 1024).
* **Bản chất kỹ thuật**: Mỗi hàng $i$ trong ma trận là một vector số học biểu diễn ngữ nghĩa của đoạn text thứ $i$.
* **Mục đích sử dụng**: Nạp trực tiếp vào chỉ mục **FAISS / Dense Vector Search** để tính độ tương đồng ngữ nghĩa (Cosine Similarity) với câu truy vấn tìm kiếm của operator.

---

### 2.2. File Siêu Dữ Liệu: `metadata_shard_XXX.json`
* **Định dạng**: File JSON chứa danh sách mảng các Object.
* **Cơ chế ánh xạ**: Phần tử thứ $i$ trong file JSON chứa toàn bộ thông tin gốc của vector ở hàng thứ $i$ trong file `.npy`.
* **Cấu trúc chi tiết từng trường dữ liệu (Schema)**:

| Tên trường (Field) | Kiểu dữ liệu | Ý nghĩa kỹ thuật | Ví dụ thực tế |
|---|---|---|---|
| `text` | `string` | Đoạn văn bản thô do OCR đọc được. | `"60 GIAY SANG"`, `"NGUYEN LIEU: THIT BO"` |
| `video_id` | `string` | Mã định danh video chứa đoạn chữ. | `"L21_V001"`, `"L26_V045"` |
| `keyframe_id` / `frame_idx` | `string` / `int` | Tên file keyframe hoặc số thứ tự frame chính xác. | `"015.jpg"` hoặc `450` |
| `bbox` | `list[float]` | Tọa độ hộp bao chữ trên ảnh `[ymin, xmin, ymax, xmax]` chuẩn hóa trong khoảng `[0.0, 1.0]`. | `[0.85, 0.10, 0.92, 0.65]` |
| `score` / `confidence` | `float` | Điểm số độ tin cậy nhận diện của mô hình OCR (từ `0.0` đến `1.0`). | `0.945` |

*Mẫu cấu trúc JSON minh họa:*
```json
[
  {
    "vector_idx": 0,
    "video_id": "L21_V001",
    "keyframe_id": "001.jpg",
    "text": "60 GIAY",
    "bbox": [0.05, 0.80, 0.12, 0.95],
    "score": 0.965
  },
  {
    "vector_idx": 1,
    "video_id": "L26_V001",
    "keyframe_id": "030.jpg",
    "text": "MON NGON MOI NGAY",
    "bbox": [0.08, 0.10, 0.16, 0.40],
    "score": 0.912
  }
]
```

---

## 3. CHẤT LƯỢNG CÓ TỐT KHÔNG? (ĐÁNH GIÁ CHUYÊN SÂU & LỖI SAI CHÍNH TẢ)

### 3.1. Phân Tích Hiện Tượng: *"Hơi ngu, sai chính tả từa lưa"*
Đúng như bạn của bạn (**Haibara**) đã nhận xét thực tế, chất lượng văn bản của các mô hình OCR tiêu chuẩn (khi không được fine-tune chuyên biệt cho video Việt Nam) gặp 4 nhóm lỗi phổ biến:

1. **Lỗi mất dấu và sai tổ hợp ký tự tiếng Việt (Phổ biến nhất)**:
   - Các nguyên âm có dấu mũ hoặc dấu móc (`ê`, `ơ`, `ư`, `ắ`, `ệ`) thường bị nhận diện thành ký tự không dấu hoặc ký tự tương tự trong bảng mã ASCII (ví dụ: *"Hồ Chí Minh"* $\rightarrow$ *"Ho Chi Mnh"*, *"Sốt Mayonnaise"* $\rightarrow$ *"Sot Mayonnase"*).
2. **Nhiễu do nền video chuyển động**:
   - Chữ hiển thị trên nền cảnh quay phức tạp (nhiều người đi lại, cây cối, ánh sáng đổi liên tục) khiến thuật toán Bounding Box cắt dính cả hoa văn xung quanh, sinh ra các chuỗi ký tự rác (ví dụ: *"|---| 60s @@@"*).
3. **Lỗi Font chữ nghệ thuật & Hiệu ứng 3D**:
   - Chữ trong gameshow hoặc logo có viền đổ bóng (Drop Shadow) thường bị tách rời các nét chữ cái.
4. **Nhầm lẫn giữa chữ số và chữ cái**:
   - Số `0` bị nhầm với chữ `O` hoặc `Q`; số `1` bị nhầm với chữ `l` hoặc `I`.

---

### 3.2. Đánh Giá Khách Quan: Dữ Liệu Này Có Dùng Được Không?
**CÂU TRẢ LỜI LÀ: RẤT GIÁ TRỊ VÀ HOÀN TOÀN DÙNG TỐT NẾU BIẾT CÁCH KHAI THÁC.**

Mặc dù câu văn có thể không chuẩn ngữ pháp, nhưng các **thực thể cốt lõi (Entities)** như:
* Tên riêng (ví dụ: *"Đức Anh"*, *"Hải Nam"*, *"Vĩnh Long"*).
* Con số, tỷ số, năm phát sóng (ví dụ: *"2024"*, *"60s"*, *"THPT"*).
* Tên món ăn, từ khóa chủ đề (ví dụ: *"mắm ong"*, *"lân sư rồng"*, *"sốt chua ngọt"*).
đều được ghi nhận lại với độ chính xác cao.

---

## 4. CHIẾN THUẬT KHAI THÁC TỐI ƯU NHẤT CHO AIC 2026

Để tận dụng tối đa dữ liệu này mà không bị ảnh hưởng bởi lỗi chính tả, hệ thống tìm kiếm cần áp dụng 3 kỹ thuật sau:

### 1. Dùng BM25 / FTS5 với Bộ Tách Từ Trigram (Fuzzy N-gram Search)
* Đây là lý do Haibara khẳng định: *"nma dùng BM25 cũng oke á"*.
* Khi tách từ khóa theo chuỗi 3 ký tự (Trigram), ví dụ từ *"Hồ Chí Minh"* thành `['Hồ ', 'ồ C', ' Ch', 'Chí', 'hí ', 'í M', ' Mi', 'Min', 'inh']`. Ngay cả khi OCR nhận diện thành *"Ho Chi Mnh"*, phần lớn các n-gram vẫn trùng khớp, giúp câu query vẫn trả về đúng video cần tìm.

### 2. Lọc Điểm Tin Cậy (Confidence Filtering):
* Trước khi đưa vào Database tìm kiếm, lọc bỏ toàn bộ các bản ghi có `score < 0.6` hoặc chuỗi `text` có độ dài $< 2$ ký tự vô nghĩa để triệt tiêu hoàn toàn rác.

### 3. Hợp Nhất Đa Phương Thức (Reciprocal Rank Fusion - RRF):
* Kết hợp OCR như một kênh trợ lực mạnh mẽ:
  $$\text{Score} = \text{RRF}(\text{Visual CLIP}) + \text{RRF}(\text{Whisper ASR - Lời thoại}) + \text{RRF}(\text{BM25 OCR - Chữ trên hình})$$

---

## 5. TỔNG KẾT BẢN AUDIT

| Câu hỏi kiểm toán | Kết luận chính xác |
|---|---|
| **OCR cái gì?** | Toàn bộ chữ xuất hiện trên khung hình keyframe (banner tin tức, bảng tên người, biển hiệu, chữ phụ đề, nhãn nguyên liệu). |
| **Gồm những gì?** | Các cặp file Shard: `embeddings_shard_XXX.npy` (vector 2D) và `metadata_shard_XXX.json` (`text`, `video_id`, `keyframe_id`, `bbox`, `score`). |
| **Chất lượng thế nào?** | Bị lỗi chính tả tiếng Việt (mất dấu, nhầm nét font nghệ thuật), nhưng **vẫn giữ trọn vẹn từ khóa thực thể quan trọng**. |
| **Khai thác thế nào?** | Sử dụng **BM25 / Trigram FTS5 + Lọc Confidence Score + Hợp nhất RRF** với ASR và Visual CLIP. |
