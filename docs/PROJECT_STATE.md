# Project State

**Current Phase:** Evaluation Closure PARTIAL / metric chất lượng bị chặn bởi ground truth

## What is done
- M0 reliability scaffold (checkpointing/resume validation).
- Keyframe/CSV/CLIP mapping contract fix.
- 20-video real-data mapping validation.
- M1 nạp CLIP + baseline FAISS: 177.321 vector, dimension 512.
- Truy hồi text-to-keyframe dùng OpenCLIP `ViT-B-32`, pretrained `openai`, đúng theo notebook baseline BTC.
- Evaluation contract version 1, KIS scorer và CLIP-only runner đã hoàn tất.
- Production-index smoke run: 1 unlabeled, 0 failed, quality status `BLOCKED_BY_GROUND_TRUTH`.

## What is not done
- Import 35 query Group A và gắn ground truth có provenance.
- DEV/HOLDOUT Recall@1/5/20/50/100 và failure analysis.
- QA/TRAKE scorer chính thức do chưa có scoring contract.
- OCR, ASR, SigLIP, Objects extraction.
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
- Cung cấp Group A query source/ground truth, validate contract rồi chạy baseline DEV/HOLDOUT.

> [!CAUTION]
> **CHỈ THỊ RÕ RÀNG:** Chưa bắt đầu OCR, ASR, SigLIP hoặc Objects cho đến khi milestone tiếp theo được phê duyệt.
