# AIC 2026 — Báo Cáo Hoàn Tất M1C: ASR + OCR Canonical Mapping

> **Milestone:** M1 — Data Hub & Unified Mapping  
> **Slice:** M1C — ASR + OCR Canonical Mapping (Hoàn tất xác thực M1C-R1)  
> **Thời gian thực hiện:** 2026-08-18  
> **Acceptance Verdict:** **PASS**  
> **M1D Ready:** **YES**

---

## 1. TỔNG QUAN KẾT QUẢ M1C (EXECUTIVE SUMMARY)

| Chỉ số / Hạng mục | Kết quả đạt được | Trạng thái |
|---|:---:|:---:|
| **ASR Video Manifest Rows** | **873** | ✅ Khớp 100% video vũ trụ M1A |
| **Unique ASR Video IDs** | **873** | ✅ Độc bản |
| **ASR Segments (Câu thoại)** | **107,540** | ✅ Khớp 100% |
| **Unique ASR Segment IDs** | **107,540** (`ASR:{video_id}:{source_segment_id}`) | ✅ 100% Unique |
| **ASR Duplicate Segment IDs** | **0** | ✅ 0 duplicate |
| **Videos có $\ge 1$ câu thoại (HAS_SEGMENTS)** | **859** | ✅ Khớp 100% |
| **Zero-ASR Videos (ZERO_ASR_SEGMENTS)** | **14** (L24: 13, L30: 1) | ✅ Được bảo toàn nguyên vẹn, không coi là lỗi |
| **Invalid ASR Intervals ($end\_ms < start\_ms$ / negative)** | **0** | ✅ Khoảng thời gian hợp lệ 100% |
| **Empty ASR Transcripts (Câu thoại rỗng)** | **0** | ✅ 100% có text hợp lệ |
| **ASR Unknown Videos** | **0** | ✅ Khớp video_ordinal M1A |
| **ASR Canonical Checksum** | `4816759e565dcb371b9ff6ca51b01e6029a13795bd87a30d952206633ab4527b` | ✅ Khóa mã băm |
| **OCR Keyframe Manifests** | **116,767** | ✅ 100% frame CUSTOM |
| **OCR Mapped CUSTOM Keyframes** | **116,767** | ✅ Khớp 100% không gian M1B |
| **OCR Missing / Extra CUSTOM Keyframes** | **0 / 0** | ✅ Giao thoa hoàn hảo 1:1 |
| **OCR Covered Videos** | **873** | ✅ Đầy đủ 873 video |
| **Raw OCR Text Items (Toàn vũ trụ raw)** | **676,925** | ✅ Quét trực tiếp 116,767 JSON gốc |
| **Raw OCR Items Conf $\ge 0.5$** | **658,003** | ✅ Tập tin cậy cao |
| **Raw OCR Items Conf $< 0.5$** | **18,922** | ✅ Bảo toàn phát hiện raw ($0.3 \le score < 0.5$) |
| **Raw Items Không Có Dense Vector** | **64,112** | ✅ $676,925 - 612,813 = 64,112$ |
| **OCR Canonical Checksum** | `0f8dd9f48bdb4779436ea83d2eb84ae048ed4a0ff7b3b7c2a9818d690ff00759` | ✅ Khóa mã băm |
| **OCR BGE-M3 Dense Model Passport** | BAAI/bge-m3, 1024D, normalized=True | ✅ Đọc trực tiếp từ đĩa |
| **OCR BGE-M3 Shards Verified** | **10 / 10** | ✅ Khớp shape & metadata 100% |
| **OCR BGE-M3 Vector Rows** | **612,813** | ✅ Khớp nối 1:1 sang raw canonical items |
| **OCR BGE-M3 Unmapped / Ambiguous** | **0 / 0** | ✅ 0 lỗi ánh xạ |
| **OCR BGE Rowmap Checksum** | `4cc7cb5f1d359e3033df8b52d5341b39e23f61ac478ccafbaf317cf7579300b7` | ✅ Khóa mã băm |
| **Producer Input Manifest SHA-256** | `c05599c2d1f8dfb2029f8e5008234b0bafaf88d5fb2dae4df36d07d9a3ef9616` | ✅ `ocr_manifest.json` |
| **Đột biến dữ liệu gốc (Raw Mutation)** | **0** (Hoàn toàn read-only/immutable) | ✅ Bất biến |
| **Inference / Embedding Rerun** | **0** | ✅ Zero rerun |
| **Targeted Tests Passed** | **15 / 15** | ✅ 100% PASS |
| **Full Pytest Suite Passed** | **218 / 218** in 13.43s | ✅ 100% PASS |

---

## 2. PHÂN BỔ 14 ZERO-ASR VIDEOS (ZERO ASR SUMMARY)

1. `L24_V008` (Series L24 - Múa lân / Nhạc nền không lời)
2. `L24_V013` (Series L24)
3. `L24_V015` (Series L24)
4. `L24_V016` (Series L24)
5. `L24_V019` (Series L24)
6. `L24_V021` (Series L24)
7. `L24_V027` (Series L24)
8. `L24_V028` (Series L24)
9. `L24_V029` (Series L24)
10. `L24_V031` (Series L24)
11. `L24_V033` (Series L24)
12. `L24_V038` (Series L24)
13. `L24_V043` (Series L24)
14. `L30_V029` (Series L30 - Video phóng sự không có lời thoại)

**Tổng phân bổ:** Series L24: 13 video; Series L30: 1 video. Tổng cộng: **14 video**.

---

## 3. GHI CHÚ ĐIỀU CHỈNH NGHIỆM THU M1C-R1

M1C commit `02b68ce` đã hoàn tất chính xác phần ASR và OCR keyframe coverage, nhưng phần nghiệm thu BGE và raw text items ban đầu dựa trên passport specification. M1C-R1 đã thực hiện đọc trực tiếp (Direct Source Read) toàn bộ 10 file `.npy` (2.5GB) và 10 file `.json`, xác minh độ dài vector 1024D, chuẩn hóa L2 norm 1.0000, ánh xạ chính xác 612,813 vector rows sang canonical OCR items mà không có bất kỳ hàng nào bị thiếu (unmapped = 0, ambiguous = 0).

Chi tiết đối soát 10 shards xem tại: [`docs/retrieval_v2/M1C_R1_OCR_BGE_REAL_MAPPING_RESULT.md`](file:///F:/AIC_DEV/aic2026/docs/retrieval_v2/M1C_R1_OCR_BGE_REAL_MAPPING_RESULT.md).

---

## 4. BƯỚC TIẾP THEO

- M1C & M1C-R1 hoàn tất xuất sắc toàn bộ tiêu chuẩn acceptance.
- Bước kế tiếp: **`M1D — BTC Keyframe + Map + CLIP + Object + Media Mapping`** (theo `plan/01_DATA_HUB_MAPPING.md`).
