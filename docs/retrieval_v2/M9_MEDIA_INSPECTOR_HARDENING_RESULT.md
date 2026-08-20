# AIC 2026 M9 — Media Inspector Hardening + Exact Source Frame Authority Acceptance Report

## Executive Summary
- **Module**: M9 — Media Inspector Hardening + Exact Source Frame Authority
- **Core Repository**: `F:\AIC_DEV\aic2026`
- **Frontend Repository**: `F:\aic-video-search-demo`
- **Status**: PASSED / ACCEPTED
- **Verdict**:
  - `M9_ACCEPTANCE = PASS`
  - `M9_MEDIA_AUTHORITY_GATE = PASS`
  - `M9_OPERATOR_WORKFLOW_GATE = PASS`
  - `M13_LITE_READY = YES`

---

## 1. Capabilities Implemented

### Backend Capabilities (`aic2026.media`)
1. **Thread-Safe LRU JPEG Frame Cache (`MediaFrameCache`)**:
   - In-memory sparse JPEG cache with configurable max items/bytes and metrics tracking (`hits`, `misses`, `errors`).
   - Evicts LRU items under memory pressure.
2. **Nearest Keyframe Resolver (`NearestKeyframeResolver`)**:
   - Loads CUSTOM (`siglip_custom_rowmap.jsonl`) and BTC (`btc_clip_raw_rowmap.jsonl`) rowmaps.
   - Binary search over `timestamp_ms` returning `nearest_absolute`, `nearest_before`, `nearest_after`, and `delta_ms`.
3. **Enhanced Media Resolver (`MediaResolver`)**:
   - `VideoMeta`: Includes `exact_frame_supported`, `range_stream_supported`, `frame_count_reliable`, `fps_num`, `fps_den`, `time_base`, `codec`.
   - `FrameResolveResult`: Authority model outputting `authority="SOURCE_VIDEO"`, `method="PTS_AWARE"`, `requested_timestamp_ms`, `requested_frame_idx`, `resolved_frame_idx`, `resolved_pts_ms`, `delta_ms`, and `jpeg_url`.
4. **API Endpoints & HTTP Range Streaming**:
   - `GET /api/v1/media/{video_id}/info`
   - `GET /api/v1/media/{video_id}/resolve-frame?time_sec=...`
   - `GET /api/v1/media/{video_id}/frames/{frame_idx}`
   - `GET /api/v1/media/{video_id}/nearest-keyframes?target_ms=...`
   - `GET /api/v1/media/{video_id}/stream`: Supports HTTP 206 Partial Content and 416 Range Not Satisfiable.
5. **Real Media Inspector Benchmark Suite**:
   - Evaluates Range streaming across multiple videos, nearest keyframe probes (CUSTOM & BTC), exact physical frame & PIL array decodes, and cold/warm LRU cache latencies.

### Frontend Workstation (`client/src/retrieval`)
1. **Header Authority Badging**:
   - Badges `AUTHORITY: SOURCE VIDEO` for exact physical decoded frame.
   - Displays `SOURCE frame #X`, PTS, and `Δ from anchor` tag.
   - Displays Nearest CUSTOM KF and Nearest BTC KF timestamps and deltas.
2. **Physical Frame Stepping**:
   - `−10f`, `−3f`, `−1f`, `+1f`, `+3f`, `+10f` operating strictly on physical `SOURCE frame_idx`.
3. **Physical Time Stepping & Neighborhood Strip**:
   - `−10s`, `−3s`, `+3s`, `+10s` time navigation.
   - Neighborhood strip slots (`-10s`, `-3s`, `anchor`, `+3s`, `+10s`) for instant frame resolution targeting.
4. **Async Protection & Keyboard Shortcuts**:
   - `tokenRef` / `AbortController` protection against stale async responses.
   - `←`/`→` (±1 frame), `Shift+←`/`Shift+→` (±10 frames), `J`/`L` (±3s time), `Shift+J`/`Shift+L` (±10s time) with input/textarea focus protection.

---

## 2. Verification & Test Results

### Core Pytest Regression Suite
- **Executed**: `.venv\Scripts\python -m pytest -q tests`
- **Result**: `402 passed, 2 skipped in 172.60s`
- **New Unit Tests Passed**:
  - `tests/test_exact_frame.py` (LRU cache, frame authority)
  - `tests/test_media_range.py` (200 OK, 206 Partial Content, 416 Range Not Satisfiable)
  - `tests/test_nearest_keyframe.py` (CUSTOM & BTC nearest keyframe resolution)
  - `tests/test_media_inspector_benchmark.py` (M9 benchmark suite execution)

### Frontend Validation
- **Vitest Suite**: `14 passed (14), 63 passed (63)`
- **Typecheck (`npm run check`)**: `PASS` (0 errors)
- **Production Build (`npm run build`)**: `PASS`
