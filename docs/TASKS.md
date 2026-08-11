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

## NEXT
- Thẩm định top candidates và gắn ground truth có provenance
- Tách DEV/HOLDOUT rồi chạy baseline, báo Recall@K và failure analysis

## BLOCKED
- Metric chất lượng baseline: BLOCKED_BY_GROUND_TRUTH
- QA scorer và TRAKE scorer: BLOCKED_BY_SCORING_CONTRACT

## NOT YET
- OCR
- ASR
- Objects
- SigLIP
- TRAKE
- UI
