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

## Evaluation baseline

Import Group A combined text (chỉ tạo query `unlabeled_reference`, không tạo ground truth):

```powershell
python -m aic2026.cli import-combined-queries `
  --input query-p3-groupA_combined.txt `
  --out F:\AIC_WORK\evaluation\group-a-unlabeled-v1.json `
  --expected-sha256 ad9044eb901042ac5760c772b1297f2ecfd94e4a2b2abf9b8121155387586e80
```

Luôn validate dataset trước khi chạy:

```powershell
python -m aic2026.cli validate-eval-dataset --dataset <eval.json>
```

DEV và HOLDOUT phải chạy vào hai artifact directory khác nhau:

```powershell
python -m aic2026.cli run-baseline-eval `
  --dataset <eval.json> `
  --index-dir <m1-index-dir> `
  --out <new-run-dir> `
  --split dev `
  --experiment-name <name>
```

Xác thực output và xem summary:

```powershell
python -m aic2026.cli eval-summary --run-dir <run-dir>
```

Xuất bảng review riêng, không ghi thêm vào run đã có `DONE.json`:

```powershell
python -m aic2026.cli export-eval-candidates `
  --dataset <eval.json> `
  --run-dir <run-dir> `
  --out <new-review-dir>
```

`candidate_review.csv` là UTF-8 BOM để mở an toàn trên Excel/Windows. `failure_sheet.csv` luôn tồn tại; nếu không có lỗi thì file chỉ có header.

Nếu summary ghi `BLOCKED_BY_GROUND_TRUTH`, predictions vẫn là artifact hợp lệ nhưng không được diễn giải như metric chất lượng.

## M2-ASR pilot

Tạo manifest từ Group A candidate review. Builder dùng inventory audit làm authority cho `video_path`, chỉ lưu relative path và không copy video:

```powershell
python -m aic2026.cli build-asr-pilot-manifest `
  --config configs/local.toml `
  --candidate-review F:\AIC_WORK\artifacts\evaluation\group-a-review-v1\candidate_review.csv `
  --out F:\AIC_WORK\asr\manifests\group-a-candidate-pilot-v1.jsonl

python -m aic2026.cli split-asr-shards `
  --manifest F:\AIC_WORK\asr\manifests\group-a-candidate-pilot-v1.jsonl `
  --num-shards 4 `
  --out-dir F:\AIC_WORK\asr\shards\group-a-candidate-pilot-v1
```

Pilot hiện có 95 video: top-10 chỉ có 61 video unique nên builder mở rộng top-20. Bốn shard có 24/24/24/23 video.

Chạy/resume một shard:

```powershell
python -m aic2026.cli run-asr-shard `
  --config configs/local.toml `
  --shard F:\AIC_WORK\asr\shards\group-a-candidate-pilot-v1\shard_000_of_004.json `
  --out-dir F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1\shard_000_of_004 `
  --model medium --model-revision medium --language vi --device auto
```

Mặc định: faster-whisper, `beam_size=5`, VAD bật, word timestamps tắt, CUDA `float16`, CPU `int8`. Thiếu optional dependency trả lỗi rõ và không ảnh hưởng CLIP baseline. Xem hướng dẫn worker tại `scripts/asr_worker_colab_kaggle.md`.

Sau khi đủ shard, merge sẽ fail closed nếu DONE/checksum/count sai; mỗi lỗi video riêng lẻ vẫn nằm trong `errors.jsonl`:

```powershell
python -m aic2026.cli merge-asr-shards `
  --shards-dir F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1 `
  --out-dir F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-merged-v1

python -m aic2026.cli build-asr-fts `
  --segments F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-merged-v1\asr_segments.jsonl `
  --out F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-fts-v1

python -m aic2026.cli search-asr `
  --index F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-fts-v1 `
  --query "tên địa danh cần tìm" --top-k 20
```

Chỉ chạy full corpus nếu pilot có transcript hữu ích và chi phí chấp nhận được. Với 873 video/4 shard, splitter cân bằng thành 219/218/218/218 video. ASR timestamps chỉ là temporal anchors, không phải submission frame IDs.
