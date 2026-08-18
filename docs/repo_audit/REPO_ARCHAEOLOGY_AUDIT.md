# AIC 2026 — Repository Archaeology & Legacy Audit Report

> **Thời gian thực hiện:** 2026-08-18  
> **Chế độ (Mode):** READ-ONLY ARCHAEOLOGY & CLEANUP PLANNING  
> **Thẩm quyền áp dụng:** AGENTS.md (1085 dòng) & Retrieval V2 Plan Suite (`plan/`)  
> **Khẩu quyết:** *Independent evidence, shared identity, late fusion.* | *Raw immutable → Canonical normalized → Runtime rebuildable.*

---

## 1. EXECUTIVE SUMMARY (TÓM TẮT ĐIỀU HÀNH)

Cuộc kiểm toán toàn diện đã rà soát **157 file** trong repository `aic2026`. Sau khi đã dọn dẹp các script tạm và file test phân mảnh ở bước trước, repository hiện tại ở trạng thái **rất sạch sẽ, tập trung và không có dead code nguy hiểm**.

### Các phát hiện cốt lõi:
1. **Trạng thái Codebase**: Toàn bộ **46 file production** trong `src/aic2026` (`retrieval`, `media`, `evaluation`, `search`, `core`) đều có reachability rõ ràng và được bảo vệ bởi **23 test files (178 unit tests)** đang PASS 100%.
2. **Trạng thái Tài liệu**: Thư mục `plan/` (gồm 8 tài liệu V2) là **Thẩm quyền thiết kế tối cao (Current Design Authority)**. Các tài liệu lịch sử cũ (`docs/PROJECT_STATE.md`, `docs/EVALUATION.md`) được giữ lại nhưng hạ cấp làm tài liệu tham khảo quá khứ (`KEEP_BUT_DEMOTE`).
3. **Độ an toàn dữ liệu**: Đã khóa không gian 873 video canonical, 107.5k câu thoại Whisper ASR, 116.7k Custom Keyframes, 116.5k Qwen captions thông qua `DATA_REGISTRY` (`DATA_PATHS.md`).

---

## 2. AUDIT SCOPE & SAFETY

* **Phạm vi kiểm toán**: 100% file trong `F:\AIC_DEV\aic2026`.
* **An toàn tuyệt đối**: Không có file nào bị xóa, đổi tên hay di chuyển trong quá trình audit này.
* **Quy tắc tuân thủ**: Mọi kết luận đều dựa trên evidence thực nghiệm (imports, CLI registry, FastAPI router, pytest execution).

---

## 3. REPOSITORY BASELINE

* **Repository Root**: `F:\AIC_DEV\aic2026`
* **Current Branch**: `main`
* **Starting / Current HEAD**: `fa470d38892bc31b87e6b460c3b020534007e490`
* **Tổng số file quét được**: **157 files** (trong đó 129 tracked trong Git).
* **Test Baseline**: **178 passed, 0 failed** (pytest run time: ~6.38s).
* **Top-Level Directories**: `artifacts/`, `configs/`, `docs/`, `manifests/`, `notebooks/`, `plan/`, `scripts/`, `src/`, `tests/`.

---

## 4. CURRENT PRODUCTION / REUSABLE FOUNDATION

### A. Subsystems Cốt Lõi (Active Production):
1. **`src/aic2026/retrieval/`**:
   - `orchestrator.py`: Reciprocal Rank Fusion (RRF $k=60$) Engine.
   - `capabilities.py`: Báo cáo trạng thái khả dụng của từng provider độc lập.
   - `providers/`: `visual.py` (CLIP FAISS), `asr.py` (Whisper Search), `object.py` (Object detection).
   - `contract.py`: Khung JSON schema contract cho request/response tìm kiếm.
2. **`src/aic2026/media/`**:
   - `mapper.py`: Ánh xạ chính xác $pts\_time \leftrightarrow frame\_idx$.
   - `resolver.py`: Stream video nguồn MP4 và giải mã frame vật lý chính xác.
3. **`src/aic2026/evaluation/`**:
   - `scoring.py`: Bộ chấm điểm KIS, QA, TRAKE chuẩn thể lệ AIC.
   - `runner.py`: Động cơ chạy benchmark đánh giá tự động.
4. **`src/aic2026/core/`**:
   - `data_registry.py`: Data Registry tập trung kết nối Drive và Local.
   - `paths.py`, `config.py`, `atomic.py`, `hashing.py`: Tiện ích nền tảng.

---

## 5. CURRENT DESIGN & CONTRACT AUTHORITIES

1. **`plan/` Suite (8 tài liệu)**: Thẩm quyền kiến trúc tối cao cho Retrieval V2.
2. **`AGENTS.md`**: Hiến pháp kỹ thuật 1085 dòng.
3. **`docs/DATA_PATHS.md` & `configs/data_paths.json`**: Thẩm quyền đường dẫn dữ liệu.
4. **`docs/DATA_CONTRACT_LOCK.md`**: Bản khóa contract dữ liệu canonical.
5. **`docs/openapi-retrieval-v1.yaml`**: Chuẩn giao tiếp REST API cho Frontend.

---

## 6. SOURCE-OF-TRUTH CONFLICTS & GIẢI QUYẾT

| Xung đột tiềm ẩn | Nguồn cũ / Sai lệch | Nguồn thẩm quyền (Source-of-Truth) | Giải pháp chốt |
|---|---|---|---|
| Số lượng video | 859 video (thiếu 14 video phi ngôn ngữ) | **873 video canonical** | Đã chốt 873 video trong `DATA_REGISTRY` & `asr_videos.jsonl`. |
| Thẩm quyền Frame nộp bài | Keyframe JPEG ordinal | **Source Video MP4** | Exact physical frame resolution qua `media/resolver.py`. |
| Không gian Keyframe | Trộn BTC và Custom | **Phân tách 3 namespace**: BTC, CUSTOM, SOURCE | Giữ độc lập theo Rule 9 `AGENTS.md`. |
| Không gian Vector | Nguy cơ cross embedding | **CLIP $\leftrightarrow$ BTC CLIP, SigLIP $\leftrightarrow$ SigLIP, BGE $\leftrightarrow$ Text** | Không lai tạp theo Rule 17 `AGENTS.md`. |
| Kết hợp điểm số | Cộng thô raw scores | **RRF Fusion ($k=60$)** | Chuẩn hóa hoàn toàn theo thứ hạng. |

---

## 7. LEGACY PLANS & SUPERSEDED DOCS

Các tài liệu cũ từ các phase trước (`docs/PROJECT_OVERVIEW.md`, `docs/PROJECT_STATE.md`, `docs/EVALUATION.md`, `docs/CLOUD_EXECUTION.md`, `START_HERE.md`) ghi lại tiến trình lịch sử khi đang bóc băng ASR trên Colab. Hiện tại đã hoàn thành 100% nên các file này được gán nhãn `LEGACY_STILL_REFERENCED` và `KEEP_BUT_DEMOTE`.

---

## 8. EXPERIMENTAL CODE & ORPHAN CANDIDATES

* Không phát hiện dead code hoặc orphan code nguy hiểm trong `src/aic2026/`.
* Thư mục `src/aic2026.egg-info/` là sản phẩm sinh ra khi chạy `pip install -e .`, cần được đưa vào `.gitignore`.

---

## 9. GIT HYGIENE & GENERATED ARTIFACTS

* Không có binary lớn (file `.npy`, `.faiss`, video `.mp4` hay ảnh `.jpg`) bị commit vào Git.
* Cấu hình `.gitignore` hiện tại đã bảo vệ tốt, cần bổ sung `*.egg-info/` và `*.db`.

---

## 10. DO_NOT_TOUCH (DANH SÁCH BẢO VỆ TỐI CAO)

1. `src/aic2026/media/` (Tuyệt đối không sửa khi không có test bảo vệ, đây là module tính frame vật lý).
2. `src/aic2026/retrieval/contract.py` (Contract chuẩn giữa Backend và UI).
3. `src/aic2026/core/data_registry.py` & `configs/data_paths.json` (Nguồn tham chiếu dữ liệu duy nhất).
4. `plan/` directory (Tài liệu thiết kế kiến trúc chuẩn).
5. `AGENTS.md` (Hiến pháp kỹ thuật).
6. Toàn bộ 178 unit tests trong `tests/`.

---

## 11. QUANTITATIVE CLASSIFICATION SUMMARY

```text
PHÂN LOẠI THEO VAI TRÒ (ROLE_STATUS):
├── CURRENT_PRODUCTION:           46 files
├── CURRENT_DESIGN_AUTHORITY:      14 files
├── CURRENT_DATA_CONTRACT:         13 files
├── CURRENT_TEST:                  23 files
├── CURRENT_REUSABLE_FOUNDATION:   17 files
├── CURRENT_TOOLING:               28 files
├── LINEAGE_EVIDENCE:               5 files
├── LEGACY_STILL_REFERENCED:        5 files
└── BUILD_OUTPUT:                   6 files

PHÂN LOẠI THEO ĐỀ XUẤT HÀNH ĐỘNG (ACTION_RECOMMENDATION):
├── KEEP:                         130 files
├── KEEP_AND_MARK_AUTHORITY:       16 files
├── KEEP_BUT_DEMOTE:                5 files
└── ADD_TO_GITIGNORE_CANDIDATE:     6 files
```

---

## 12. QUYẾT ĐỊNH GO / NO-GO

### A. Cleanup Phase: **GO**
* Repository đã được dọn sạch các script scratch và notebook nháp. Không có xung đột kỹ thuật cản trở.

### B. Retrieval V2 Milestone 0 (Data Hub Construction): **GO**
* Tất cả 5 trụ cột dữ liệu (873 video, 107.5k ASR, 116.7k Custom Keyframes, 116.5k Qwen captions, 178k BTC keyframes) đã sẵn sàng để nạp vào SQLite Data Hub theo tài liệu `plan/01_DATA_HUB_MAPPING.md`.
