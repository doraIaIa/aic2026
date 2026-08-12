# Project State

**Current Phase:** M2-ASR PILOT / Evaluation metric vẫn bị chặn bởi ground truth

## What is done
- M0 reliability scaffold (checkpointing/resume validation).
- Keyframe/CSV/CLIP mapping contract fix.
- 20-video real-data mapping validation.
- M1 nạp CLIP + baseline FAISS: 177.321 vector, dimension 512.
- Truy hồi text-to-keyframe dùng OpenCLIP `ViT-B-32`, pretrained `openai`, đúng theo notebook baseline BTC.
- Evaluation contract version 1, KIS scorer và CLIP-only runner đã hoàn tất.
- Production-index smoke run: 1 unlabeled, 0 failed, quality status `BLOCKED_BY_GROUND_TRUTH`.
- Đã import 35 Group A query text: 29 KIS, 4 QA, 2 TRAKE; tất cả là `unlabeled_reference`.
- Group A baseline top-100: 35/35 query thành công, 3.500 predictions, p50 291,66 ms, p95 377,56 ms.
- Candidate review artifact và failure sheet đã sẵn sàng tại `F:\AIC_WORK\artifacts\evaluation\group-a-review-v1`.
- M2-ASR pilot pipeline đã sẵn sàng: faster-whisper `medium`, tiếng Việt, resume/checksum/DONE, merge và SQLite FTS5.
- Group A ASR pilot manifest có 95 video unique từ top-20 candidates; kế hoạch chính dùng 2 worker: Colab 48 video và Kaggle 47 video.
- Full-corpus ASR đã merge đủ 873 video / 107.540 segments; SQLite FTS5 search index tại `F:\AIC_WORK\db\aic.sqlite` đã PASS integrity/count/smoke tests.
- CLI ASR search hỗ trợ BM25, phrase query, `video_id` filter, JSON output và tìm tiếng Việt không dấu qua `unicode61 remove_diacritics 2`.

## What is not done
- Gắn ground truth có provenance cho 35 query Group A và phân loại trap category.
- DEV/HOLDOUT Recall@1/5/20/50/100 và failure analysis.
- QA/TRAKE scorer chính thức do chưa có scoring contract.
- Đánh giá retrieval usefulness của ASR trên query thật và chuẩn bị fusion có kiểm chứng.
- OCR, SigLIP và Objects extraction.
- TRAKE retrieval logic.
- Application UI.

## Accepted dataset facts
1. Canonical videos: 873.
2. Valid BTC keyframes: 177,321.
3. CSV schema: `n, pts_time, fps, frame_idx`
4. Keyframe filenames are 1-based ordinals (e.g., `001.jpg`, `002.jpg`, ...).
5. Keyframe filename ordinal maps exactly to `CSV.n`.
6. `CSV.frame_idx` is the original-video frame index.
7. `frame_idx` is NOT the keyframe filename. There is NO requirement for `000000.jpg`.
8. CLIP row index is 0-based: `clip row 0 ↔ CSV.n=1 ↔ keyframe 001.jpg`.
9. Objects are partial and optional.
10. OpenCV `CAP_PROP_POS_FRAMES` is not authoritative for exact frame extraction.
11. PTS-based FFmpeg extraction is the accepted exact-frame method from prior V4 audit.

## Current risks
- The dataset scale is significant, and I/O latency to Google Drive is high. Any full traversal requires caching or batched logic.

## Next Phase
- Dùng ASR CLI trên query thật, review false positives/phrase behavior và đo usefulness trước fusion.
- Song song: gắn ground truth có provenance để đo CLIP-only và +ASR khi dữ liệu nhãn sẵn sàng.

> [!CAUTION]
> **M2 scope:** Chỉ ASR pilot đã được mở. Chưa bắt đầu OCR, SigLIP, Objects, TRAKE production hoặc UI.
