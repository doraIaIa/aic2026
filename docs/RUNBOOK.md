# Operations runbook

## Before every long job

- confirm Git commit/tag
- confirm config hash
- confirm manifest hash
- run unit tests
- run 10-100 item pilot
- inspect outputs manually
- estimate wall time and storage
- choose shard size

## During a job

- never edit manifest in place
- monitor failures and throughput
- preserve error records
- do not reduce integrity checks to make a job "finish"

## After a shard

```bash
python -m aic2026.cli validate-artifact --artifact-dir <dir>
```

Only validated shards are eligible for local import.

## If cloud runtime dies

Run the exact same `run-shard` command. The checkpoint and valid partial records determine where processing continues.

## If output is corrupt

Do not overwrite evidence. Move the directory to `artifacts/rejected/<task>/<shard>-<timestamp>` and rerun to a clean artifact directory.
