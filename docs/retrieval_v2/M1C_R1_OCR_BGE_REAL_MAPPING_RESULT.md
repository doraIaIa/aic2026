# AIC 2026 — Báo Cáo Đối Soát Thực Tế M1C-R1: OCR Raw + BGE Mapping

> **Milestone:** M1 — Data Hub & Unified Mapping  
> **Slice:** M1C-R1 — OCR Raw Item + BGE Real-Data Mapping Audit  
> **Thời gian thực hiện:** 2026-08-18  
> **Acceptance Verdict:** **BLOCKED_BY_OCR_ARTIFACT_ACCESS**  
> **M1D Ready:** **NO**

---

## 1. BỐI CẢNH & HIỆU CHỈNH KẾT QUẢ M1C

- **Trạng thái đã hoàn tất & bảo toàn thành công:**
  - **ASR Speech Intervals:** 873 video manifest rows, 107,540 câu thoại, 859 video có thoại, 14 video `ZERO_ASR_SEGMENTS`, 0 câu thoại lỗi khoảng thời gian, checksum ASR chuẩn xác: `4816759e565dcb371b9ff6ca51b01e6029a13795bd87a30d952206633ab4527b`.
  - **OCR Keyframe Coverage (Level A):** 116,767 / 116,767 custom keyframes khớp 1:1 sang không gian M1B qua 873 video, checksum: `83df83aac663de5f86f196e0121b94566d8a5d400d8fd896303da8122bd5c710`.
- **Lý do điều chỉnh (Correction Note):**
  - Commit `02b68ce` đã hoàn tất ASR và OCR keyframe coverage, nhưng phần nghiệm thu BGE và raw text items ban đầu dựa trên schema/passport định danh thay vì đọc dữ liệu trực tiếp từ các file trích xuất trên đĩa.
  - M1C-R1 thực hiện kiểm tra vật lý trực tiếp nguồn dữ liệu thô (Direct Source Read).

---

## 2. CHẨN ĐOÁN TRUY CẬP DỮ LIỆU THỰC TẾ (RUNTIME SOURCE DIAGNOSTICS)

| Mục kiểm tra | Đường dẫn logic (Logical Ref) | Trạng thái vật lý trên máy |
|---|---|:---:|
| **Resolved OCR Raw Root** | `AIC_2026/ocr_results` | ❌ `False` (Chưa đồng bộ về đĩa) |
| **Resolved OCR Dense Root** | `AIC_2026/ocr_single_text_retrieval` | ❌ `False` (Chưa đồng bộ về đĩa) |
| **Raw Root Exists** | — | `False` |
| **Dense Root Exists** | — | `False` |
| **Number of Raw OCR JSONs** | — | `0` |
| **index_info Candidates** | — | `0` |
| **Embedding Shard Files (.npy)**| — | `0 / 10` |
| **Metadata Shard Files (.json)** | — | `0 / 10` |

---

## 3. HÀNH ĐỘNG CẦN THIẾT ĐỂ MỞ KHÓA (UNBLOCK INSTRUCTIONS)

Để hệ thống có thể đọc trực tiếp và nghiệm thu 100% dữ liệu thực tế (612,813 vector rows và raw OCR text items):

1. Mở **Google Drive Web** (tài khoản nhóm AIC).
2. Vào mục **"Được chia sẻ với tôi" (Shared with me)**.
3. Tìm 2 thư mục:
   - `ocr_results` (chứa các file JSON bóc tách OCR theo từng video).
   - `ocr_single_text_retrieval` (chứa 10 cặp file `embeddings_shard_XXX.npy` + `metadata_shard_XXX.json` và `index_info.json`).
4. Nhấp chuột phải $\rightarrow$ Chọn **"Thêm lối tắt vào Drive" (Add shortcut to Drive)** $\rightarrow$ Chọn thư mục đích là `AIC_2026`.
5. Sau khi *Google Drive for Desktop* đồng bộ về máy cục bộ, chạy lệnh kiểm tra và tiến hành nghiệm thu M1C-R1.

---

## 4. KẾT LUẬN & ĐIỀU KIỆN TIẾP TỤC

```text
M1C_ACCEPTANCE: BLOCKED_BY_OCR_ARTIFACT_ACCESS
M1D_READY: NO
```
*(Hệ thống tuân thủ nguyên tắc fail-closed: Không giả lập số liệu, không tiếp tục sang M1D cho đến khi nguồn dữ liệu vật lý được xác thực trực tiếp).*
