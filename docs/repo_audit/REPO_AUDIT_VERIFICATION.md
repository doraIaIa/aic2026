# AIC 2026 — Báo Cáo Xác Minh & Hiệu Chỉnh Kiểm Toán Repository (C0V Verification)

> **Mục tiêu:** Kiểm toán lại tính nhất quán của `REPO_ARCHAEOLOGY_AUDIT.md`, sửa chữa các mâu thuẫn số liệu, phát hiện rủi ro tái lập commit HEAD và hiệu chỉnh kế hoạch dọn dẹp an toàn.
> **Chế độ (Mode):** READ-ONLY AUDIT VERIFICATION
> **Starting / Current HEAD:** `fa470d38892bc31b87e6b460c3b020534007e490` | **Branch:** `main`

---

## 1. EXECUTIVE VERDICT (PHÁN QUYẾT TỔNG THỂ)

| Tiêu chí đánh giá | Kết quả | Lý do & Minh chứng kỹ thuật |
|---|:---:|---|
| **A. Audit Consistency** | **FAIL -> RECONCILED** | Audit cũ báo 129 + 45 != 157. Đã xác minh chính xác: 129 tracked - 17 deleted = 112 present tracked + 45 untracked = 157. |
| **B. HEAD Reproducibility** | **FAIL** | Working tree pass 178 tests nhưng phụ thuộc vào **23 file critical UNTRACKED** (`data_registry.py`, `workspace.py`, `plan/*`, `tests/test_data_registry.py`...). Một checkout sạch từ HEAD sẽ **FAIL**. |
| **C. Cleanup C0 (Baseline Freeze)** | **GO** | Bắt buộc phải thực hiện C0 (Stage & Commit toàn bộ untracked critical files) để tạo điểm tựa Git vững chắc. |
| **D. Cleanup C1 (Git Hygiene)** | **GO** | Thêm các pattern an toàn vào `.gitignore` (`src/*.egg-info/`, `.pytest_cache/`, `local.db`). |
| **E. Doc Governance / Archive** | **NO-GO** | Bị chặn bởi xung đột: `AGENTS.md` Rule 1 bắt buộc đọc `docs/PROJECT_STATE.md`. Không được move file này vào `archive/` cho tới khi `AGENTS.md` được cập nhật. |
| **F. Retrieval V2 M0 (Baseline Freeze)** | **GO** | M0 chính là cột mốc đóng băng Data Contract & Baseline Code. |
| **G. Retrieval V2 M1 (Data Hub)** | **NO-GO** | Bị chặn (Blocked) cho tới khi M0 Baseline Freeze được commit thành công. |

---

## 2. ĐỐI SOÁT & GIẢI TRÌNH SỐ LIỆU FILE (INVENTORY RECONCILIATION)

Trong audit trước, có sự mâu thuẫn toán học giữa các con số: 129 (tracked) + 45 (untracked) = 174 != 157.

### Bảng Phân Tích Thực Tế Chính Xác 100%:
| Chỉ số (Metric) | Số lượng | Giải thích kỹ thuật |
|---|:---:|---|
| **`git_tracked_total`** | **129** | Tổng số file đang được Git theo dõi trong index / commit HEAD. |
| **`tracked_deleted_in_working_tree`** | **17** | Các file tracked đã bị xóa cục bộ (12 file test phase cũ + 5 notebook nháp). |
| **`tracked_present_in_working_tree`** | **112** | Số file tracked đang thực sự có mặt trên ổ đĩa (129 - 17 = 112). |
| **`on_disk_untracked`** | **45** | Số file mới chưa được commit vào Git (`??` trong `git status`). |
| **`actual_files_on_disk_scanned`** | **157** | Tổng số file quét được trên đĩa (112 + 45 = 157). **Khớp tuyệt đối 100%**. |

---

## 3. DANH SÁCH FILE UNTRACKED QUAN TRỌNG (CRITICAL UNTRACKED FILES)

Working tree hiện tại chứa **23 file untracked cực kỳ quan trọng** (ảnh hưởng trực tiếp đến 178 unit tests đang chạy):

| Đường dẫn (Path) | Vai trò (Role) | Có trong HEAD? | Tests cần? | CLI/API cần? | Đề xuất xử lý |
|---|---|:---:|:---:|:---:|---|
| `src/aic2026/core/data_registry.py` | `CURRENT_REUSABLE_FOUNDATION` | ❌ Không | ✅ Có (`test_data_registry.py`) | ✅ Có | **COMMIT VÀO M0 BASELINE** |
| `src/aic2026/workspace.py` | `CURRENT_PRODUCTION` | ❌ Không | ✅ Có (`test_workspace.py`) | ✅ Có | **COMMIT VÀO M0 BASELINE** |
| `src/aic2026/retrieval/providers/object.py` | `CURRENT_PRODUCTION` | ❌ Không | ✅ Có (`test_object_provider.py`) | ✅ Có | **COMMIT VÀO M0 BASELINE** |
| `src/aic2026/retrieval/planner.py` | `CURRENT_PRODUCTION` | ❌ Không | ❌ Không | ✅ Có | **COMMIT VÀO M0 BASELINE** |
| `src/aic2026/search/build_object_index.py` | `CURRENT_PRODUCTION` | ❌ Không | ❌ Không | ✅ Có | **COMMIT VÀO M0 BASELINE** |
| `src/aic2026/evaluation/annotation_assist.py`| `CURRENT_PRODUCTION` | ❌ Không | ❌ Không | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `src/aic2026/evaluation/dataset.py` | `CURRENT_PRODUCTION` | ❌ Không | ❌ Không | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `src/aic2026/evaluation/labels.py` | `CURRENT_PRODUCTION` | ❌ Không | ❌ Không | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `src/aic2026/evaluation/prepare_review.py` | `CURRENT_PRODUCTION` | ❌ Không | ❌ Không | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `tests/test_data_registry.py` | `CURRENT_TEST` | ❌ Không | ✅ Có | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `tests/test_object_provider.py` | `CURRENT_TEST` | ❌ Không | ✅ Có | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `tests/test_workspace.py` | `CURRENT_TEST` | ❌ Không | ✅ Có | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `plan/` (Toàn bộ 8 files) | `CURRENT_DESIGN_AUTHORITY` | ❌ Không | ❌ Không | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `docs/DATA_PATHS.md` | `CURRENT_DATA_CONTRACT` | ❌ Không | ❌ Không | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `configs/data_paths.json` | `CURRENT_DATA_CONTRACT` | ❌ Không | ✅ Có | ❌ Không | **COMMIT VÀO M0 BASELINE** |
| `configs/local.toml` | `CURRENT_REUSABLE_FOUNDATION` | ❌ Không | ❌ Không | ❌ Không | **GIỮ LOCAL (KHÔNG COMMIT)** |

👉 **KẾT LUẬN HEAD_REPRODUCIBILITY = FAIL**:
Nếu ai đó clone repository từ commit HEAD hiện tại (`fa470d38`), họ sẽ **KHÔNG THỂ chạy pass 178 tests** vì thiếu các file trên. Bắt buộc phải thực hiện **M0 Baseline Freeze Commit** trước khi bắt đầu M1.

---

## 4. XÁC MINH CÁC FILE DUPLICATE (EXACT DUPLICATES DETECTION)

Kiểm tra mã băm SHA-256 trên toàn bộ repo phát hiện **2 cặp file trùng lặp nội dung 100%**:

1. **Cặp 1**: `AIC2026_RECOVERED_MASTER_PLAN.md` và `docs/AIC2026_RECOVERED_MASTER_PLAN.md`
   - *SHA-256*: `5d2c5e7428ce6ecdfd5b271d46b7ff6c7b98a0cbeae41ec2bf5fffcce7677d24` (13,390 bytes).
   - *Thẩm quyền chuẩn (Canonical)*: `docs/AIC2026_RECOVERED_MASTER_PLAN.md`.
   - *Khuyến nghị*: Bản ở thư mục gốc là bản copy, có thể lưu trữ hoặc dọn dẹp sau.
2. **Cặp 2**: `docs/deep-research-report.md` và `plan/deep-research-report.md`
   - *SHA-256*: `5e88ec3265d8c1ee1fa6a47eb9ea2a233b8a1c97a9cf608c02741527877c482c` (29,434 bytes).
   - *Thẩm quyền chuẩn (Canonical)*: `plan/deep-research-report.md` (thuộc bộ suite `plan/`).

---

## 5. XUNG ĐỘT THẨM QUYỀN VĂN BẢN (AGENTS.MD MANDATORY PATH CONFLICT)

- **Xung đột**: Trong `AGENTS.md` (Section 1 và Rule 22), AI Agent bị bắt buộc phải đọc file `docs/PROJECT_STATE.md`. Tuy nhiên, kế hoạch dọn dẹp cũ (C2) lại đề xuất di chuyển `docs/PROJECT_STATE.md` vào `docs/archive/`.
- **Hậu quả nếu thực hiện C2 cũ**: Các AI Agent tiếp theo sẽ bị lỗi `NOT FOUND` và vi phạm hiến pháp Rule 1.
- **Giải pháp khắc phục (Precondition)**:
  1. Giữ nguyên `docs/PROJECT_STATE.md` tại vị trí cũ.
  2. Chỉ được di chuyển vào `docs/archive/` **SAU KHI** cập nhật `AGENTS.md` trỏ sang tài liệu thẩm quyền mới (`plan/README.md`).

---

## 6. ĐIỀU CHỈNH ĐÁNH SỐ CỘT MỐC (MILESTONE NUMBERING CORRECTION)

Audit cũ đã gọi Data Hub là 'Milestone 0'. Đối chiếu với `plan/05_IMPLEMENTATION_EVALUATION_ROADMAP.md`, thứ tự chuẩn mực là:

```text
├── Milestone 0 (M0): Contract, Data Registry & Baseline Git Freeze (HIỆN TẠI)
├── Milestone 1 (M1): Data Hub & Unified Mapping Construction (01_DATA_HUB_MAPPING.md)
├── Milestone 2 (M2): 4 Independent Retrieval Lanes (03_SEARCH_LANES_TECH_STACK.md)
├── Milestone 3 (M3): Compare & Benchmark Harness
├── Milestone 4 (M4): Temporal Sequence Engine (04_TEMPORAL_MEDIA_INSPECTOR.md)
├── Milestone 5 (M5): Safe Pruning & Query Brain (02_QUERY_BRAIN_SEARCH_MODES.md)
└── Milestone 6 (M6): Production UI & Hardening
```

---

## 7. RÀ SOÁT CẤU HÌNH .GITIGNORE & BẢO MẬT CONFIG

- **Tránh blanket ignore `*.db`**: Nếu sau này có các file SQLite database fixture nhỏ dùng cho unit tests (`tests/fixtures/*.db`), pattern `*.db` sẽ chặn luôn cả test fixtures.
- **Pattern đề xuất an toàn, có scope rõ ràng**:
  ```gitignore
  # Build metadata
  src/*.egg-info/
  
  # Pytest cache
  .pytest_cache/
  
  # Production runtime databases (local only)
  aic2026_data_hub.db
  local.db
  *.sqlite3-journal
  ```
- **Bảo mật config**: `configs/local.toml` chứa cấu hình máy cục bộ, tuyệt đối **KHÔNG COMMIT**. `configs/data_paths.json` là registry portable cấu hình tham chiếu, **AN TOÀN ĐỂ COMMIT**.

---

## 8. HÀNH ĐỘNG TIẾP THEO AN TOÀN NHẤT (RECOMMENDED NEXT ACTION)

1. **KHÔNG THỰC HIỆN BẤT KỲ REFACTOR HAY CODE DATA HUB NÀO NGAY BÂY GIỜ.**
2. **Thực hiện Milestone 0 (Baseline Freeze)**:
   - Thêm các pattern an toàn vào `.gitignore`.
   - Stage và Commit toàn bộ 23 file critical untracked (`src/aic2026/core/data_registry.py`, `plan/*`, `docs/DATA_PATHS.md`, `tests/test_data_registry.py`...) để biến trạng thái 178 tests PASS thành một **Git Commit tái lập được 100%**.
3. **Sau khi M0 hoàn tất**: Mới chính thức mở cổng **GO cho Milestone 1 (Data Hub)**.