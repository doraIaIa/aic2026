# Kế Hoạch Dọn Dẹp & Vệ Sinh Repository (Phased Cleanup Plan C0–C5)

> **LƯU Ý:** ĐÂY LÀ KẾ HOẠCH HÀNH ĐỘNG DỰ THẢO. **KHÔNG THỰC THI TỰ ĐỘNG**.
> Mọi hành động chỉ được thực hiện sau khi có phê duyệt rõ ràng.

---

## PHA C0: AN TOÀN TRƯỚC KHI THAO TÁC (PRE-CLEANUP SAFETY)
* **Mục tiêu**: Đảm bảo toàn bộ test suite đang chạy tốt và không có thay đổi dang dở.
* **Preconditions**:
  * Chạy `pytest -q tests` $\rightarrow$ Đạt 178/178 tests PASS.
  * Kiểm tra `git status` $\rightarrow$ Ghi nhận snapshot làm điểm rollback an toàn.

---

## PHA C1: VỆ SINH CẤU HÌNH & GITIGNORE (GIT HYGIENE)
* **Hành động**:
  * Thêm `src/*.egg-info/`, `*.db`, `*.sqlite3` vào file `.gitignore` để tránh commit nhầm metadata build hoặc file database cục bộ lên repo.
* **Risk**: Rất thấp (LOW).
* **Validation After**: Chạy `git status` xác nhận thư mục `src/aic2026.egg-info` không còn bị theo dõi.

---

## PHA C2: PHÂN TÁCH TÀI LIỆU LỊCH SỬ (DOCS ARCHIVE CANDIDATES)
* **Hành động đề xuất**:
  * Tạo thư mục `docs/archive/` và gom các tài liệu đã bị supersede (`docs/PROJECT_OVERVIEW.md`, `docs/PROJECT_STATE.md`, `docs/EVALUATION.md`, `docs/CLOUD_EXECUTION.md`, `START_HERE.md`) vào đó để làm gọn thư mục `docs/` chính.
* **Risk**: Rất thấp (LOW). Không làm ảnh hưởng đến mã nguồn Python.
* **Validation After**: Kiểm tra các link tài liệu trong `plan/` và `README.md` vẫn hoạt động tốt.

---

## PHA C3: CHUẨN HÓA CẤU TRÚC SEARCH & RETRIEVAL (PACKAGE REFACTOR PLAN)
* **Hành động đề xuất**:
  * Chuyển `src/aic2026/search/api.py` thành `src/aic2026/api/` hoặc tích hợp trực tiếp vào `retrieval/api.py` để thống nhất điểm truy cập REST API.
  * Chuyển các script build index rời rạc (`build_asr_index.py`, `build_object_index.py`) thành các lệnh CLI chính thức trong `src/aic2026/cli.py` (`aic build-index ...`).
* **Risk**: Trung bình (MEDIUM). Cần cập nhật các test trong `tests/test_asr_search_api.py`.
* **Validation After**: Chạy lại toàn bộ test suite `pytest tests`.

---

## PHA C4: THIẾT LẬP DATA HUB (M0 EXECUTION PREPARATION)
* **Hành động**:
  * Tạo module `src/aic2026/db/hub.py` và script nạp dữ liệu từ `DATA_REGISTRY` vào SQLite `aic2026_data_hub.db` theo đúng thiết kế `plan/01_DATA_HUB_MAPPING.md`.
* **Risk**: Thấp (LOW - Hoàn toàn mới, không ghi đè code cũ).
* **Validation After**: Viết unit test `tests/test_data_hub.py` kiểm tra kết nối và truy vấn FTS5.

---

## PHA C5: POST-CLEANUP VERIFICATION & BENCHMARK BASELINE
* **Hành động**:
  * Chạy full test suite `pytest -q tests`.
  * Khởi động server FastAPI và kiểm tra endpoint `/api/v1/capabilities`.
