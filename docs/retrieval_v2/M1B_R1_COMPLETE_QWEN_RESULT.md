# AIC 2026 — Báo Cáo M1B-R1: Hoàn Tất Phủ Toàn Bộ 100% Qwen Semantics

> **Milestone:** M1 — Data Hub & Unified Mapping  
> **Slice:** M1B-R1 — Finalize Complete Qwen Coverage  
> **Thời gian thực hiện:** 2026-08-18  
> **Starting HEAD:** `449ae5882672bf62cfa0303884ea2ae22e1a38e8`  
> **Acceptance Verdict:** **PASS**

---

## 1. TỔNG QUAN HIỆU CHỈNH (EXECUTIVE SUMMARY)

- **Ngữ cảnh lịch sử (Historical Lineage):**
  - Snapshot trước đây: ghi nhận 116,587 bản ghi thành công và 180 bản ghi khuyết.
  - Snapshot thực tế hiện hành: Đã chạy lại (rerun) toàn bộ các batch lỗi trên Colab, hợp nhất thành **shard_000.jsonl hoàn chỉnh 100%**.
- **Quy tắc phân loại ngữ nghĩa (Semantic Status Rule):**
  - `ROW_PRESENT_VALID => OK` (kể cả khi các mảng quan sát ngữ nghĩa rỗng, đây vẫn là một quan sát VLM hoàn tất hợp lệ).
  - `ROW_ABSENT => MISSING`.
- **Kết quả đối soát trên dữ liệu thật:**

| Chỉ số / Hạng mục | Kết quả đạt được | Trạng thái |
|---|:---:|:---:|
| **Tổng số CUSTOM Keyframes** | **116,767** | ✅ Khớp 100% |
| **Qwen Raw Rows** | **116,767** | ✅ Đầy đủ |
| **Qwen Joined thành công (OK)** | **116,767** | ✅ Khớp 100% (1:1) |
| **Qwen Missing** | **0** | ✅ Không còn khuyết |
| **Qwen Orphan** | **0** | ✅ 0 orphan |
| **Qwen Duplicates** | **0** | ✅ 0 duplicate |
| **Số lượng video bao phủ** | **873** | ✅ Đầy đủ 873 video |
| **Lệch mốc thời gian (pts mismatch)** | **0** | ✅ Khớp từng mili-giây |
| **Vi phạm đường dẫn tuyệt đối** | **0** | ✅ 100% Portable |
| **Đột biến dữ liệu gốc (Raw Mutation)** | **0** | ✅ Bất biến |
| **Chạy lại mô hình (Inference rerun)** | **0** | ✅ Read-only parsing |
| **Checksum Catalog CUSTOM** | `c90ba65322dacaf6e475df14ebf7a00c65bd46d8c21c591203c857f2b8aefbf6` | ✅ Khóa mã băm |
| **Checksum Catalog Qwen Canonical** | `31e4b027a2e3b9ec3d0bf683d822717afc9018d3da1e2af13a15eb4add8b3b66` | ✅ Khóa mã băm |
| **Kết quả kiểm thử toàn diện** | **203 passed** (100% PASS) | ✅ PASS |

---

## 2. CÁC FILE ĐÃ HIỆU CHỈNH

1. `src/aic2026/data_hub/custom_builder.py`: Cập nhật logic phân loại `OK` cho mọi bản ghi Qwen hợp lệ hiện diện trong shard.
2. `tests/test_custom_qwen_mapping.py`: Bổ sung kiểm thử cho các ca bản ghi ngữ nghĩa rỗng và độ phủ 1:1 đầy đủ.
3. `docs/retrieval_v2/M1B_CUSTOM_QWEN_MAPPING_RESULT.md`: Cập nhật trạng thái snapshot hoàn chỉnh.
4. `docs/retrieval_v2/M1B_R1_COMPLETE_QWEN_RESULT.md`: Báo cáo chi tiết M1B-R1.

---

## 3. KẾT LUẬN & SẴN SÀNG

- **M1B_ACCEPTANCE:** **PASS**
- **M1C_READY:** **YES**
- **Bước tiếp theo:** 👉 **`M1C — ASR + OCR Mapping`**.
