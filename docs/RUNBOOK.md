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
  --num-shards 2 `
  --out-dir F:\AIC_WORK\asr\shards\group-a-candidate-pilot-v1-2workers
```

Pilot hiện có 95 video: top-10 chỉ có 61 video unique nên builder mở rộng top-20. Colab chạy shard 0 có 48 video; Kaggle chạy shard 1 có 47 video. Split 4 phần cũ không còn là kế hoạch chính.

Chạy/resume một shard:

```powershell
python -m aic2026.cli run-asr-shard `
  --config configs/local.toml `
  --shard F:\AIC_WORK\asr\shards\group-a-candidate-pilot-v1-2workers\shard_000_of_002.json `
  --out-dir F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1\smoke_shard_000_of_002_limit5 `
  --model medium --model-revision medium --language vi --device auto --limit-videos 5
```

Smoke luôn dùng output riêng. Khi smoke validate, bỏ `--limit-videos` và chạy vào `shard_000_of_002` hoặc `shard_001_of_002`. Mặc định: faster-whisper, `beam_size=5`, VAD bật, word timestamps tắt, CUDA `float16`, CPU `int8`. Dùng `validate-asr-shard` trước khi zip. Xem guide và `notebooks/asr_whisper_medium_worker.ipynb`.

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

Sau FTS, `export-asr-candidates` chạy batch 35 Group A query và tạo `asr_candidate_review.csv`. `--metadata` là optional; chỉ truyền M1 metadata JSONL đã validate khi cần nearest keyframe/frame.

Chỉ chạy full corpus nếu pilot có transcript hữu ích và chi phí chấp nhận được. Lượt này không tạo hoặc chạy shard cho toàn bộ 873 video. ASR timestamps chỉ là temporal anchors, không phải submission frame IDs.

## Full-corpus ASR SQLite search

Build/rebuild atomic từ merged final JSONL; builder từ chối `.partial.jsonl`, backup DB cũ khi `--force`, validate trước khi swap và ghi report vào `F:\AIC_WORK\validation`:

```powershell
python -m aic2026.search.build_asr_index --config configs/local.toml --force
```

Chạy lại không `--force` là idempotent khi source fingerprint và integrity vẫn khớp.

```powershell
python -m aic2026.search.asr "thành phố hồ chí minh"
python -m aic2026.search.asr "60 giây" --limit 20
python -m aic2026.search.asr '"chào mừng quý vị"' --video-id L21_V001
python -m aic2026.search.asr "bão lũ" --json
```

FTS dùng `unicode61 remove_diacritics 2`; tìm không dấu tiện hơn nhưng có thể tăng false positive giữa các từ chỉ khác dấu. Dùng phrase query và `--video-id` khi cần tăng precision. ASR timestamp vẫn chỉ là temporal anchor.

## Local ASR Search API và demo UI

> [!IMPORTANT]
> Đây chỉ là luồng diagnostic cho ASR provider. Không phát triển route ASR-only thành product UI. Contract sản phẩm chung xem tại `docs/RETRIEVAL_CONTRACT.md`; `/prototype` chỉ được thay mock sau khi Phase 1–2 backend hoàn tất.

Khởi chạy API read-only từ repo chính; API reuse `aic2026.search.asr.search_asr`, không chứa SQL riêng và không copy database sang frontend:

```powershell
cd F:\AIC_DEV\aic2026
.\.venv\Scripts\python.exe -m aic2026.search.api --config configs/local.toml
```

Endpoints:

- `GET http://127.0.0.1:8765/api/health`
- `GET http://127.0.0.1:8765/api/v1/capabilities` — trạng thái thật ASR/Visual/OCR/Object/media; lần đầu có thể chậm do checksum và lazy-load Visual.
- `GET http://127.0.0.1:8765/api/asr/search?q=60%20gi%C3%A2y&limit=20`
- Thêm `video_id=L21_V001` để giới hạn một video.

Chạy frontend riêng ở `F:\aic-video-search-demo`:

```powershell
cd F:\aic-video-search-demo
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Mở `http://localhost:3000`. Vite proxy `/api` tới `http://127.0.0.1:8765`; có thể override bằng biến `AIC_API_URL`. Route `/prototype` giữ nguyên bản mock cũ để tham chiếu, còn `/` là ASR search thật.

Video preview chưa bật: `source_video_path` trong DB là relative path đúng contract, nhưng `data_root` phải được mount và media phải được serve qua endpoint có kiểm soát. Không chuyển ASR timestamp thành submission frame ID.
