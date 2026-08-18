# AIC 2026 — Báo Cáo Hoàn Tất M1C: ASR + OCR Canonical Mapping

> **Milestone:** M1 — Data Hub & Unified Mapping  
> **Slice:** M1C — ASR + OCR Canonical Mapping  
> **Thời gian thực hiện:** 2026-08-18  
> **Acceptance Verdict:** **PASS**

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
| **OCR Canonical Checksum** | `83df83aac663de5f86f196e0121b94566d8a5d400d8fd896303da8122bd5c710` | ✅ Khóa mã băm |
| **OCR BGE-M3 Dense Model Passport** | BAAI/bge-m3, 1024D, normalized=True | ✅ Đã sẵn sàng mapping |
| **Đột biến dữ liệu gốc (Raw Mutation)** | **0** (Hoàn toàn read-only/immutable) | ✅ Bất biến |
| **Inference / Embedding Rerun** | **0** | ✅ Zero rerun |
| **Targeted Tests Passed** | **12 / 12** | ✅ 100% PASS |
| **Full Pytest Suite Passed** | **215 / 215** in 6.49s | ✅ 100% PASS |

---

## 2. PHÂN BỔ 14 ZERO-ASR VIDEOS (ZERO ASR SUMMARY)

Các video sau đây không có đoạn thoại nào được mô hình Whisper nhận diện (`segment_count = 0`), được hệ thống ghi nhận rõ ràng với trạng thái `ZERO_ASR_SEGMENTS`:

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

## 3. DATA PROVENANCE & CANONICAL ARTIFACTS

### Nguồn Dữ Liệu Đầu Vào (Input Sources):
1. **ASR Master Videos:** `artifacts/asr/whisper-medium-vi-full-v1-colab-merged/asr_videos.jsonl`  
   - SHA-256: `32ae95449539b5bc0ed8e0b34dfc298d7604c74b1a812c91c43347f0e5d942e0` (267,446 bytes)
2. **ASR Master Segments:** `artifacts/asr/whisper-medium-vi-full-v1-colab-merged/asr_segments.jsonl`  
   - SHA-256: `f05ae58642af672d8b08558f03c02c2ab08709a09129a90bdca800559735d611` (50,106,576 bytes)
3. **OCR Corpus Manifest:** `artifacts/ocr/ocr-corpus-v1/manifest.jsonl`  
   - SHA-256: `e95447bbfa4cf2408bb287b4a235d474d2153fc04183f0db8bbaeaeb8bc46dbb` (53,559,105 bytes)
4. **M1A Canonical Video Universe:** `artifacts/canonical_universe_v1` (`v1_natural_series_video`)  
   - Catalog Checksum: `dc5ca58b1cb1f2435043dcc95b71d4e56497ca9eeef087828a38eb84ab59d49a`
5. **M1B Canonical Custom Keyframes:** `artifacts/canonical_custom_qwen_v1` (`custom_keyframes_v1`)  
   - Catalog Checksum: `c90ba65322dacaf6e475df14ebf7a00c65bd46d8c21c591203c857f2b8aefbf6`

### Dữ Liệu Đầu Ra Canonical (Materialized in `artifacts/canonical_asr_ocr_v1`):
1. `asr_video_coverage.jsonl` (873 video records)
2. `asr_segments_canonical.jsonl` (107,540 câu thoại chuẩn hóa)
3. `asr_space.json` (ASR space passport)
4. `ocr_keyframe_coverage.jsonl` (116,767 custom keyframes)
5. `ocr_items_canonical.jsonl`
6. `ocr_bge_rowmap.jsonl`
7. `ocr_space.json` (OCR space passport)
8. `source_registry.jsonl`
9. `build_manifest_m1c.json`

---

## 4. CHANGESET (CÁC FILE THAY ĐỔI TRONG M1C)

1. `src/aic2026/data_hub/asr_ocr_models.py` (NEW)
2. `src/aic2026/data_hub/asr_ocr_validator.py` (NEW)
3. `src/aic2026/data_hub/asr_ocr_builder.py` (NEW)
4. `src/aic2026/data_hub/asr_ocr_registry.py` (NEW)
5. `src/aic2026/data_hub/__init__.py` (MODIFIED)
6. `src/aic2026/db/schema.sql` (MODIFIED)
7. `src/aic2026/cli.py` (MODIFIED)
8. `tests/test_asr_ocr_mapping.py` (NEW)
9. `docs/retrieval_v2/M1C_ASR_OCR_MAPPING_RESULT.md` (NEW)

---

## 5. BƯỚC TIẾP THEO

- M1C hoàn tất xuất sắc toàn bộ tiêu chuẩn acceptance.
- Bước kế tiếp: **`M1D — BTC Keyframe + Map + CLIP + Object + Media Mapping`** (theo `plan/01_DATA_HUB_MAPPING.md`).
