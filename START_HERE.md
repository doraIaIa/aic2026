# Start here — first 60 minutes

Do not start Whisper/OCR/SigLIP full-corpus jobs yet.

## 1. Put the repository on the local SSD

Recommended:

```text
F:\AIC_DEV\aic2026     <- Git repository
F:\AIC_WORK\           <- cache/db/indexes/derived artifacts
G:\My Drive\AI_challenge\AIC_2026        <- Google Drive canonical raw corpus, read-only
```

The repository and work directory are deliberately separate from the Google Drive source corpus.

## 2. Bootstrap

Open PowerShell in the repo:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap_windows.ps1
```

Edit `configs/local.toml`. Use a stable human-readable Drive path if it is accessible. Avoid persisting `.shortcut-targets-by-id` in code/data contracts.

Run:

```powershell
python -m aic2026.cli doctor --config configs/local.toml
python -m aic2026.cli init-db --db F:/AIC_WORK/db/aic.sqlite
```

## 3. Prove resume/checkpointing before touching real data

```powershell
python -m aic2026.cli demo-manifest --out manifests/demo.jsonl --count 120
python -m aic2026.cli shard --manifest manifests/demo.jsonl --out manifests/shards/demo --size 40 --task demo
python -m aic2026.cli run-shard --shard manifests/shards/demo/shard-000.json --artifact-dir F:/AIC_WORK/artifacts/demo/demo-000 --handler echo --checkpoint-every 10
python -m aic2026.cli validate-artifact --artifact-dir F:/AIC_WORK/artifacts/demo/demo-000
```

Run the `run-shard` command a second time; it must return the existing valid artifact rather than duplicate work.

## 4. Create the private GitHub repository

Follow `scripts/create_github_repo_instructions.md`.

## 5. Give Antigravity one task only

Use `ANTIGRAVITY_BOOTSTRAP_PROMPT.md`.

The next deliverable is a read-only **dataset + frame/CLIP mapping audit**, not ML preprocessing.

## Gate to continue

Do not begin M1/Whisper/OCR/SigLIP production until the audit reports that the canonical path, frame mapping, keyframe ordering, and CLIP/keyframe count relationship are proven or explicitly understood.
