# Bản Đồ Tài Liệu & Thẩm Quyền Kiến Trúc (Repo Superseded Map)

> **Mục tiêu**: Phân định rõ ràng tài liệu nào là **Thẩm quyền hiện tại (Current Authority)**, tài liệu nào là **Lịch sử / Đã bị thay thế (Superseded)** để tránh đọc nhầm hướng dẫn cũ.

---

## 1. BẢNG TRA CỨU THẨM QUYỀN TÀI LIỆU (AUTHORITY MATRIX)

| Tài liệu / Kế hoạch | Phân loại | Tài liệu thẩm quyền thay thế (Superseded by) | Trạng thái & Ghi chú |
|---|---|---|---|
| **`plan/00_MASTER_ARCHITECTURE.md`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Bản thiết kế kiến trúc chủ đạo của toàn hệ thống Retrieval V2. |
| **`plan/01_DATA_HUB_MAPPING.md`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Bản đặc tả chi tiết SQLite Data Hub, schema và mapping 1:1. |
| **`plan/02_QUERY_BRAIN_SEARCH_MODES.md`**| `CURRENT_AUTHORITY` | *(Chính nó)* | 5 chế độ tìm kiếm, bộ định tuyến chủ đề và cơ chế rescue. |
| **`plan/03_SEARCH_LANES_TECH_STACK.md`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Công nghệ 4 Làn độc lập (SigLIP2, Whisper, OCR Trigram, Qwen). |
| **`plan/04_TEMPORAL_MEDIA_INSPECTOR.md`**| `CURRENT_AUTHORITY` | *(Chính nó)* | Thuật toán chuỗi thời gian TRAKE và Exact Media Player. |
| **`plan/05_IMPLEMENTATION_EVALUATION_ROADMAP.md`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Lộ trình từng bước và benchmark harness. |
| **`AGENTS.md`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Hiến pháp kỹ thuật 1085 dòng bảo vệ repository. |
| **`docs/DATA_PATHS.md`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Bảng tra cứu đường dẫn dữ liệu tập trung (Drive & Local). |
| **`docs/DATA_CONTRACT_LOCK.md`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Bản khóa contract dữ liệu canonical (873 video). |
| **`docs/openapi-retrieval-v1.yaml`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Đặc tả chuẩn REST API cho Frontend kết nối Backend. |
| **`docs/deep-research-report.md`** | `CURRENT_AUTHORITY` | *(Chính nó)* | Báo cáo nghiên cứu sâu dung hòa toàn bộ ý tưởng của đội. |
| **`docs/AUDIT_*.md` (4 files)** | `HISTORICAL_KEEP` | *(Dữ liệu kiểm toán thực tế)* | Báo cáo kiểm toán 873 video, dữ liệu BTC, OCR và Series. |
| **`docs/PROJECT_OVERVIEW.md`** | `SUPERSEDED` | `plan/00_MASTER_ARCHITECTURE.md` | Tài liệu tổng quan giai đoạn cũ trước khi merge ASR full. |
| **`docs/PROJECT_STATE.md`** | `SUPERSEDED` | `plan/README.md` & `DATA_PATHS.md` | Ghi chú trạng thái thời điểm chạy batch Colab. |
| **`docs/EVALUATION.md`** | `SUPERSEDED` | `plan/05_IMPLEMENTATION_EVALUATION_ROADMAP.md` | Bản kế hoạch đánh giá cũ trước khi có bộ chấm KIS/QA/TRAKE. |
| **`docs/CLOUD_EXECUTION.md`** | `SUPERSEDED` | `notebooks/colab_asr_whisper_medium_full_corpus_v1.ipynb` | Hướng dẫn chạy cloud batch cũ (hiện đã chạy xong 100%). |
| **`START_HERE.md`** | `SUPERSEDED` | `plan/README.md` | Hướng dẫn bắt đầu sơ khai của repo. |

---

## 2. NGUYÊN TẮC ÁP DỤNG:
* Khi tra cứu về **Kiến trúc & Thuật toán**: Luôn đọc từ thư mục **`plan/`**.
* Khi tra cứu về **Đường dẫn & Dữ liệu**: Luôn đọc từ **`docs/DATA_PATHS.md`** hoặc `DATA_REGISTRY`.
* Các tài liệu thuộc nhóm `SUPERSEDED` được giữ lại trong repo để lưu giữ lịch sử phát triển (**Lineage**), nhưng **không được dùng làm căn cứ kỹ thuật** cho giai đoạn Retrieval V2.
