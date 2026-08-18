# AIC 2026 — Báo Cáo Cập Nhật M1C: ASR + OCR Canonical Mapping

> **Milestone:** M1 — Data Hub & Unified Mapping  
> **Slice:** M1C — ASR + OCR Canonical Mapping (Kèm đối soát M1C-R1)  
> **Thời gian thực hiện:** 2026-08-18  
> **Acceptance Status:** **BLOCKED_BY_OCR_ARTIFACT_ACCESS**  
> **Ghi chú nghiệm thu:** Phần ASR và OCR Keyframe Coverage hoàn tất 100%; Phần OCR raw items và BGE 10 shards tạm dừng chờ đồng bộ thư mục Drive.

---

## 1. TỔNG QUAN KẾT QUẢ M1C

| Hạng mục dữ liệu | Kết quả đạt được | Trạng thái kỹ thuật |
|---|:---:|:---:|
| **ASR Video Manifest Rows** | **873** | ✅ PASS (Khớp 100% video M1A) |
| **ASR Segments (Câu thoại)** | **107,540** | ✅ PASS (100% hợp lệ) |
| **Videos có $\ge 1$ câu thoại (HAS_SEGMENTS)** | **859** | ✅ PASS |
| **Zero-ASR Videos (ZERO_ASR_SEGMENTS)** | **14** (L24: 13, L30: 1) | ✅ PASS (Được bảo toàn đầy đủ) |
| **ASR Canonical Checksum** | `4816759e565dcb371b9ff6ca51b01e6029a13795bd87a30d952206633ab4527b` | ✅ PASS |
| **OCR Keyframe Manifests (Level A)** | **116,767** | ✅ PASS (100% custom keyframes) |
| **OCR Mapped CUSTOM Keyframes** | **116,767** | ✅ PASS (Khớp 1:1 sang M1B) |
| **OCR Canonical Checksum** | `83df83aac663de5f86f196e0121b94566d8a5d400d8fd896303da8122bd5c710` | ✅ PASS |
| **Raw OCR Text Items (Level B)** | Chờ truy cập `ocr_results` trên Drive | ⏸️ BLOCKED (Chưa đồng bộ) |
| **OCR BGE-M3 10 Shards (Level C)** | Chờ truy cập `ocr_single_text_retrieval` | ⏸️ BLOCKED (Chưa đồng bộ) |
| **Targeted Tests Passed** | **12 / 12** | ✅ 100% PASS |
| **Full Pytest Suite Passed** | **215 / 215** in 6.49s | ✅ 100% PASS |

---

## 2. HIỆU CHỈNH NGHIỆM THU (CORRECTION SUMMARY)

M1C commit `02b68ce` đã hoàn tất chính xác và đầy đủ các thực thể ASR (107,540 câu thoại / 873 video) và OCR keyframe coverage (116,767 keyframes / 873 video). Tuy nhiên, nghiệm thu cấp độ dữ liệu thô (Level B & Level C) yêu cầu đọc trực tiếp các file vật lý từ `AIC_2026/ocr_results` và `AIC_2026/ocr_single_text_retrieval`. Do các thư mục này chưa được đồng bộ từ Google Drive về máy cục bộ, hệ thống tuân thủ nguyên tắc fail-closed: **Tạm hoãn nghiệm thu M1C cho đến khi có quyền truy cập đĩa vật lý, không giả lập số liệu.**

Chi tiết xem tại: [`docs/retrieval_v2/M1C_R1_OCR_BGE_REAL_MAPPING_RESULT.md`](file:///F:/AIC_DEV/aic2026/docs/retrieval_v2/M1C_R1_OCR_BGE_REAL_MAPPING_RESULT.md).
