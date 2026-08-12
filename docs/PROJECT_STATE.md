# Project State

**Current Phase:** PHASE 4 – MEDIA + EXACT-FRAME EVIDENCE INSPECTOR

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
- Local read-only ASR HTTP API đã nối trực tiếp với search core; demo React/Vite riêng đã dùng API thật tại `http://localhost:3000`.
- ASR route hiện chỉ là diagnostic/smoke UI; không phải product architecture.
- Unified retrieval contract/policy v1 đã khóa bằng JSON Schema, backend validation, fixtures và generated frontend type có checksum.
- Demo frontend đã có local Git baseline; `/prototype` là product shell sẽ migrate sau khi backend provider/orchestrator hoàn tất.
- Phase 1 provider layer đã có ASR/Visual adapters, cached OpenCLIP/FAISS lifecycle và `GET /api/v1/capabilities`.
- Production capability smoke: ASR 873 video/107.540 segment/FTS rows; Visual 177.321 vector, dimension 512; checksum đúng marker. OCR/Object vẫn `UNAVAILABLE`; media hiện `MEDIA_UNAVAILABLE`.
- Phase 2 unified orchestrator đã có auto/manual routing, bounded provider concurrency, deterministic EvidenceWindow, anti-chain windowing và per-lane collapsed RRF.
- `POST /api/v1/search` đã chạy production smoke ASR-only, Visual-only và auto Visual+ASR. Đây là integrity/schema/latency smoke, không phải quality benchmark.
- Phase 3: product UI đã migrate, mock đã loại bỏ hoàn toàn, `/` là SearchWorkspace thật, `/prototype` redirect. TypeScript PASS, 11/11 test PASS, build PASS. Commit: `251c0c3`.
- Phase 4: Media module (`src/aic2026/media/`): resolver, api_handler, 4 endpoints mới (`/info`, `/stream`, `/frames/{id}`, `/resolve-frame`). Path traversal blocked. Absolute path không bao giờ ra ngoài. Media capability live. 3 video smoke: L21_V001/L25_V007/L30_V009 PASS.
- Phase 4: TRAKE scorer chính thức implement per BTC spec: R-Score = matched_events / N, R@k = max R-Score top-k, Final Score = mean(R@1..R@100). 36 backend tests PASS, 12 frontend tests PASS.
- Phase 4: Evidence Inspector mới: video player thật (seek tới anchor), exact-frame controls (±1/±10), KIS/QA/TRAKE candidate builder, mixed-video guard, candidate list tối đa 100.

## What is not done
- Gắn ground truth có provenance cho 35 query Group A và phân loại trap category.
- DEV/HOLDOUT Recall@1/5/20/50/100 và failure analysis.
- QA semantic answer scorer: vẫn `BLOCKED_BY_SEMANTIC_ANSWER_CONTRACT` do chưa có official normalization.
- OCR, SigLIP và Objects extraction.
- TRAKE retrieval logic (ASR/CLIP retrieval đã có; TRAKE-specific chưa).
- Dense-frame verification qua ffmpeg decode (hiện dùng fps-based PTS).
- VFR video support trong resolve-frame (CFR đã covered).

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
- Phase 5 (nếu cần): Gắn ground truth, đo Recall@k thật, failure analysis.
- Hoặc: Dense-frame decode qua ffmpeg/PTS walk cho VFR video; operator frame selection refinement.
- Song song: OCR extraction nếu dataset có text; SigLIP reranking nếu muốn nâng quality.

> [!CAUTION]
> **Product direction:** Không phát triển thêm UI ASR riêng. ASR FTS5 là provider đã PASS. ASR/OCR không tự mở submit gate; frame phải có mapping visual/dense hợp lệ và operator xác nhận.
