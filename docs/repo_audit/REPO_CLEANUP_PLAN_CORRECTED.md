# Kế Hoạch Vệ Sinh Repository Đã Hiệu Chỉnh (Corrected Cleanup Plan C0–C4)

> **Phạm vi:** Kế hoạch này **CHỈ CHỨA CÁC HÀNH ĐỘNG VỆ SINH MÃ NGUỒN & QUẢN TRỊ TÀI LIỆU (Housekeeping & Governance)**.
> Tuyệt đối **KHÔNG** trộn lẫn việc cài đặt tính năng (như Data Hub M1 hay Refactor Search API) vào kế hoạch dọn dẹp này.

---

## PHA C0: ĐÓNG BĂNG BASELINE & TÁI LẬP GIT (AUTHORITY & BASELINE FREEZE)
* **Phân loại**: `TRUE_CLEANUP / BASELINE_FREEZE`
* **Mục tiêu**: Giải quyết dứt điểm lỗi `HEAD_REPRODUCIBILITY = FAIL` bằng cách commit toàn bộ mã nguồn hợp lệ đang chạy 178 tests.
* **Preconditions**:
  * Chạy `pytest -q tests` -> Đạt 178/178 tests PASS.
* **Planned Actions**:
  1. Giữ nguyên `configs/local.toml` ở trạng thái uncommitted/ignored.
  2. Stage toàn bộ các file core, test và docs chuẩn:
     - `src/aic2026/core/data_registry.py`
     - `src/aic2026/workspace.py`
     - `src/aic2026/retrieval/providers/object.py`
     - `src/aic2026/retrieval/planner.py`
     - `src/aic2026/search/build_object_index.py`
     - `src/aic2026/evaluation/*.py`
     - `tests/test_data_registry.py`, `test_object_provider.py`, `test_workspace.py`
     - `plan/*` (Toàn bộ 8 tài liệu V2)
     - `docs/DATA_PATHS.md`, `configs/data_paths.json`
     - `docs/repo_audit/*`
  3. Tạo focused commit: `chore(baseline): freeze canonical baseline data registry, tests and retrieval v2 plan`.
* **Validation After**:
  * `git status --short` sạch sẽ.
  * `pytest -q tests` chạy PASS 178 tests trên clean HEAD.

---

## PHA C1: VỆ SINH .GITIGNORE AN TOÀN (SAFE GIT HYGIENE)
* **Phân loại**: `TRUE_CLEANUP`
* **Mục tiêu**: Ngăn chặn commit rác phát sinh khi build hoặc chạy test.
* **Planned Actions**:
  * Bổ sung các pattern có scope rõ ràng vào `.gitignore`:
    ```gitignore
    src/*.egg-info/
    .pytest_cache/
    aic2026_data_hub.db
    local.db
    ```
* **Validation After**: Thư mục `src/aic2026.egg-info` không còn hiện `??` trong git status.

---

## PHA C2: QUẢN TRỊ TÀI LIỆU CŨ CÓ ĐIỀU KIỆN (CONDITIONAL DOCS GOVERNANCE)
* **Phân loại**: `DOC_GOVERNANCE`
* **Mục tiêu**: Sắp xếp tài liệu lịch sử mà không làm gãy các quy tắc của `AGENTS.md`.
* **Precondition Bắt Buộc**:
  * Cập nhật `AGENTS.md` Section 1 và Rule 22 trước khi di chuyển bất kỳ tài liệu nào.
* **Planned Actions**:
  * Sau khi `AGENTS.md` được cập nhật: Tạo thư mục `docs/archive/` và gom các tài liệu đã supersede (`docs/PROJECT_OVERVIEW.md`, `docs/PROJECT_STATE.md`, `docs/EVALUATION.md`, `docs/CLOUD_EXECUTION.md`, `START_HERE.md`).

---

## PHA C3: XÁC MINH VÀ XỬ LÝ FILE DUPLICATE (DUPLICATE RECONCILIATION)
* **Phân loại**: `TRUE_CLEANUP`
* **Mục tiêu**: Xử lý 2 cặp duplicate SHA-256 đã phát hiện:
  1. `AIC2026_RECOVERED_MASTER_PLAN.md` ở root -> Lưu trữ hoặc loại bỏ vì đã có bản canonical tại `docs/AIC2026_RECOVERED_MASTER_PLAN.md`.
  2. `docs/deep-research-report.md` -> Lưu trữ hoặc loại bỏ vì đã có bản canonical tại `plan/deep-research-report.md`.

---

## PHA C4: KIỂM TRA TOÀN DIỆN HẬU DỌN DẸP (POST-CLEANUP VERIFICATION)
* **Phân loại**: `VERIFICATION`
* **Mục tiêu**: Đảm bảo repository ở trạng thái hoàn hảo nhất trước khi bước sang Retrieval V2 M1.
* **Planned Actions**:
  * Chạy `pytest -q tests` -> 178 tests PASS.
  * Chạy `git status` -> Working tree clean.
  * Mở cổng **GO cho Retrieval V2 Milestone 1 (Xây dựng SQLite Data Hub)**.