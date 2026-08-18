# Master Data Paths Registry: Bản Đồ Nguồn Dữ Liệu AIC 2026

> **Tài liệu tham chiếu chuẩn (Single Source of Truth)** lưu trữ toàn bộ các đường dẫn dữ liệu quan trọng nhất trên Google Drive (`G:\...`) và Local Disk (`F:\...`) cho toàn bộ dự án AIC 2026.
> **Thời gian cập nhật**: 2026-08-18 | **Tập dữ liệu**: Đủ 100% (873 video, 107.5k câu thoại ASR, 116.7k Custom Keyframes, 178.2k BTC Keyframes).

---

## 1. CÁC THƯ MỤC GỐC CHÍNH (ROOT DIRECTORIES)

> **Cấu hình Git vs Local Runtime**:
> - `configs/data_paths.example.json`: File mẫu cấu hình chung portable được commit lên Git.
> - `configs/data_paths.json`: File cấu hình máy cục bộ thực tế chứa đường dẫn đĩa cá nhân (được `.gitignore` chặn, không commit lên Git).

| Tên định danh | Đường dẫn mẫu / Ví dụ thực tế | Vai trò |
|---|---|---|
| **`BTC_DRIVE_ROOT`** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026` | Gốc Google Drive chứa dữ liệu trích xuất của BTC và Custom Keyframes. |
| **`LOCAL_ARTIFACTS_ROOT`** | `F:\AIC_WORK\artifacts` | Gốc lưu trữ cục bộ các artifacts đã xử lý (ASR, OCR, Evaluation). |
| **`LOCAL_DEV_ROOT`** | `F:\AIC_DEV\aic2026` | Gốc mã nguồn backend và tests. |

---

## 2. NGUỒN DỮ LIỆU BAN TỔ CHỨC CUNG CẤP (BTC DATA - DRIVE)

| Thành phần dữ liệu | Đường dẫn tuyệt đối | Quy mô / Định dạng | Mục đích sử dụng |
|---|---|---|---|
| **Keyframes (Ảnh BTC)** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\data_extracted\keyframes` | 873 thư mục (~178,195 ảnh JPEG) | Ảnh đại diện phân cảnh chuẩn BTC. |
| **Map-Keyframes (CSV)** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\data_extracted\map-keyframes` | 873 file CSV (`n, pts_time, fps, frame_idx`) | Ánh xạ timestamp sang frame vật lý. |
| **CLIP Features (512D)** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\data_extracted\clip-features-32` | 873 file `.npy` (ViT-B/32, float16) | Nạp vào FAISS cho Visual Zero-shot Search. |
| **Objects Detection** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\data_extracted\objects` | 178,195 file JSON (`bbox, scores, classes`) | Bounding box đối tượng thị giác. |
| **Video MP4 Thô** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\data_extracted\video` | 873 file `.mp4` | Stream video và cắt frame vật lý. |
| **Media-Info (YouTube)** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\data\media-info-aic25-b1.zip` | 873 file JSON (`title, desc, tags, author`) | Metadata gốc từ YouTube. |

---

## 3. NGUỒN DỮ LIỆU CUSTOM & MÔ TẢ THỊ GIÁC (ENRICHED DATA - DRIVE)

| Thành phần dữ liệu | Đường dẫn tuyệt đối | Quy mô / Định dạng | Mục đích sử dụng |
|---|---|---|---|
| **Custom Keyframes** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\output\keyframes` | 873 thư mục (116,767 ảnh JPEG) | Keyframe chất lượng cao lọc mờ Laplacian. |
| **Custom Map Keyframes**| `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\output\map_keyframes` | 873 file CSV (kèm `laplacian_score, cluster_id`)| Ánh xạ keyframe custom. |
| **Qwen VLM Captions** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\output_llm\shard_000.jsonl` | 116,587 bản ghi (123 MB JSONL) | Mô tả chi tiết hành động, bối cảnh, vật thể cho FTS5. |
| **Video Metadata CSV** | `G:\.shortcut-targets-by-id\1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv\AIC_2026\output\video_metadata.csv` | 1 file CSV | Thống kê tổng hợp thời lượng, số frame. |

---

## 4. NGUỒN LỜI THOẠI ASR (WHISPER MASTER - LOCAL DISK)

| Thành phần dữ liệu | Đường dẫn tuyệt đối | Quy mô / Định dạng | Trạng thái |
|---|---|---|---|
| **Master ASR Segments** | `F:\AIC_WORK\artifacts\asr\whisper-medium-vi-full-v1-colab-merged\asr_segments.jsonl` | 107,540 câu thoại (`start_sec, end_sec, text`) | **100% Hoàn Tất** (Khớp cả 873 video). |
| **Master ASR Videos** | `F:\AIC_WORK\artifacts\asr\whisper-medium-vi-full-v1-colab-merged\asr_videos.jsonl` | 873 bản ghi video (`duration_sec, segment_count`) | **100% Hoàn Tất**. |
| **Backup Final Master** | `F:\AIC_WORK\artifacts\asr\whisper-medium-vi-full-873-final\` | Thư mục chứa 2 file JSONL hợp nhất chuẩn | Bản lưu trữ an toàn. |

---

## 5. NGUỒN NHẬN DIỆN CHỮ OCR (TEXT IN IMAGE)

| Thành phần dữ liệu | Đường dẫn tuyệt đối | Quy mô / Định dạng | Mục đích sử dụng |
|---|---|---|---|
| **OCR Corpus Manifest V1** | `F:\AIC_WORK\artifacts\ocr\ocr-corpus-v1\manifest.jsonl` | 138,791 selected frames (JSONL) | Manifest danh sách frame cần OCR. |
| **Team OCR Shards** | Thư mục `ocr_single_text_retrieval/` | `embeddings_shard_*.npy` + `metadata_shard_*.json` | Dense Vector + BM25 Scene Text. |

---

## 6. HƯỚNG DẪN TRUY CẬP TRONG MÃ NGUỒN PYTHON

Toàn bộ backend Python không cần phải hardcode đường dẫn mà chỉ cần import từ module `data_registry`:

```python
from aic2026.core.data_registry import DATA_REGISTRY

# 1. Truy cập file ASR Master
asr_file = DATA_REGISTRY.asr.master_segments_file

# 2. Truy cập Qwen Visual Captions
qwen_file = DATA_REGISTRY.custom.qwen_captions_shard

# 3. Truy cập thư mục Keyframes
kf_dir = DATA_REGISTRY.custom.keyframes_dir

# 4. Truy cập file Media-Info Zip
media_info = DATA_REGISTRY.btc.media_info_zip
```
