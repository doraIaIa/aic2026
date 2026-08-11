# Engineering rules for AI coding agents

These rules are mandatory. If a requested change conflicts with them, stop and report the conflict instead of silently working around it.

1. Never modify, rename, move, or delete source BTC data.
2. Never infer file format, feature dimension, FPS convention, frame indexing, or ID mapping. Inspect and record evidence first.
3. Never persist machine-specific absolute paths in manifests, SQLite, FAISS metadata, or evaluation data.
4. Every batch operation must be resumable, idempotent, shardable, and atomic at artifact finalization.
5. Write state/output to temporary or partial files first. Finalize only after validation.
6. Every derived artifact must record task, model, model revision, config hash, git commit when available, input manifest hash, expected count, processed count, failures, and output checksum.
7. Optional modalities fail open: ASR/OCR/SigLIP/Qwen failure must not kill baseline retrieval.
8. Data-integrity failures fail closed: wrong mapping, duplicate stable ID, dimension mismatch, checksum mismatch, malformed manifest, or frame convention uncertainty must stop the affected import.
9. Never run `pip install --upgrade` as a convenience fix. Dependency changes are explicit code-review changes.
10. Do not add PostgreSQL, Elasticsearch, Milvus, Qdrant, Celery, Airflow, or another service without a measured bottleneck that SQLite + FTS5 + FAISS cannot meet.
11. ASR/OCR/VLM timestamps are temporal anchors, never authoritative submission frame IDs.
12. Exact submission frame selection must use the verified BTC frame-index mapping and source video.
13. Cloud workers must not mutate the production SQLite DB. They emit immutable artifacts; local validates and imports them.
14. Do not put raw data, media, model weights, embeddings, indexes, databases, tokens, or secrets in Git.
15. At the end of every coding task report: files changed, tests run, evidence, known limitations, and rollback procedure.
16. Prefer small reversible commits. Do not refactor unrelated working code while implementing a feature.
17. Before a full-dataset ML job: pilot -> validate -> benchmark -> GO/NO-GO -> shard production run.
18. A shard is trusted only when its `DONE.json` validates against the output checksum and manifest hash.
19. Do not overwrite a valid completed shard. Recompute into a new artifact/version if model/config/input changes.
20. Any schema/config contract change requires migration notes and updated tests.
21. Batch-1 dataset audit is closed. Do not re-audit the full corpus unless the dataset/schema changes or production code reveals a new contradiction.
22. Before every task, read docs/PROJECT_STATE.md and docs/DATA_CONTRACT_LOCK.md.
