# ASR Whisper medium pilot — 2 worker Colab/Kaggle

Pilot gồm 95 video lấy từ Group A candidates và chỉ dùng hai worker hợp lệ:

- Colab: `shard_000_of_002.json` — 48 video;
- Kaggle: `shard_001_of_002.json` — 47 video.

Worker chỉ đọc BTC video và ghi artifact bất biến. Không sửa raw data, không ghi production SQLite và không dùng nhiều tài khoản để né quota.

## 1. Đưa input lên worker

Mỗi worker cần:

1. repository tại `/content/aic2026` (Colab) hoặc `/kaggle/working/aic2026` (Kaggle);
2. đúng một shard JSON từ `F:\AIC_WORK\asr\shards\group-a-candidate-pilot-v1-2workers`;
3. BTC root có layout tương đối như `data_extracted/video/L21_V011.mp4`;
4. Internet hoặc model cache hợp lệ để cài `faster-whisper` và lấy model `medium`.

Colab có thể mount Google Drive. Kaggle nên attach BTC/model/shard dưới `/kaggle/input` và ghi output dưới `/kaggle/working`. Không đưa token hoặc secret vào notebook/config.

Notebook runnable: `notebooks/asr_whisper_medium_worker.ipynb`. Chọn:

```python
WORKER = "colab"   # Colab; tự dùng SHARD_INDEX=0
WORKER = "kaggle"  # Kaggle; tự dùng SHARD_INDEX=1
NUM_SHARDS = 2
```

## 2. Cài dependency và tạo runtime config

```bash
cd /content/aic2026  # Kaggle: /kaggle/working/aic2026
python -m pip install -e '.[asr]'
python -m aic2026.cli doctor --config /content/aic-runtime.toml
```

Runtime TOML phải đặt `data_root` đúng BTC root của worker. Absolute path chỉ nằm trong runtime config; manifest/artifact tiếp tục lưu relative source paths.

## 3. Smoke 5 video trước

Luôn dùng output riêng, không dùng thư mục full-shard:

```bash
python -m aic2026.cli run-asr-shard \
  --config /content/aic-runtime.toml \
  --shard /content/shards/shard_000_of_002.json \
  --out-dir /content/asr-output/smoke_shard_000_of_002_limit5 \
  --model medium --model-revision medium --language vi \
  --beam-size 5 --vad-filter --device auto --limit-videos 5

python -m aic2026.cli validate-asr-shard \
  --artifact-dir /content/asr-output/smoke_shard_000_of_002_limit5
```

Kaggle thay path bằng `/kaggle/...` và shard `001`. Chỉ chạy full shard khi smoke có `DONE.json`, checksum hợp lệ, transcript/timestamp đọc được và lỗi không có tính hệ thống.

## 4. Chạy/resume full shard

Colab:

```bash
python -m aic2026.cli run-asr-shard \
  --config /content/aic-runtime.toml \
  --shard /content/shards/shard_000_of_002.json \
  --out-dir /content/asr-output/shard_000_of_002 \
  --model medium --model-revision medium --language vi \
  --beam-size 5 --vad-filter --device auto
```

Kaggle:

```bash
python -m aic2026.cli run-asr-shard \
  --config /kaggle/working/aic-runtime.toml \
  --shard /kaggle/input/aic-asr-shards/shard_001_of_002.json \
  --out-dir /kaggle/working/asr-output/shard_001_of_002 \
  --model medium --model-revision medium --language vi \
  --beam-size 5 --vad-filter --device auto
```

Mặc định word timestamps tắt; CUDA dùng `float16`, CPU dùng `int8`. Chạy lại đúng command để resume. Không dùng `--force` trừ khi chủ động archive artifact cũ.

## 5. Validate và tải artifact về local

```bash
python -m aic2026.cli validate-asr-shard --artifact-dir <full-shard-output>
```

Zip bằng notebook `shutil.make_archive`, rồi download nguyên artifact gồm `asr_segments.jsonl`, `asr_videos.jsonl`, `errors.jsonl`, `progress.json`, `DONE.json`, `checksum.sha256` và partial files phục vụ forensic/resume.

Giải nén về:

```text
F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1\
  shard_000_of_002\
  shard_001_of_002\
```

## 6. Merge và build FTS tại local

Chỉ chạy khi cả hai shard validate thành công:

```powershell
python -m aic2026.cli merge-asr-shards `
  --shards-dir F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1 `
  --out-dir F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1-merged

python -m aic2026.cli build-asr-fts `
  --segments F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1-merged\asr_segments.jsonl `
  --out F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1-fts

python -m aic2026.cli export-asr-candidates `
  --dataset F:\AIC_WORK\evaluation\group-a-unlabeled-v1.json `
  --index F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1-fts `
  --metadata F:\AIC_WORK\artifacts\m1\clip-faiss-btc-v1\metadata.jsonl `
  --out F:\AIC_WORK\artifacts\asr\whisper-medium-vi-pilot-v1-review `
  --top-k 20
```

Có thể bỏ `--metadata` để các cột nearest keyframe để trống. ASR `start_sec/end_sec` chỉ là temporal anchor, không phải submission frame ID.

## 7. GO/NO-GO

GO chỉ khi ít nhất 90% video thành công, timestamp hợp lệ, transcript tiếng Việt đọc được ở phần lớn video có lời nói, FTS/search hoạt động và một số query tên riêng/thời sự/lời dẫn trả segment liên quan. NO-GO hoặc chỉnh pipeline nếu transcript rỗng hàng loạt, timestamp lệch, lỗi format/audio tập trung hoặc model medium cho tiếng Việt quá kém. Chưa mở full 873 video trước quyết định này.
