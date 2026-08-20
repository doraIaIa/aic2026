# Codex taxonomy/runtime UI completion result

Ngày kiểm chứng: 2026-08-20

## Kết luận

PASS cho phạm vi sửa lần này:

- 873 canonical videos được giữ theo runtime recovery authority.
- Taxonomy API trả `global_count = 873`, `programs = 9`, `topics = 9`.
- 12/12 retrieval providers HEALTHY sau restart backend.
- 12/12 retrieval providers search smoke OK sau restart backend.
- Program/Topic pruning tạo `candidate_video_ids` thật trước retrieval; case Topic Ngữ văn trả 0 leakage.
- Result previews của ASR BM25 trong UI không còn blank: 9/9 preview image loaded, kích thước 1280×720.
- Preview smoke trực tiếp trên 24 sample hits từ 12 lane: 0 failure.
- Inspector/video cho result canonical L25 phát được: video element `readyState = 4`, không `VIDEO_UNAVAILABLE`.
- Single unified search PASS sau khi ASR adapter được nối sang schema canonical.
- Compare API PASS.
- Sequence API PASS.
- Frontend viewport screenshots có bằng chứng cho 1920×1080, 1440×900, 1366×768.

## Root cause đã sửa

1. Unified Single path vẫn dùng `AsrProvider` legacy và đọc bảng `asr_segments/asr_segments_fts`.
   Runtime recovery authority hiện dùng `canonical_asr_segments/asr_fts`, nên Single trả `ASR_INTEGRITY_ERROR`.
   Fix: `AsrProvider` tự nhận diện schema canonical và dùng backend `AsrBm25Provider`, nhưng vẫn trả modality `asr` đúng retrieval.v1 contract.

2. Program/Topic pruning chưa được expose thành API/runtime scope ổn định cho frontend.
   Fix: thêm `/api/v1/taxonomy`, frontend load taxonomy, Program/Topic select sinh `filters.video_ids`/`candidate_video_ids` thật cho Single/Compare/Sequence/direct lanes.

3. ASR/OCR/Qwen fallback preview trước đó có thể đoán sai ordinal keyframe.
   Fix: thêm `/api/v1/media/{video_id}/preview-keyframe?target_ms=...&space=CUSTOM|BTC` và frontend dùng nearest keyframe theo timestamp thay vì tự đoán ordinal.

4. CUSTOM rowmap thiếu `local_keyframe_no` trong một số artifact.
   Fix: nearest keyframe resolver derive keyframe number từ `csv_n`, `keyframe_no`, `keyframe_id`, hoặc `image_relpath`.

5. UI provider status trước đây có thể hiển thị theo capability legacy 4 modality.
   Fix: frontend hiển thị health chi tiết 12 lane khi endpoint lane health có dữ liệu.

## Artifact bằng chứng

Run root:

`F:\AIC_WORK\artifacts\retrieval_v2\codex_ui_repair\codex_ui_repair_20260820_162919`

Các file chính:

- `taxonomy_inventory.json`
- `pruning_cases.jsonl`
- `provider_smokes.jsonl`
- `preview_smokes.jsonl`
- `single_smoke.json`
- `workflow_smokes.json`
- `ui_viewports.json`
- `inspector_smokes.jsonl`
- `summary.json`
- `DONE`
- `screenshots/`

## Regression

- Backend: `410 passed, 2 skipped`
- Frontend unit: `67 passed`
- Frontend typecheck: PASS
- Frontend build: PASS
