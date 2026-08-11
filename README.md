# AIC 2026 execution scaffold

This repository is the **control-plane and reliability layer** for the AIC 2026 video-retrieval project.
It is intentionally conservative: Git stores code/config/manifests; Google Drive stores canonical data and durable artifacts; local/Colab/Kaggle are compute workers.

## Non-negotiable architecture

- Raw BTC data is read-only.
- Paths persisted in manifests/DB are relative, never `G:\...`, `/content/...`, or `/kaggle/...`.
- Cloud workers do not write to the production SQLite database.
- Long jobs are sharded, resumable, idempotent, and finalized with checksum + `DONE.json`.
- No `DONE.json` means the artifact is untrusted.
- Local is the authority that validates and merges cloud outputs.
- Exact submission frames must later pass through the verified BTC `frame_idx` mapping path.

## Quick start

### Windows local

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
Copy-Item configs\local.example.toml configs\local.toml
# edit configs/local.toml to match your machine
python -m pytest -q
python -m aic2026.cli doctor --config configs/local.toml
```

### Build a demo manifest and shards

```powershell
python -m aic2026.cli demo-manifest --out manifests/examples/demo.jsonl --count 120
python -m aic2026.cli shard --manifest manifests/examples/demo.jsonl --out manifests/shards/demo --size 40 --task demo
python -m aic2026.cli status --shards manifests/shards/demo --artifacts F:/AIC_WORK/artifacts/demo
```

### Dry-run the worker with resumable checkpoints

```powershell
python -m aic2026.cli run-shard `
  --shard manifests/shards/demo/shard-000.json `
  --artifact-dir F:/AIC_WORK/artifacts/demo/shard-000 `
  --handler echo `
  --checkpoint-every 10
```

Re-run the same command. Completed item IDs are skipped and the finalized artifact validates again rather than duplicating work.

## What is implemented now

- environment/path config loader
- portable relative-path resolver
- manifest + deterministic shard generation
- resumable item-level checkpointing
- atomic JSON writes
- append-safe JSONL recovery
- artifact finalization with SHA-256 and `DONE.json`
- artifact validator
- job status scanner
- SQLite schema draft for corpus/jobs/evaluation
- Colab/Kaggle bootstrap notebooks
- Windows/Linux bootstrap scripts
- tests for resume and corruption detection
- versioned evaluation contract và validator
- KIS Recall@1/5/20/50/100 scorer
- CLIP-only evaluation runner với predictions, latency, provenance và checksum

## What is deliberately NOT implemented yet

- Whisper, PaddleOCR, SigLIP2 handlers
- QA/TRAKE scorer chính thức và UI

Those should be implemented only after the dataset/path/frame mapping contract is verified on the actual corpus. See `docs/IMPLEMENTATION_SPEC.md` and `ANTIGRAVITY_BOOTSTRAP_PROMPT.md`.
