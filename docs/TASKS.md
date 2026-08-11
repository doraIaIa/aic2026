# Project Tasks Queue

## DONE
- M0 reliability scaffold
- checkpoint/resume validation
- keyframe/CSV/CLIP mapping contract fix
- 20-video real-data mapping validation
- M1 baseline BTC CLIP + FAISS
- Evaluation contract v1, KIS scorer và CLIP-only runner
- Production-index evaluation smoke run với query unlabeled
- Import 35 Group A query text theo contract v1 và provenance checksum
- Group A CLIP-only top-100 run: 3.500 predictions, 0 failure
- Candidate review CSV và failure sheet
- M2-ASR pilot code: manifest/shard/resume/checksum/merge/FTS5
- Group A ASR pilot manifest: 95 video, 4 shard (24/24/24/23)

## NEXT
- Chạy 4 faster-whisper `medium`/`vi` pilot shard trên GPU
- Merge transcript, build FTS5 và review ASR hits
- Thẩm định top candidates và gắn ground truth có provenance
- Tách DEV/HOLDOUT rồi chạy baseline, báo Recall@K và failure analysis

## BLOCKED
- Metric chất lượng baseline: BLOCKED_BY_GROUND_TRUTH
- QA scorer và TRAKE scorer: BLOCKED_BY_SCORING_CONTRACT
- ASR smoke thật tại local: BLOCKED_BY_RUNTIME (`faster-whisper` chưa cài, không có CUDA)

## NOT YET
- OCR
- ASR full corpus (chỉ mở sau pilot GO/NO-GO)
- Objects
- SigLIP
- TRAKE
- UI
