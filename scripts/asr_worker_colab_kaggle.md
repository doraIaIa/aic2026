# ASR Whisper medium worker (Colab/Kaggle)

M2-ASR hiện chỉ là pilot trên 95 video lấy từ Group A top candidates. Worker chỉ đọc video và ghi artifact bất biến; không sửa raw BTC data hoặc production SQLite.

## 1. Chuẩn bị worker

Copy repository và đúng một shard manifest lên runtime. Mount/copy BTC corpus sao cho `data_root` chứa các path tương đối như `data_extracted/video/L21_V011.mp4`. Tạo config từ `configs/colab.example.toml` hoặc `configs/kaggle.example.toml`; không commit token hay đường dẫn chứa secret.

```bash
python -m pip install -e '.[asr]'
python -m aic2026.cli doctor --config configs/colab.toml
```

Kaggle dùng config riêng, ví dụ `configs/kaggle.toml`. Chỉ dùng worker hợp lệ của cá nhân/nhóm và tuân thủ quota/nội quy dữ liệu.

## 2. Chạy một shard

```bash
python -m aic2026.cli run-asr-shard \
  --config configs/colab.toml \
  --shard /content/shards/shard_000_of_004.json \
  --out-dir /content/asr-output/shard_000_of_004 \
  --model medium \
  --model-revision medium \
  --language vi \
  --device auto
```

Mặc định là `beam_size=5`, VAD bật, word timestamps tắt; CUDA dùng `float16`, CPU dùng `int8`. Chạy lại đúng lệnh để resume. Artifact hoàn tất có `DONE.json` và `checksum.sha256`; không dùng `--force` trừ khi chủ động archive artifact cũ và tạo lại.

## 3. Thu artifact về local

Zip/download nguyên thư mục shard, gồm:

```text
asr_segments.jsonl
asr_videos.jsonl
errors.jsonl
progress.json
DONE.json
checksum.sha256
```

Đặt bốn thư mục tại:

```text
F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1\
  shard_000_of_004\
  shard_001_of_004\
  shard_002_of_004\
  shard_003_of_004\
```

## 4. Validate, merge và build FTS tại local

`merge-asr-shards` kiểm tra DONE/checksum/count của từng shard trước khi nhập:

```powershell
python -m aic2026.cli merge-asr-shards `
  --shards-dir F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1 `
  --out-dir F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-merged-v1

python -m aic2026.cli build-asr-fts `
  --segments F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-merged-v1\asr_segments.jsonl `
  --out F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-fts-v1

python -m aic2026.cli search-asr `
  --index F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-fts-v1 `
  --query "thành phố Hồ Chí Minh" `
  --top-k 20
```

ASR `start_sec/end_sec` chỉ là temporal anchor, không phải frame ID để nộp. Exact frame vẫn phải đi qua mapping BTC đã xác minh và source video.
