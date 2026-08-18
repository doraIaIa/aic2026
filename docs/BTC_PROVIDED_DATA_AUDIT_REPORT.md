# Báo Cáo Audit Toàn Diện: Dữ Liệu Do Ban Tổ Chức (BTC) Cung Cấp (AIC 2026)

> **Mục tiêu**: Thống kê, giải mã cấu trúc và mô tả chi tiết toàn bộ các thành phần dữ liệu do Ban Tổ Chức cuộc thi AIC cung cấp (ngoại trừ file video MP4 thô).
> **Thời gian thực hiện**: 2026-08-17 | **Dữ liệu nguồn**: Thư mục `data/` và `data_extracted/` trên Drive dự án AIC 2026.

---

## 1. TỔNG QUAN HỆ THỐNG DỮ LIỆU PHI-VIDEO (EXCLUDING RAW VIDEOS)

Bên cạnh các file video thô (`.mp4`), Ban Tổ Chức cung cấp **5 gói dữ liệu phụ trợ chính thức** nhằm phục vụ việc trích xuất đặc trưng, ánh xạ mốc thời gian và nhận diện đa phương tiện:

| STT | Thành phần dữ liệu | Định dạng gốc | Số lượng file | Quy mô / Dung lượng | Vai trò cốt lõi trong hệ thống Tìm kiếm |
|---|---|---|---|---|---|
| **1** | **Keyframes** (Khung hình đại diện) | 14 file `.zip` $\rightarrow$ Thư mục ảnh `.jpg` | **873 thư mục** (~178,195 ảnh JPEG) | ~29.5 GB (Zip) / ~35 GB (Extracted) | Cung cấp hình ảnh trực quan đại diện cho từng phân cảnh, phục vụ duyệt kết quả và trích xuất Visual/OCR. |
| **2** | **Map-Keyframes** (Bảng ánh xạ frame) | `map-keyframes-aic25-b1.zip` $\rightarrow$ `.csv` | **873 file CSV** | 1.53 MB (Zip) / ~6.2 MB (Extracted) | Ánh xạ 1:1 giữa số thứ tự keyframe (`n`), mốc thời gian phát sóng (`pts_time`), tốc độ khung hình (`fps`) và frame vật lý (`frame_idx`). |
| **3** | **Media-Info** (Siêu dữ liệu YouTube) | `media-info-aic25-b1.zip` $\rightarrow$ `.json` | **873 file JSON** | 1.06 MB (Zip) / ~3.8 MB (Extracted) | Cung cấp tiêu đề gốc (`title`), mô tả chi tiết (`description`), từ khóa tác giả (`keywords`), kênh xuất bản (`author`), ngày đăng tải và URL gốc. |
| **4** | **Objects Detection** (Tọa độ vật thể) | `objects-aic25-b1.zip` $\rightarrow$ `.json` | **178,195 file JSON** | 610.46 MB (Zip) / ~1.8 GB (Extracted) | Bounding box và nhãn phân loại các đối tượng trực quan xuất hiện trên từng keyframe theo tập Open Images / COCO. |
| **5** | **CLIP Features 512D** (Vector thị giác) | `clip-features-32-aic25-b1.zip` $\rightarrow$ `.npy` | **873 file `.npy`** | 160.38 MB (Zip) / ~180 MB (Extracted) | Vector đặc trưng nhúng thị giác 512 chiều (trích xuất bởi mô hình OpenAI CLIP ViT-B/32) phục vụ tìm kiếm Zero-Shot Text-to-Image. |

---

## 2. CHI TIẾT THÀNH PHẦN 1: KEYFRAMES (ẢNH ĐẠI DIỆN)

### 2.1. Cấu trúc lưu trữ & Quy ước đặt tên (Naming Convention)
* **Quy mô**: 873 thư mục tương ứng 873 video, được nhóm theo 10 Series (`L21` $\rightarrow$ `L30`).
* **Định dạng file**: Ảnh màu JPEG (`.jpg`), độ phân giải chuẩn của video gốc (thường là 720p hoặc 1080p).
* **Quy ước đặt tên file ảnh**: `001.jpg`, `002.jpg`, `003.jpg`,..., `N.jpg` (đánh số thứ tự tăng dần 3 chữ số bắt đầu từ `001`).
* **Đường dẫn mẫu**: `data_extracted/keyframes/L21_V001/001.jpg`

### 2.2. Phân bố số lượng Keyframes theo 10 Series:
Các file zip gốc được BTC đóng gói theo từng Series:
1. `Keyframes_L21.zip` (1,380.06 MB)
2. `Keyframes_L22.zip` (1,640.99 MB)
3. `Keyframes_L23.zip` (482.77 MB)
4. `Keyframes_L24.zip` (1,646.82 MB)
5. `Keyframes_L25.zip` (5,810.28 MB)
6. `Keyframes_L26_a.zip` $\rightarrow$ `Keyframes_L26_e.zip` (5 zip packages, tổng cộng ~11,577.44 MB)
7. `Keyframes_L27.zip` (1,040.51 MB)
8. `Keyframes_L28.zip` (2,064.65 MB)
9. `Keyframes_L29.zip` (2,393.38 MB)
10. `Keyframes_L30.zip` (1,346.10 MB)

---

## 3. CHI TIẾT THÀNH PHẦN 2: MAP-KEYFRAMES (BẢNG ÁNH XẠ MỐC THỜI GIAN)

### 3.1. Cấu trúc Schema & Ý nghĩa các trường dữ liệu
Gói `map-keyframes-aic25-b1.zip` cung cấp 873 file CSV (ví dụ: `L21_V001.csv`). Mỗi dòng tương ứng với 1 keyframe trong thư mục ảnh:

| Tên cột | Kiểu dữ liệu | Ý nghĩa kỹ thuật | Ví dụ giá trị |
|---|---|---|---|
| `n` | `int` | Số thứ tự của keyframe (1-based index, khớp với tên file `001.jpg` $\rightarrow$ `n = 1`). | `1`, `2`, `3` |
| `pts_time` | `float` | Mốc thời gian phát sóng (Presentation Timestamp) tính bằng giây kể từ đầu video. | `0.0`, `3.0`, `10.0` |
| `fps` | `float` | Tốc độ khung hình (Frames Per Second) của video gốc. | `30.0` hoặc `25.0` |
| `frame_idx` | `int` | Chỉ số khung hình vật lý chính xác trong luồng video MP4 gốc. | `0`, `90`, `300` |

### 3.2. Công thức toán học & Quan hệ dữ liệu:
$$\text{frame\_idx} = \text{round}(\text{pts\_time} \times \text{fps})$$
$$\text{Tên file ảnh} = f"{n:03d}.jpg"$$

*Trích xuất thực tế từ file `L21_V002.csv`:*
```csv
n,pts_time,fps,frame_idx
1,0.0,30.0,0
2,3.0,30.0,90
3,10.0,30.0,300
4,13.0,30.0,390
```

---

## 4. CHI TIẾT THÀNH PHẦN 3: MEDIA-INFO (METADATA GỐC TỪ YOUTUBE)

### 4.1. Cấu trúc Schema file JSON
Gói `media-info-aic25-b1.zip` chứa **873 file JSON** (ví dụ: `media-info/L21_V001.json`). Cung cấp toàn bộ thông tin ngữ cảnh xuất bản gốc:

| Tên trường (Key) | Kiểu dữ liệu | Mô tả chi tiết |
|---|---|---|
| `title` | `string` | Tiêu đề gốc của video khi đăng tải trên YouTube (chứa số ngày, tên chương trình, chủ đề). |
| `description` | `string` | Toàn văn mô tả video (thường chứa tóm tắt mục lục bản tin, thông tin bản quyền, danh sách tiết mục). |
| `keywords` | `list[str]` | Mảng các thẻ từ khóa (tags) do đơn vị sản xuất gắn cho video (rất giàu thông tin ngữ nghĩa). |
| `author` | `string` | Tên kênh / Đài truyền hình phát hành (ví dụ: *60 Giây Official*, *Món Ngon Mỗi Ngày*, *Báo Thanh Niên*). |
| `channel_id` | `string` | Mã định danh kênh YouTube (Channel ID). |
| `channel_url` | `string` | Đường dẫn URL chính thức tới kênh YouTube phát hành. |
| `length` | `int` | Tổng thời lượng thực tế của video tính bằng giây. |
| `publish_date` | `string` | Ngày phát hành video định dạng `DD/MM/YYYY` (ví dụ: `01/08/2024`). |
| `watch_url` | `string` | Đường link YouTube trực tiếp để xem video gốc trực tuyến. |
| `thumbnail_url` | `string` | Đường dẫn ảnh thumbnail chất lượng cao đại diện trên YouTube. |

*Mẫu trích xuất thực tế từ `L21_V001.json`:*
```json
{
  "author": "60 Giây Official",
  "channel_id": "UCRjzfa1E0gA50lvDQipbDMg",
  "channel_url": "https://www.youtube.com/channel/UCRjzfa1E0gA50lvDQipbDMg",
  "title": "60 Giây Sáng - Ngày 01/08/2024 - HTV Tin Tức Mới Nhất 2024",
  "description": "60 Giây Sáng - Ngày 01/08/2024 - HTV Tin Tức Mới Nhất 2024\n► Đăng ký KÊNH để xem Tin Tức Mới Nhất...",
  "keywords": ["HTV Tin tức", "chuong trinh 60 giay", "thoi su", "60s hom nay", "Tin tuc 60 giay"],
  "length": 1262,
  "publish_date": "01/08/2024",
  "watch_url": "https://youtube.com/watch?v=Rzpw5WR7nAY",
  "thumbnail_url": "https://i.ytimg.com/vi/Rzpw5WR7nAY/sddefault.jpg"
}
```

---

## 5. CHI TIẾT THÀNH PHẦN 4: OBJECTS DETECTION (NHẬN DIỆN ĐỐI TƯỢNG TRỰC QUAN)

### 5.1. Cấu trúc lưu trữ
* **Quy mô**: **178,195 file JSON**, tổ chức theo từng thư mục video: `objects/Lxx_Vxxx/001.json`, `002.json`,...
* **Nguyên tắc ánh xạ**: Mỗi file `001.json` chứa thông tin bounding box của đúng keyframe `001.jpg` tương ứng.

### 5.2. Cấu trúc Schema trong từng file JSON:
* `detection_boxes`: Mảng các tọa độ bounding box theo chuẩn normalized `[ymin, xmin, ymax, xmax]` nằm trong khoảng `[0.0, 1.0]`.
* `detection_scores`: Mảng điểm tin cậy dự đoán (Confidence Score, float từ `0.0` đến `1.0`).
* `detection_class_names`: Tên lớp đối tượng bằng tiếng Anh (ví dụ: `Person`, `Car`, `Building`, `Tree`, `Food`, `Chair`, `Glasses`,...).
* `detection_class_entities`: Mã định danh thực thể Ontology (ví dụ: `/m/01g317`).
* `detection_class_labels`: Mã nhãn số nguyên (Integer Class ID).

*Mẫu trích xuất từ `objects/L26_V361/155.json`:*
```json
{
  "detection_class_names": ["Food", "Tableware", "Bowl", "Person", "Plate"],
  "detection_scores": ["0.981", "0.930", "0.881", "0.726", "0.313"],
  "detection_boxes": [
    [0.452, 0.312, 0.891, 0.745],
    [0.410, 0.250, 0.950, 0.810]
  ]
}
```

---

## 6. CHI TIẾT THÀNH PHẦN 5: CLIP FEATURES 512D (VECTOR ĐẶC TRƯNG THỊ GIÁC)

### 6.1. Định dạng kỹ thuật:
* **Quy mô**: **873 file NumPy `.npy`** (ví dụ: `clip-features-32/L21_V001.npy`).
* **Kiến trúc mô hình**: OpenAI CLIP **ViT-B/32** (Vision Transformer Base, Patch 32).
* **Kích thước ma trận (Shape)**: `(N, 512)` trong đó:
  * `N`: Đúng bằng số lượng keyframe của video đó.
  * `512`: Số chiều không gian vector nhúng (Embedding Dimension).
* **Kiểu dữ liệu (dtype)**: `float16` (Half Precision để tối ưu bộ nhớ).

### 6.2. Ứng dụng trong hệ thống Search:
* Vector này được nạp vào chỉ mục **FAISS (IndexFlatIP / IndexHNSW)** để tính toán độ tương đồng Cosine Similarity với Text Query đã được mã hóa bằng CLIP Text Encoder `ViT-B/32`.

---

## 7. BẢNG TỔNG KẾT ÁNH XẠ DỮ LIỆU BTC CHO 1 KEYFRAME ĐIỂN HÌNH

Để hình dung tính liên kết hoàn chỉnh, xét keyframe thứ **`n = 1`** của video **`L21_V001`**:

```text
[Video Gốc L21_V001]
       │
       ├── (1) Ảnh Keyframe:           data_extracted/keyframes/L21_V001/001.jpg
       ├── (2) Mốc Thời Gian (CSV):     pts_time = 0.0s, fps = 30.0, frame_idx = 0
       ├── (3) Siêu dữ liệu (JSON):     title = "60 Giây Sáng...", author = "60 Giây Official"
       ├── (4) Vật thể nhận diện (JSON): objects/L21_V001/001.json (Boxes: Person, Microphone, Suit...)
       └── (5) Vector nhúng (NPY):      Vector hàng 0 trong L21_V001.npy (512 chiều float16)
```

---

## 8. KẾT LUẬN & ĐÁNH GIÁ TÍNH ĐẦY ĐỦ

1. **Tính Toàn Vẹn**: Toàn bộ **873 video** đều có đầy đủ 100% các thành phần Keyframes, Map-Keyframes, Media-Info và CLIP-Features-32.
2. **Khả năng Mở Rộng**: Dữ liệu do BTC cung cấp đã chuẩn bị sẵn sàng toàn bộ hạ tầng thị giác (Visual + Objects) và ngữ cảnh xuất bản (YouTube metadata). Kết hợp với dữ liệu **Whisper ASR (107,540 câu thoại)** và **OCR Corpus V1 (138,791 frame)** mà chúng ta đã chuẩn hóa, hệ thống AIC 2026 đã sở hữu đầy đủ mọi chiều dữ liệu đa phương thức (Multimodal Fusion).
