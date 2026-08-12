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
- Group A ASR pilot manifest: 95 video, 2 worker shard (48/47)
- Full ASR search DB: 873 video, 107.540 segments, 107.540 FTS rows, 0 orphan/duplicate
- CLI `python -m aic2026.search.asr` và atomic/idempotent index builder

## NEXT
- Review ASR-only search quality trên Group A queries
- Định nghĩa ablation CLIP-only so với CLIP+ASR sau khi có ground truth
- Thẩm định top candidates và gắn ground truth có provenance
- Tách DEV/HOLDOUT rồi chạy baseline, báo Recall@K và failure analysis

## BLOCKED
- Metric chất lượng baseline: BLOCKED_BY_GROUND_TRUTH
- QA scorer và TRAKE scorer: BLOCKED_BY_SCORING_CONTRACT

## NOT YET
- OCR
- ASR full corpus (chỉ mở sau pilot GO/NO-GO)
- Objects
- SigLIP
- TRAKE
- UI
