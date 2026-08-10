# Cloud execution runbook

## Principle

Cloud runtime is disposable. Durable progress is represented by persisted checkpoints and completed immutable artifacts, not notebook state.

## Colab

1. Mount Drive only for durable input/output exchange.
2. Copy/archive one shard into `/content`.
3. Process locally in `/content/aic_work`.
4. Checkpoint every N items to durable artifact root.
5. Finalize shard locally, verify checksum, then persist completed artifact.
6. On restart, clone/pull repository and re-run the same shard command; completed IDs are skipped.

Avoid per-image read/write loops against mounted Drive when the same shard can be copied once and processed locally.

## Kaggle

1. Attach a prepared private input dataset/shard when practical.
2. Clone or upload the exact repository revision.
3. Run one or several bounded shards.
4. Save notebook output as completed artifacts.
5. Download/transfer artifacts to local/Drive for authority validation.

Do not design progress tracking around browser connectivity or notebook variables.

## Cross-worker safety

Two workers may process different shards simultaneously.
Two workers must not write to the same artifact directory/shard ID.
If intentional recomputation is required, use a new run/config hash or artifact version.

## Resume semantics

- If `DONE.json` validates: skip shard.
- If checkpoint/partial output exists without valid DONE: resume.
- If state is inconsistent: quarantine or restart the shard after preserving evidence.
