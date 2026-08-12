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

## Phase 1 provider layer

- `AsrProvider` chỉ gọi production authority `aic2026.search.asr` trên SQLite mở read-only. Product query được biên dịch theo FTS policy v1; raw FTS vẫn chỉ thuộc diagnostic CLI.
- `VisualProvider` xác minh `DONE.json`, checksum index/metadata, count, dimension, stable embedding ID và mapping `csv_n ↔ clip_row ↔ keyframe ordinal` trước khi lane `OK`.
- OpenCLIP model, tokenizer, metadata và FAISS index được lazy-load một lần cho application lifecycle. Một lock serialize text encoding + FAISS search; raw cosine/BM25 không được so sánh trong provider layer.
- `GET /api/v1/capabilities` chỉ báo trạng thái thật của provider/media. Endpoint chưa search đa phương thức và chưa fusion.

## Phase 2 orchestrator

- `POST /api/v1/search` nhận `SearchRequest` và trả đầy đủ `SearchResponse.results: EvidenceWindow[]`; không có stateless detail endpoint.
- Auto route có reason cố định `baseline_all_available_v1` và chạy mọi provider đang `OK`; manual route chỉ load/chạy lane được bật.
- Provider chạy bounded concurrency. Timeout/lỗi một lane trả `PARTIAL`; không còn lane thành công trả `ERROR` trong response.
- Windowing dùng biên inclusive 4 giây, span tối đa 12 giây, cùng video, deduplicate `(modality, evidence_id)` và ID băm deterministic.
- RRF equal-weight `k=60` chỉ lấy best rank từng lane trong mỗi window; mọi evidence vẫn được giữ để giải thích.
- OpenAPI companion: `docs/openapi-retrieval-v1.yaml`. JSON Schema/policy backend vẫn là authority.
