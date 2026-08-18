# AIC 2026 — Báo Cáo Hoàn Tất M1B: CUSTOM Keyframe Catalog + Qwen Semantics Mapping

> **Milestone:** M1 — Data Hub & Unified Mapping  
> **Slice:** M1B — CUSTOM Keyframe Catalog + Qwen Semantics Mapping (Bao gồm hiệu chỉnh M1B-R1)  
> **Thời gian thực hiện:** 2026-08-18  
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
| **Qwen Raw Records đọc được** | **116,767** | ✅ Đọc toàn bộ shard_000 hoàn chỉnh |
| **Qwen Joined thành công (Semantic OK)** | **116,767** | ✅ Khớp chính xác 100% |
| **Qwen Orphan (Bản ghi mồ côi)** | **0** | ✅ 0 orphan |
| **Qwen Missing (Khuyết quan sát)** | **0** | ✅ Độ phủ toàn diện 100% |
| **Lệch mốc thời gian (pts_time mismatch)** | **0** | ✅ Khớp từng mili-giây |
| **Vi phạm đường dẫn tuyệt đối (Absolute Path)** | **0** (Chỉ dùng canonical relative path) | ✅ 100% Portable |
| **Đột biến dữ liệu gốc (Raw Mutation)** | **0** (Hoàn toàn non-mutating) | ✅ Bất biến |
| **Chạy lại mô hình (Inference rerun)** | **0** (Không inference tốn kém) | ✅ Read-only parsing |
| **Checksum Catalog CUSTOM** | `c90ba65322dacaf6e475df14ebf7a00c65bd46d8c21c591203c857f2b8aefbf6` | ✅ Khóa mã băm |
| **Checksum Catalog Qwen Semantics** | `31e4b027a2e3b9ec3d0bf683d822717afc9018d3da1e2af13a15eb4add8b3b66` | ✅ Khóa mã băm |
| **Kết quả kiểm thử toàn diện** | **203 passed** (100% PASS) | ✅ PASS |

---

## 2. NGUỒN DỮ LIỆU & NGUYÊN TẮC ÁNH XẠ (DATA PROVENANCE & MAPPING)

### Nguồn Dữ Liệu:
- **Authority A (Custom Keyframes):** `output_llm/cache/df_keyframes.pkl` (hoặc `output/map_keyframes/*.csv` qua 873 video).
- **Authority B (Qwen VLM Semantics):** `output_llm/shard_000.jsonl` (bản hoàn chỉnh sau khi rerun trên Colab).
- **Authority C (Canonical Video Universe):** M1A Canonical Video Catalog (`v1_natural_series_video`).

### Ghi Chú Lịch Sử (Historical Lineage):
- **Snapshot ban đầu:** Ghi nhận 116,587 success và 180 missing.
- **Snapshot hiện hành có thẩm quyền:** File `shard_000.jsonl` đã được bổ sung đầy đủ, đạt độ phủ 116,767 / 116,767 bản ghi. Các bản ghi có mảng ngữ nghĩa rỗng vẫn là các quan sát VLM hoàn tất hợp lệ (`OK`), đảm bảo tỷ lệ phủ 100% không khuyết.

---

## 3. CÁC FILE ĐÃ TẠO VÀ CHỈNH SỬA (CHANGESET)

1. `src/aic2026/data_hub/custom_models.py`
2. `src/aic2026/data_hub/custom_validator.py`
3. `src/aic2026/data_hub/custom_builder.py`
4. `src/aic2026/data_hub/custom_registry.py`
5. `src/aic2026/data_hub/__init__.py`
6. `src/aic2026/db/schema.sql`
7. `src/aic2026/cli.py`
8. `tests/test_custom_qwen_mapping.py`
9. `docs/retrieval_v2/M1B_CUSTOM_QWEN_MAPPING_RESULT.md`
10. `docs/retrieval_v2/M1B_R1_COMPLETE_QWEN_RESULT.md`

---

## 4. GIỚI HẠN & BƯỚC TIẾP THEO

- **Giới hạn Slice M1B:** Chỉ ánh xạ Custom Keyframes và Qwen Semantics trong không gian `CUSTOM`.
- **Bước tiếp theo (Next Task):**
  👉 **`M1C — ASR + OCR Mapping`** (theo `plan/01_DATA_HUB_MAPPING.md`).
