# Project State

**Current Phase:** M0 closing / M1 ready

## What is done
- M0 reliability scaffold (checkpointing/resume validation).
- Keyframe/CSV/CLIP mapping contract fix.
- 20-video real-data mapping validation.

## What is not done
- M1 (CLIP ingestion + FAISS baseline).
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
- **M1 CLIP + FAISS only**

> [!CAUTION]
> **EXPLICIT INSTRUCTION:** Do NOT start OCR, ASR, SigLIP, or Objects extraction yet. M1 is purely CLIP + FAISS.
