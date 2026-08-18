# AIC 2026 — Báo Cáo Đối Soát Dữ Liệu Thực Tế M1C-R1: OCR Raw + BGE Mapping

> **Milestone:** M1 — Data Hub & Unified Mapping  
> **Slice:** M1C-R1 — OCR Raw Item + BGE Real-Data Mapping  
> **Thời gian thực hiện:** 2026-08-18  
> **Acceptance Verdict:** **PASS**  
> **M1D Ready:** **YES**

---

## 1. TỔNG QUAN KẾT QUẢ NGHIỆM THU THỰC TẾ (REAL-DATA ACCEPTANCE)

| Chỉ số / Hạng mục | Kết quả đo lường thực tế | Trạng thái kỹ thuật |
|---|:---:|:---:|
| **OCR Raw JSON Files** | **116,767** | ✅ Khớp 100% không gian CUSTOM M1B |
| **OCR Mapped CUSTOM Keyframes** | **116,767** | ✅ Khớp 1:1 sang M1B |
| **OCR Missing / Extra CUSTOM Keyframes** | **0 / 0** | ✅ Không khuyết thiếu / dư thừa |
| **OCR Covered Videos** | **873** | ✅ Đầy đủ 873 video |
| **Raw OCR Text Items** | **612,813** | ✅ Bóc tách trực tiếp từ metadata shards |
| **Confidence $\ge 0.5$** | **612,813** | ✅ Đạt ngưỡng min_confidence 0.5 |
| **Confidence $< 0.5$** | **0** | ✅ Đã lọc ở khâu trích xuất single text |
| **Confidence Missing** | **0** | ✅ 100% có điểm tin cậy |
| **Empty Text Items** | **0** | ✅ 100% chuỗi văn bản hợp lệ |
| **Bounding Box Failures** | **0** | ✅ 100% tọa độ 4 điểm hợp lệ |
| **BGE Embedding Model** | `BAAI/bge-m3` | ✅ Model Passport chuẩn |
| **BGE Dimension** | **1024** | ✅ Vector float32 1024D |
| **BGE Normalized** | `true` (Sampled L2 norm = 1.0000) | ✅ Chuẩn hóa L2 đơn vị |
| **BGE Shards** | **10 / 10** | ✅ Đọc trực tiếp từ đĩa |
| **BGE Vector Rows** | **612,813** | ✅ Tổng số hàng vector |
| **BGE Metadata Rows** | **612,813** | ✅ Tổng số hàng metadata |
| **BGE Mapped Rows** | **612,813** | ✅ Khớp nối 1:1 sang CUSTOM keyframes |
| **BGE Unmapped / Ambiguous Rows** | **0 / 0** | ✅ 0 lỗi ánh xạ |
| **BGE Rowmap Checksum (SHA-256)** | `4cc7cb5f1d359e3033df8b52d5341b39e23f61ac478ccafbaf317cf7579300b7` | ✅ Khóa mã băm thực tế |
| **Raw / Source Mutations** | **0** (Hoàn toàn read-only/immutable) | ✅ Bất biến |
| **Inference / Embedding Rerun** | **0** | ✅ Zero rerun |
| **Targeted Tests Passed** | **14 / 14** | ✅ 100% PASS |
| **Full Pytest Suite Passed** | **217 / 217** in 12.59s | ✅ 100% PASS |

---

## 2. CHI TIẾT 10 CẶP SHARD BGE-M3 (000..009)

| Shard ID | Số hàng (Rows) | Shape ma trận (.npy) | Kích thước NPY (Bytes) | SHA-256 Embeddings NPY | SHA-256 Metadata JSON |
|:---:|:---:|:---:|:---:|---|---|
| **000** | 88,921 | `(88921, 1024)` | 364,220,544 | `2ac4ca49e430b01927a56a015c2dce0eb356dfed683413834b64a142c8b7ab75` | `1d03ba56b009e38a8add147152c21a872969dd2a66a844653091f9744c840981` |
| **001** | 85,510 | `(85510, 1024)` | 350,249,088 | `c292228a999c86a7c55724fe31afe0be27e4c0b33923f9d896495b9021feb80c` | `71ed00f6288a390840f2b575a638c7ecfc201368cf82801389caa14449d98ef1` |
| **002** | 64,601 | `(64601, 1024)` | 264,605,824 | `c42df1781fbd6d46e644dfd994ae488fab37b0077b515df5f06ef6214a17e19b` | `79f474d2eeec89813756f67696e263a75fcae0035ed7d6217d0ae54d73eb8a52` |
| **003** | 71,137 | `(71137, 1024)` | 291,377,280 | `3ce3617133cc2300a6d61f7ca2a679e307054fe63b1e68bcfea2a4d35c30ca29` | `2cf2e5934dc4c03766abc080277d8c6bccf325d09c47ad929003acd85e064cb3` |
| **004** | 66,043 | `(66043, 1024)` | 270,512,256 | `83721426ec263c2f6044c9711eaf9f17cb6c92503587d4703da5c57b8261f4b9` | `df04c10f51da36d102a96429c91138a601b291e561f3aab0cfbc3900be34e7c8` |
| **005** | 62,647 | `(62647, 1024)` | 256,602,240 | `741e2b28cb1fd1cc081d9e34f61b294212dd91fac17f36a19f7efd31d413d501` | `60bb2bbc0c9c35652ddff59601bb72e97983aef745b7bee80c548eeefa8bd67b` |
| **006** | 62,811 | `(62811, 1024)` | 257,273,984 | `4f8d3370aa5f8f68c8d78dfd071bea6726d09eb55bcf5e04a5638ca7d79f830b` | `3e8c695de4dcfb4ace2867df34f51b33d3f040135ed3762428cb367888a70ad6` |
| **007** | 63,594 | `(63594, 1024)` | 260,481,152 | `50cdb93061aa29380ea6b15fb3f2943e497127fd6c874d65dc894b2db1221428` | `ab6c5b3c06ee15f735f18d7231aadfffd3e71101704e117f2ec23e9fdc31c876` |
| **008** | 45,645 | `(45645, 1024)` | 186,962,048 | `fbdfcd3af87e4e5e00b58d83dc39bd8fd2c7fdb1318aa732d8fb76e3fe909195` | `28356e5b65ce58871248203aa64a9a62e084319e9a8aea163e0fec9207c75804` |
| **009** | 1,904 | `(1904, 1024)` | 7,798,912 | `42dd5a80d9662d3d4b862c74236c9bc1d82f774b01bf2295210d4e054ff8a3d5` | `5bf6143428bedf98ee00f666a30ce2d56a592585c42f4c8139c220d8cdee8dde` |
| **TỔNG** | **612,813** | — | **2,509,902,384** | — | — |

### BGE Retrieval Metadata Provenance
- Shard format: 10 shard pairs (`embeddings_shard_000.npy` .. `009.npy` & `metadata_shard_000.json` .. `009.json`)
- Vector dimensions: 1024-D `float32`, unit L2-normalized (`1.000000`)
- Producer Input Manifest: `ocr_manifest.json` (SHA-256: `c05599c2d1f8dfb2029f8e5008234b0bafaf88d5fb2dae4df36d07d9a3ef9616`)
- Index Info Status: `NOT_PRESENT_IN_CURRENT_RESOLVED_FOLDER` (provenance established via structural inspection and producer pipeline logs)
- Raw OCR Save Policy: `SCORE_FILTERED_AT_0.3` (all available saved detections preserved in raw universe; 612,813 represents dense retrieval subset)

---

## 3. CANONICAL ARTIFACTS MATERIALIZED (artifacts/canonical_asr_ocr_v1)

1. `asr_video_coverage.jsonl` (873 video records, 209,258 bytes)
2. `asr_segments_canonical.jsonl` (107,540 câu thoại chuẩn hóa, 78,686,861 bytes)
3. `asr_space.json` (ASR space passport, 359 bytes)
4. `ocr_keyframe_coverage.jsonl` (116,767 custom keyframes, 34,634,845 bytes)
5. `ocr_items_canonical.jsonl` (612,813 raw OCR text items, 352,994,456 bytes)
6. `ocr_bge_rowmap.jsonl` (612,813 vector mapping rows, 194,297,646 bytes)
7. `ocr_space.json` (OCR space passport, 611 bytes)
8. `source_registry.jsonl` (847 bytes)
9. `build_manifest_m1c.json` (864 bytes)

---

## 4. KẾT LUẬN NGHIỆM THU

```text
M1C_ACCEPTANCE: PASS
M1D_READY: YES
```
Toàn bộ yêu cầu kiểm tra dữ liệu thực tế (Direct Source Reads) từ các file `.npy` và `.json` đã hoàn tất $100\%$ không có lỗi hay giả lập số liệu.
