# Báo Cáo Phục Hồi Dữ Liệu & Retrieval Provider Runtime (AIC 2026)

**Mã phiên phục hồi**: `rec_001`  
**Thời gian**: 2026-08-20  
**Trạng thái**: **THÀNH CÔNG TOÀN DIỆN (SUCCESS)**

---

## 1. Tóm Tắt Tổng Quan

Toàn bộ tài nguyên dữ liệu, cơ sở dữ liệu SQLite, 12 provider truy vấn và quy trình hiển thị khung hình preview / streaming video đã được phục hồi, cấu hình và xác minh đầy đủ:
- **Tập video 873 file**: 100% video (`873/873`) và 100% thư mục keyframe đã được kết nối từ Google Drive (`G:\.shortcut-targets-by-id\...`), đồng thời tận dụng bộ nhớ đệm SSD NVMe cục bộ (`F:\KTLT\data_extracted\video`) cho 39 video thuộc các series L21 & L22.
- **Giải mã chênh lệch 39 vs 37 video**: Thư mục cục bộ `F:\KTLT\data_extracted\video` thực tế chứa đúng 39 file MP4 hoàn chỉnh. Con số 37 trước đây xuất phát từ việc duyệt dải tuần tự `1..29` bỏ sót các video không liên tục (như `V030`, `V031`).
- **Cơ sở dữ liệu SQLite**: Kết nối thành công `mapping.sqlite` (1,045.54 MB, 66 bảng), phục hồi hoàn toàn các bảng FTS5 và siêu dữ liệu cho ASR, OCR, Qwen và Media.
- **12/12 Retrieval Providers**: 100% đạt trạng thái **HEALTHY** và trả về HTTP 200 kèm kết quả chính xác trong kiểm thử thực tế.
- **Chính sách Result Preview (Mục 24)**: Thực thi triệt để trên giao diện frontend, loại bỏ hoàn toàn hiện tượng khung hình đen / trắng vô nghĩa, hiển thị đúng badge mô tả cho từng loại evidence.
- **Độ tin cậy kiểm thử**: 
  - Backend: **406 passed, 2 skipped, 0 failed (100%)**
  - Frontend: **63 passed (14 test files), 0 lỗi TypeScript, build production sạch**.

---

## 2. Bảng Trạng Thái 12 Provider Lanes

| # | Provider Lane | Modality | CSDL / Artifact Nguồn | Trạng Thái Trước | Trạng Thái Sau | Kết Quả Smoke Test |
|---|---|---|---|---|---|---|
| 1 | `siglip_custom` | Visual | `siglip_custom_v1` (FAISS) | HEALTHY | **HEALTHY** | HTTP 200, 5 hits (CUSTOM keyframe) |
| 2 | `btc_clip` | Visual | `clip-faiss-btc-v1` (FAISS) | HEALTHY | **HEALTHY** | HTTP 200, 5 hits (BTC keyframe) |
| 3 | `asr_bm25` | Speech/ASR | `asr_fts` (mapping.sqlite) | DEGRADED | **HEALTHY** | HTTP 200, 5 hits (ASR Segment) |
| 4 | `asr_bge` | Speech/ASR | `asr_bge_v1` (FAISS) | HEALTHY | **HEALTHY** | HTTP 200, 5 hits (ASR Dense) |
| 5 | `ocr_bm25` | Text/OCR | `ocr_fts` (mapping.sqlite) | DEGRADED | **HEALTHY** | HTTP 200, 5 hits (OCR BBox) |
| 6 | `ocr_trigram` | Text/OCR | `ocr_trigram_v1` (FTS5) | DEGRADED | **HEALTHY** | HTTP 200, 5 hits (OCR Fuzzy) |
| 7 | `ocr_bge` | Text/OCR | `ocr_bge_v1` (FAISS) | DEGRADED | **HEALTHY** | HTTP 200, 5 hits (OCR Dense) |
| 8 | `media_bm25` | Metadata | `media_fts` (mapping.sqlite) | DEGRADED | **HEALTHY** | HTTP 200, 5 hits (Video Metadata) |
| 9 | `qwen_structured`| VLM/Objects | `qwen_frames` (mapping.sqlite) | HEALTHY | **HEALTHY** | HTTP 200, 5 hits (Object list) |
| 10 | `qwen_bm25` | VLM/Caption | `qwen_caption_fts` (mapping.sqlite) | DEGRADED | **HEALTHY** | HTTP 200, 5 hits (Caption lexical) |
| 11 | `qwen_bge` | VLM/Dense | `qwen_field_bge_large...` | HEALTHY | **HEALTHY** | HTTP 200, 5 hits (Caption dense) |
| 12 | `btc_objects` | Detector | `btc_objects_v1` (Postings) | HEALTHY | **HEALTHY** | HTTP 200, 5 hits (YOLO classes) |

---

## 3. Chính Sách Thumbnail & Khắc Phục Lỗi Khung Hình Trống (Blank Frame)

Theo quy định Mục 24 của tài liệu thiết kế:
1. **Visual (`siglip_custom`, `btc_clip`)**: Hiển thị trực tiếp keyframe ảnh tương ứng từ thư mục keyframes.
2. **OCR (`ocr_bm25`, `ocr_trigram`, `ocr_bge`)**: Ánh xạ `keyframe_uid` về khung hình CUSTOM gốc của video tại thời điểm phát hiện.
3. **Qwen (`qwen_structured`, `qwen_bm25`, `qwen_bge`)**: Ánh xạ về keyframe CUSTOM cha.
4. **BTC Objects (`btc_objects`)**: Ánh xạ `local_keyframe_no` về keyframe BTC tương ứng.
5. **ASR (`asr_bm25`, `asr_bge`)**: Do segment âm thanh không có 1 frame vật lý duy nhất, hệ thống tự động tìm keyframe gần nhất và gán nhãn:
   `PREVIEW NEAR ASR SEGMENT`
6. **Media Video (`media_bm25`)**: Lấy keyframe đại diện đầu tiên kèm nhãn:
   `VIDEO PREVIEW — NO MATCHED TIMESTAMP`
7. **Xử lý lỗi Video Stream**: Nếu video gốc không khả dụng hoặc lỗi tải, Video Player trong Inspector hiển thị thông báo `VIDEO_UNAVAILABLE` rõ ràng, không để player đen/trống.

---

## 4. Danh Sách Artifact Bằng Chứng Phục Hồi

Toàn bộ bằng chứng được lưu trữ tại `F:\AIC_WORK\artifacts\retrieval_v2\runtime_recovery\rec_001\`:
1. `storage_inventory.json`: Thống kê dung lượng, đường dẫn ổ đĩa Drive & NVMe SSD.
2. `video_availability_matrix.csv`: Ma trận 873 video với trạng thái tồn tại cục bộ, tồn tại Drive và thư mục keyframe.
3. `sqlite_table_inventory.csv`: Danh mục toàn bộ 66 bảng/view trong `mapping.sqlite` và số dòng dữ liệu.
4. `provider_wiring_before.json`: Trạng thái cấu hình trước phục hồi (37 bảng, 6 provider bị degraded).
5. `provider_wiring_after.json`: Trạng thái cấu hình sau phục hồi (66 bảng, 12 provider HEALTHY).
6. `blank_frame_repro.csv`: Ghi nhận nguyên nhân gốc và biện pháp khắc phục hiển thị khung hình cho từng lane.
7. `lane_smokes.jsonl`: Kết quả chạy smoke test thực tế của toàn bộ 12 lane.
8. `media_smokes.jsonl`: Thời gian phản hồi và kiểm tra giải mã frame thực tế trên các video mẫu từ L21 đến L30.
9. `summary.json`: Tổng kết chỉ số phục hồi.
10. `DONE`: File đánh dấu hoàn tất phiên phục hồi.
