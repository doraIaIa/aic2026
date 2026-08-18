# AIC 2026 — Báo Cáo Hoàn Tất M1B: CUSTOM Keyframe Catalog + Qwen Semantics Mapping

> **Milestone:** M1 — Data Hub & Unified Mapping  
> **Slice:** M1B — CUSTOM Keyframe Catalog + Qwen Semantics Mapping  
> **Thời gian thực hiện:** 2026-08-18  
> **Starting HEAD:** `b11f99c15d4ba219a16f2c2fe437943ce0445d4c`  
> **Acceptance Verdict:** **PASS**

---

## 1. TỔNG QUAN KẾT QUẢ M1B (EXECUTIVE SUMMARY)

| Chỉ số / Hạng mục | Kết quả đạt được | Trạng thái |
|---|:---:|:---:|
| **Tổng số CUSTOM Keyframes** | **116,767** | ✅ Khớp 100% |
| **Số lượng video bao phủ** | **873** | ✅ Đầy đủ 873 video |
| **Số lượng Keyframe UID duy nhất** | **116,767** (`CUSTOM:{video_id}:F{frame_idx}`) | ✅ Độc bản |
| **Số lượng khóa join `(video_id, frame_idx)` duy nhất** | **116,767** | ✅ 100% Unique |
| **Không gian khung hình (frame_space)** | `CUSTOM` (Không trộn lẫn BTC) | ✅ Tuyệt đối cô lập |
| **Qwen Raw Records đọc được** | **116,767** | ✅ Đọc toàn bộ shard_000 |
| **Qwen Joined thành công (Semantic OK)** | **116,649** | ✅ Khớp chính xác |
| **Qwen Orphan (Bản ghi mồ côi)** | **0** | ✅ 0 orphan |
| **Qwen Missing Explicit (Khuyết quan sát)** | **118** (Ghi nhận rõ trong `qwen_missing_keyframes.jsonl`) | ✅ Không tạo fake row |
| **Lệch mốc thời gian (pts_time mismatch)** | **0** | ✅ Khớp từng mili-giây |
| **Vi phạm đường dẫn tuyệt đối (Absolute Path)** | **0** (Chỉ dùng canonical relative path) | ✅ 100% Portable |
| **Đột biến dữ liệu gốc (Raw Mutation)** | **0** (Hoàn toàn non-mutating) | ✅ Bất biến |
| **Chạy lại mô hình (Inference rerun)** | **0** (Không inference tốn kém) | ✅ Read-only parsing |
| **Checksum Catalog CUSTOM** | `7acaee492dee30cb35db3e44b7d9e81863229958fbb1d2d95af7694df4e8b615` | ✅ Khóa mã băm |
| **Checksum Catalog Qwen Semantics** | `08415b0e4aa09fd980a9b7d1c9d02a0770602f60329d91f01ca638f04f9561fe` | ✅ Khóa mã băm |
| **Kết quả kiểm thử toàn diện** | **202 passed** (191 baseline + 11 M1B tests) | ✅ 100% PASS |

---

## 2. NGUỒN DỮ LIỆU & NGUYÊN TẮC ÁNH XẠ (DATA PROVENANCE & MAPPING)

### Nguồn Dữ Liệu:
- **Authority A (Custom Keyframes):** `output_llm/cache/df_keyframes.pkl` (hoặc `output/map_keyframes/*.csv` qua 873 video).
- **Authority B (Qwen VLM Semantics):** `output_llm/shard_000.jsonl`.
- **Authority C (Canonical Video Universe):** M1A Canonical Video Catalog (`v1_natural_series_video`).

### Nguyên Tắc Định Danh & Chuẩn Hóa:
- **Keyframe UID:** Định dạng chuẩn `CUSTOM:{video_id}:F{frame_idx}`.
- **Relativization:** Đường dẫn ảnh được chuẩn hóa portable: `output/keyframes/{video_id}/{file_name}`.
- **Timestamp:** Chuyển đổi chính xác sang mili-giây nguyên: `timestamp_ms = int(round(raw_pts_time * 1000))`.
- **Qwen Missing Explicit:** 118 khung hình có quan sát rỗng/lỗi parse trong raw shard được tách riêng vào `qwen_missing_keyframes.jsonl`, gán trạng thái `qwen_status = 'MISSING'`, tuyệt đối không tạo bản ghi giả (fake semantic row).

---

## 3. CÁC FILE ĐÃ TẠO VÀ CHỈNH SỬA (CHANGESET)

### Files Tạo Mới:
1. `src/aic2026/data_hub/custom_models.py`: Data models (`CustomKeyframeRecord`, `QwenSemanticRecord`, `QwenMissingRecord`, `CustomSpace`, `CustomValidationResult`).
2. `src/aic2026/data_hub/custom_validator.py`: `CustomKeyframeValidator` fail-closed đối soát 12 bất biến dữ liệu.
3. `src/aic2026/data_hub/custom_builder.py`: Bộ sinh và materializer xuất `custom_keyframes.jsonl`, `qwen_semantics_normalized.jsonl`, `qwen_missing_keyframes.jsonl`, `custom_space.json`, `source_registry.jsonl`, `build_manifest.json`.
4. `src/aic2026/data_hub/custom_registry.py`: In-memory read API (`get_custom_keyframe`, `get_custom_keyframe_by_video_frame`, `get_qwen`, `get_qwen_by_video_frame`, `qwen_status`).
5. `tests/test_custom_qwen_mapping.py`: Bộ 11 unit tests bao phủ toàn diện các ca kiểm thử M1B.
6. `docs/retrieval_v2/M1B_CUSTOM_QWEN_MAPPING_RESULT.md`: Báo cáo kết quả M1B.

### Files Chỉnh Sửa:
1. `src/aic2026/data_hub/__init__.py`: Export các lớp và hàm mới của Data Hub.
2. `src/aic2026/db/schema.sql`: Bổ sung bảng `custom_keyframes` và `qwen_frames` kèm B-tree index.
3. `src/aic2026/cli.py`: Bổ sung lệnh CLI `aic build-custom-qwen-catalog` và `aic validate-custom-qwen-catalog`.

---

## 4. GIỚI HẠN & BƯỚC TIẾP THEO

- **Giới hạn Slice M1B:** Slice M1B chỉ ánh xạ Custom Keyframes và Qwen Semantics trong không gian `CUSTOM`. Chưa nạp ASR, OCR (M1C) và chưa ánh xạ BTC Keyframes/Objects (M1D).
- **Bước tiếp theo (Next Task):**
  👉 **`M1C — ASR + OCR Mapping`** (theo `plan/01_DATA_HUB_MAPPING.md`).
