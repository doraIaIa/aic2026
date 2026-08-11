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

Không tìm thấy `query-p3-groupA.zip`, 35 query text hoặc ground truth Group A trong repository, workspace hay root BTC được kiểm tra ngày 11/08/2026. File `AIC2026_RECOVERED_MASTER_PLAN.md` chỉ nhắc tên archive và một số nhóm lỗi; nội dung này không đủ để tái tạo 35 query. Không query, `video_id`, frame range hoặc answer nào được suy diễn từ mô tả đó.

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
- `trap_category`: `visual`, `micro_moment`, `ocr_only`, `asr_only`, `event_chain`, `count`, `spatial_motion`.

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
python -m aic2026.cli validate-eval-dataset --dataset <eval.json>

python -m aic2026.cli run-baseline-eval `
  --dataset <eval.json> `
  --index-dir <m1-index-dir> `
  --out <new-run-dir> `
  --split dev `
  --experiment-name <name>

python -m aic2026.cli eval-summary --run-dir <run-dir>
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

## 7. Quyết định provenance M1

Artifact `clip-faiss-btc-v1` đủ điều kiện làm **frozen baseline artifact** cho Evaluation Closure vì:

1. index và metadata checksum khớp marker;
2. expected/processed count cùng bằng 177.321, failures bằng 0;
3. dimension bằng 512 và mapping stable ID đã được xác minh;
4. text encoder `ViT-B-32/openai` được xác nhận từ notebook BTC;
5. production-index smoke run tái lập đúng top result đã quan sát trước đó.

Không rebuild trong task này vì không có checksum mismatch, mapping contradiction hoặc thay đổi feature/index được đo. Không sửa `DONE.json` cũ.

Technical debt: marker cũ ghi source commit `9b2ecd8...+dirty` và model revision `unknown-not-present-in-source`, trong khi mã M1 sạch ở `3d7267a...`. Chỉ tạo artifact version mới khi cần một release có provenance clean end-to-end, khi feature model/config thay đổi, khi checksum lỗi hoặc khi benchmark chứng minh encoder/index không tương thích. Artifact mới phải dùng thư mục/version mới và không overwrite v1.
