# Evaluation contract và baseline runner

## 1. Trạng thái

| Thành phần | Trạng thái |
|---|---|
| Dataset contract version 1 và validator | DONE |
| KIS scorer theo inclusive frame range | DONE |
| CLIP-only evaluation runner | DONE |
| Evaluation artifact, resume và checksum | DONE |
| QA scorer chính thức | BLOCKED_BY_SCORING_CONTRACT |
| TRAKE scorer chính thức | BLOCKED_BY_SCORING_CONTRACT |
| Metric chất lượng trên Group A | BLOCKED_BY_GROUND_TRUTH |

Đã nhận và import `query-p3-groupA_combined.txt` ngày 11/08/2026: 35 query gồm 29 KIS, 4 QA và 2 TRAKE. Nguồn có SHA-256 `ad9044eb901042ac5760c772b1297f2ecfd94e4a2b2abf9b8121155387586e80`. Toàn bộ query vẫn là `unlabeled_reference`; không `video_id`, frame range hoặc answer nào được tự tạo.

### Audit implementation trước task

- `eval_experiments`, `eval_queries`, `eval_runs` tồn tại trong SQLite schema draft.
- Không có scorer, evaluation runner, prediction format hoặc CLI evaluation trước task.
- SQLite draft thiếu `label_status`, label provenance và run-level artifact provenance đầy đủ; `query_id` cũng đang là integer trong khi file contract dùng stable string ID.
- Task này không thay schema SQLite vì repository chưa có migration framework và evaluation database chưa phải authority của runner. JSON/JSONL artifact versioned là contract hiện hành. SQLite import chỉ được triển khai bằng migration riêng, có rollback và test dữ liệu cũ.

## 2. Dataset contract version 1

Evaluation dataset là một JSON object:

```json
{
  "schema_version": 1,
  "dataset_id": "group-a-reference",
  "dataset_version": "v1",
  "source_provenance": {
    "source_relpath": "query-p3-groupA_combined.txt",
    "source_sha256": "<sha256>",
    "imported_at": "<ISO-8601 UTC>",
    "parser_version": "group-a-combined-v1"
  },
  "queries": [
    {
      "query_id": "stable-query-id",
      "query_type": "KIS",
      "query_text": "mô tả truy vấn",
      "question_text": null,
      "trap_category": "visual",
      "split": "dev",
      "label_status": "unlabeled_reference",
      "gt_video_id": null,
      "gt_frame_ranges": [],
      "gt_answer": null,
      "label_provenance": null
    }
  ]
}
```

Giá trị hợp lệ:

- `query_type`: `KIS`, `QA`, `TRAKE`;
- `split`: `dev`, `holdout`;
- `label_status`: `labeled`, `unlabeled_reference`;
- `trap_category`: `visual`, `micro_moment`, `ocr_only`, `asr_only`, `event_chain`, `count`, `spatial_motion`, `unclassified`.

`unclassified` chỉ dùng cho query reference chưa được thẩm định trap category; importer không suy diễn category từ nội dung.

Query `unlabeled_reference` không được chứa ground truth hoặc label provenance. Query `labeled` phải có `label_provenance.source`. KIS/TRAKE labeled phải có `gt_video_id` và ít nhất một inclusive frame range hợp lệ; QA labeled phải có `gt_answer`.

Validator cảnh báo khi HOLDOUT không nằm trong khoảng khuyến nghị 20–30% số query labeled. Mỗi evaluation run chỉ xử lý một split để ngăn trộn DEV/HOLDOUT. HOLDOUT không được dùng để chỉnh weight hằng ngày.

## 3. KIS scoring contract

Candidate KIS đúng khi:

```text
candidate.video_id == gt_video_id
và tồn tại range sao cho start_frame <= candidate.frame_idx <= end_frame
```

Với mỗi `k ∈ {1, 5, 20, 50, 100}`:

```text
R@k = 1 nếu có candidate đúng trong top-k, ngược lại R@k = 0
```

Scorer ghi `first_correct_rank`, giới hạn tối đa 100 predictions và từ chối candidate malformed hoặc duplicate. Query unlabeled không được đưa vào mẫu số aggregate.

QA và TRAKE chỉ có adapter validation. Không có answer normalization hoặc event-chain scoring vì chưa tìm thấy scoring contract chính thức.

## 4. Baseline evaluation artifact

Một run mới ghi:

```text
resume_contract.json
predictions.partial.jsonl
predictions.jsonl
summary.json
DONE.json
```

`resume_contract.json` khóa dataset hash, config hash, split và checksum M1 index. `DONE.json` được ghi cuối và chứa count, failure count, dataset hash, config hash, Git state, model, index/metadata checksum và output checksum.

Runner ghi error theo query và tiếp tục các query còn lại. Artifact đã có `DONE.json` hợp lệ chỉ được tái sử dụng khi dataset hash và config hash khớp; không được ghi đè bằng yêu cầu khác.

## 5. CLI

```powershell
python -m aic2026.cli import-combined-queries `
  --input query-p3-groupA_combined.txt `
  --out F:\AIC_WORK\evaluation\group-a-unlabeled-v1.json `
  --expected-sha256 ad9044eb901042ac5760c772b1297f2ecfd94e4a2b2abf9b8121155387586e80

python -m aic2026.cli validate-eval-dataset --dataset <eval.json>

python -m aic2026.cli run-baseline-eval `
  --dataset <eval.json> `
  --index-dir <m1-index-dir> `
  --out <new-run-dir> `
  --split dev `
  --experiment-name <name>

python -m aic2026.cli eval-summary --run-dir <run-dir>

python -m aic2026.cli export-eval-candidates `
  --dataset <eval.json> `
  --run-dir <run-dir> `
  --out <new-review-dir>
```

Integrity/contract error trả exit code khác 0. Dataset không có label vẫn hợp lệ nhưng summary phải ghi `BLOCKED_BY_GROUND_TRUTH` và metrics bằng `null`.

## 6. Production-index smoke run

Một query tổng hợp `a person riding a bicycle` đã chạy trên production M1 index:

| Chỉ số | Giá trị |
|---|---:|
| Query | 1 |
| Labeled | 0 |
| Unlabeled | 1 |
| Failed | 0 |
| Predictions | 100 |
| Latency | 272 ms |
| Quality status | BLOCKED_BY_GROUND_TRUTH |

Đây là kiểm tra vận hành, không phải quality benchmark và không tạo Recall@K thật.

## 7. Group A unlabeled baseline run

Run `group-a-clip-only-v1` đã truy hồi top 100 cho đủ 35 query trên frozen M1 index:

| Chỉ số | Giá trị |
|---|---:|
| Query | 35 |
| KIS / QA / TRAKE | 29 / 4 / 2 |
| Labeled / unlabeled | 0 / 35 |
| Failed | 0 |
| Predictions | 3.500 |
| Latency p50 / p95 | 291,66 ms / 377,56 ms |
| Quality status | BLOCKED_BY_GROUND_TRUTH |

Artifacts:

- dataset: `F:\AIC_WORK\evaluation\group-a-unlabeled-v1.json`;
- run: `F:\AIC_WORK\artifacts\evaluation\group-a-unlabeled-v1`;
- candidate review và failure sheet: `F:\AIC_WORK\artifacts\evaluation\group-a-review-v1`.

Recall@K là `null`, không phải 0. Khi có ground truth có provenance, tạo dataset version mới, tách DEV/HOLDOUT và chạy lại scorer; không sửa dataset hoặc artifact đã hoàn tất.

## 8. Quyết định provenance M1

Artifact `clip-faiss-btc-v1` đủ điều kiện làm **frozen baseline artifact** cho Evaluation Closure vì:

1. index và metadata checksum khớp marker;
2. expected/processed count cùng bằng 177.321, failures bằng 0;
3. dimension bằng 512 và mapping stable ID đã được xác minh;
4. text encoder `ViT-B-32/openai` được xác nhận từ notebook BTC;
5. production-index smoke run tái lập đúng top result đã quan sát trước đó.

Không rebuild trong task này vì không có checksum mismatch, mapping contradiction hoặc thay đổi feature/index được đo. Không sửa `DONE.json` cũ.

Technical debt: marker cũ ghi source commit `9b2ecd8...+dirty` và model revision `unknown-not-present-in-source`, trong khi mã M1 sạch ở `3d7267a...`. Chỉ tạo artifact version mới khi cần một release có provenance clean end-to-end, khi feature model/config thay đổi, khi checksum lỗi hoặc khi benchmark chứng minh encoder/index không tương thích. Artifact mới phải dùng thư mục/version mới và không overwrite v1.
