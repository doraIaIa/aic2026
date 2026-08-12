# Unified Retrieval Contract v1

Backend Python là authority duy nhất cho retrieval contract. JSON Schema, policy và fixtures nằm tại `src/aic2026/retrieval/contracts/v1`. Frontend type phải được sinh bằng `scripts/generate_retrieval_contract_types.py`; không duy trì interface song song bằng tay.

## Policy đã khóa

- Product FTS dùng literal/all-token mặc định và giữ phrase được đặt trong dấu ngoặc kép. Raw FTS syntax chỉ thuộc diagnostic CLI.
- Window anchor: Visual dùng `pts_time`; ASR/OCR dùng midpoint. Chỉ merge trong cùng `video_id`; span tối đa 12 giây và không union-chain vô hạn.
- RRF dùng `k=60`, equal lane weights trước khi có DEV labels. Mỗi window collapse về best rank của từng lane trước fusion; `evidence_id` phải duy nhất; tie-break ổn định.
- ASR/OCR chỉ là temporal anchor. `submit_valid` chỉ xác nhận mapping/provenance hợp lệ và luôn cần operator confirm frame.
- V1 `POST /search` trả đầy đủ evidence; chưa có stateless `GET /evidence/{window_id}`.
- Media root lấy từ `AIC_MEDIA_ROOT` hoặc `paths.data_root`, chỉ đọc ở backend và không lộ absolute path. Chưa mount thì capability là `MEDIA_UNAVAILABLE`.
- OCR/Object chưa có artifact phải trả `UNAVAILABLE` với count 0; không trả mock.

## Sinh frontend type

```powershell
python scripts/generate_retrieval_contract_types.py `
  --out F:\aic-video-search-demo\shared\retrieval-contract.generated.ts
```

Header generated file chứa `contract_version`, `policy_version` và checksum toàn bộ JSON contract. Phase 0 chỉ khóa contract; chưa triển khai provider hoặc orchestrator.
