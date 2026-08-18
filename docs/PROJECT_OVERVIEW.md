Bạn đang tiếp tục repository AIC 2026 với vai trò senior Python/ML systems engineer. Hãy trực tiếp kiểm tra, triển khai, kiểm thử và cập nhật trạng thái dự án; không chỉ viết kế hoạch.

## 1. Đọc trước khi làm

Đọc đầy đủ theo thứ tự:

1. `AGENTS.md`
2. `docs/PROJECT_OVERVIEW.md`
3. `docs/PROJECT_STATE.md`
4. `docs/TASKS.md`
5. `docs/DATA_CONTRACT.md`
6. `docs/DATA_CONTRACT_LOCK.md`
7. `docs/IMPLEMENTATION_SPEC.md`
8. `docs/RUNBOOK.md`
9. `docs/CLOUD_EXECUTION.md`
10. README và mã nguồn evaluation/retrieval hiện có.

Sau đó:

* kiểm tra `git status`, branch và commit hiện tại;
* chạy full test suite trước khi sửa;
* ghi nhận các thay đổi có sẵn của người dùng;
* không sửa, xóa, format lại hoặc commit các thay đổi ngoài phạm vi.

Các thay đổi ngoài phạm vi đã biết có thể gồm:

* `docs/IMPLEMENTATION_SPEC.md`;
* `docs/PROJECT_OVERVIEW.md`;
* `interrupt_test*.ps1` đang untracked.

Nếu trạng thái thực tế khác báo cáo, ưu tiên bằng chứng trong repository và ghi rõ khác biệt.

## 2. Trạng thái đã hoàn thành — không làm lại

M0 mapping validator đã DONE:

* 20/20 video PASS;
* 60/60 mapping row PASS;
* 0 anomaly.

M1 BTC CLIP + FAISS đã DONE:

* 873 video;
* 177.321 vector;
* dimension 512;
* metadata 177.321 dòng;
* OpenCLIP `ViT-B-32`, pretrained `openai`;
* FAISS `IndexIDMap2(IndexFlatIP)`;
* checksum hợp lệ;
* self-query top-1 đúng, score `0.99999994`;
* text smoke query đã chạy end-to-end;
* full suite gần nhất: 18 tests;
* commit M1: `3d7267a4529caa89263abb9be8e1db9c6bcb008f`.

Không rebuild hoặc refactor M0/M1 nếu không có lỗi được chứng minh.

## 3. Mục tiêu duy nhất của task này

Thực hiện **Evaluation Closure cho baseline M1**.

Chưa bắt đầu:

* ASR/Whisper production;
* OCR;
* Objects pipeline;
* SigLIP;
* Query Planner;
* multimodal fusion;
* TRAKE implementation;
* Q&A/VLM;
* UI/backend;
* full-corpus preprocessing.

Mọi modality mới chỉ được xem xét sau khi baseline CLIP có metric định lượng và failure analysis.

## 4. Công việc bắt buộc

### A. Audit evaluation hiện có

Kiểm tra:

* schema `eval_experiments`, `eval_queries`, `eval_runs`;
* scorer hoặc runner đã có;
* CLI liên quan evaluation;
* format prediction hiện tại;
* tài liệu BTC/scoring contract hiện có trong repo;
* 35 query Group A có tồn tại trong workspace/repo hay không;
* query nào có ground truth thật, query nào chỉ có text mô tả.

Không được tự bịa `video_id`, frame range hoặc đáp án ground truth.

### B. Khóa evaluation data contract

Xây hoặc hoàn thiện contract có version, tối thiểu biểu diễn được:

* `query_id`;
* `query_type`: `KIS`, `QA`, `TRAKE`;
* `query_text`;
* `question_text` nếu có;
* `trap_category`;
* `split`;
* trạng thái labeled/unlabeled;
* `gt_video_id`;
* một hoặc nhiều inclusive frame ranges;
* `gt_answer` nếu có;
* provenance của label.

Trap categories tối thiểu:

* `visual`;
* `micro_moment`;
* `ocr_only`;
* `asr_only`;
* `event_chain`;
* `count`;
* `spatial_motion`.

Giữ DEV và HOLDOUT/canary tách biệt. HOLDOUT nên chiếm khoảng 20–30% số query đã được gắn ground truth và không được dùng để chỉnh weight hằng ngày.

Nếu 35 query Group A chưa có ground truth, import/phân loại chúng ở trạng thái `unlabeled_reference`; không đưa chúng vào mẫu số Recall@K.

### C. Xây scorer có kiểm chứng

Triển khai scorer theo registry/adapter cho từng query type.

Đối với KIS, nếu contract trong repo/tài liệu xác nhận, dùng quy tắc:

* candidate đúng khi `video_id` khớp và `frame_idx` nằm trong ít nhất một inclusive GT range;
* `R@k = 1` nếu có ít nhất một candidate đúng trong top-k, ngược lại bằng 0;
* tính cho `k = 1, 5, 20, 50, 100`;
* tính `first_correct_rank`;
* giới hạn tối đa 100 predictions/query;
* kết quả không được phụ thuộc vào thứ tự dictionary hoặc row tình cờ.

Đối với QA và TRAKE:

* chỉ triển khai logic chính thức khi scoring contract có bằng chứng trong repo/tài liệu;
* không tự suy diễn cách normalize answer hoặc chấm chuỗi sự kiện;
* nếu chưa đủ bằng chứng, tạo interface + validation + synthetic tests cần thiết, đánh dấu rõ `BLOCKED_BY_SCORING_CONTRACT`;
* không báo rằng scorer hoàn chỉnh nếu mới chỉ có interface.

Scorer phải xử lý an toàn:

* prediction rỗng;
* query không có label;
* duplicate prediction;
* candidate malformed;
* hơn 100 prediction;
* frame range đảo ngược hoặc không hợp lệ;
* query type không hỗ trợ;
* nhiều GT ranges;
* đáp án đúng xuất hiện đúng tại rank 1/5/20/50/100 và ngay ngoài cutoff.

### D. Baseline evaluation runner

Xây hoặc hoàn thiện runner có thể:

1. đọc eval dataset đã validate;
2. mã hóa query text bằng OpenCLIP `ViT-B-32/openai`;
3. query production FAISS index;
4. map stable ID về metadata;
5. ghi predictions;
6. chấm các query đã có ground truth;
7. bỏ riêng query unlabeled khỏi metric aggregate;
8. đo latency từng query và tổng hợp p50/p95 nếu đủ mẫu;
9. ghi failure/error record thay vì làm mất toàn bộ run;
10. lưu kết quả theo experiment có provenance.

Mỗi eval run phải ghi tối thiểu:

* pipeline/config description;
* git commit và dirty state;
* model name/pretrained tag;
* index/artifact version;
* index và metadata checksum nếu có;
* feature flags;
* query dataset hash/version;
* timestamp;
* số labeled/unlabeled/scored/failed;
* R@1/5/20/50/100;
* first-correct-rank;
* latency;
* breakdown theo query type và trap category khi có đủ label.

Không được tính query unlabeled như một query sai.

### E. CLI và output

Thêm CLI nhất quán với cấu trúc hiện tại để:

* validate eval dataset;
* chạy baseline evaluation;
* xem summary một eval run;
* xuất JSON/JSONL hoặc format artifact đang được repo sử dụng.

Không tạo một CLI framework mới nếu CLI hiện tại đã có convention.

Các lệnh phải có:

* exit code khác 0 khi contract/integrity lỗi;
* thông báo rõ khi không có query labeled;
* UTF-8 an toàn trên Windows;
* `--help` đủ hiểu;
* không mutate raw BTC data;
* không ghi trực tiếp vào artifact đã hoàn tất.

### F. Provenance decision

Artifact M1 hiện hợp lệ về checksum nhưng có provenance cần lưu ý:

* marker được tạo từ commit cũ dạng `9b2ecd8...+dirty`;
* model revision ban đầu từng là `unknown`;
* mã nguồn M1 hiện ở clean commit `3d7267a...`.

Hãy:

1. kiểm tra bằng chứng thực tế;
2. viết quyết định rõ ràng: artifact hiện tại có đủ dùng cho baseline evaluation hay cần rebuild version mới;
3. không sửa `DONE.json` cũ;
4. không overwrite artifact hợp lệ;
5. nếu rebuild không cần thiết cho task này, ghi thành technical debt có acceptance condition;
6. chỉ rebuild production artifact khi có lý do đo được và tuân thủ versioned artifact contract.

## 5. Kiểm thử bắt buộc

Thêm synthetic fixtures nhỏ, không phụ thuộc corpus 100 GB.

Test tối thiểu:

* KIS correct/incorrect;
* inclusive range boundaries;
* multiple GT ranges;
* first correct rank;
* R@1/5/20/50/100;
* empty predictions;
* duplicate predictions;
* cap 100;
* malformed records fail closed;
* unlabeled query không vào aggregate;
* split DEV/HOLDOUT không bị trộn;
* eval-run provenance được ghi;
* runner vẫn ghi lỗi theo query mà không làm mất các kết quả hợp lệ khác;
* CLI trả exit code đúng;
* regression: toàn bộ 18 tests cũ vẫn pass.

Chạy:

* targeted tests;
* full test suite;
* CLI smoke test trên synthetic data;
* nếu production index khả dụng, chạy baseline thật nhưng không được coi smoke test là quality benchmark khi thiếu ground truth.

## 6. Artifact và độ tin cậy

Giữ nguyên các quy tắc:

* BTC raw data read-only;
* stable IDs;
* relative paths;
* atomic write;
* checkpoint/resume khi có batch;
* optional path fail open;
* integrity failure fail closed;
* artifact chỉ hợp lệ khi count, manifest/config hash, model provenance, checksum và `DONE.json` khớp;
* không giản lược `DONE.json` thành cờ tồn tại đơn giản;
* không thêm PostgreSQL, Elasticsearch, Milvus, Qdrant, Airflow hoặc service mới.

## 7. Cập nhật tài liệu

Sau khi code và test xong:

* cập nhật `docs/TASKS.md`;
* cập nhật `docs/PROJECT_STATE.md`;
* cập nhật tài liệu evaluation/runbook liên quan;
* chỉ cập nhật README nếu không đè lên thay đổi ngoài phạm vi; nếu có xung đột, ghi rõ và để lại;
* ghi rõ phần nào DONE, PARTIAL hoặc BLOCKED;
* không tuyên bố M0B/evaluation hoàn chỉnh nếu chưa có ground truth đủ để tính baseline.

## 8. Acceptance criteria

Task chỉ được coi là hoàn thành khi:

* eval contract có version và validator;
* scorer KIS có test đầy đủ;
* QA/TRAKE chỉ được đánh dấu hoàn chỉnh nếu contract chính thức đã xác minh;
* runner ghi predictions, metrics, latency và provenance;
* unlabeled queries được phân biệt rõ;
* DEV/HOLDOUT được bảo vệ;
* baseline CLIP-only có thể chạy bằng một lệnh;
* full tests pass;
* không sửa dữ liệu BTC;
* không bắt đầu modality mới;
* mọi thay đổi ngoài phạm vi được giữ nguyên.

Nếu thiếu ground truth thật, kết quả hợp lệ phải là:

* framework/scorer/runner hoàn chỉnh ở phần có thể xác minh;
* 35 query được import/phân loại nhưng đánh dấu unlabeled;
* baseline prediction artifact được tạo;
* metric quality được ghi `BLOCKED_BY_GROUND_TRUTH`, không bịa số Recall@K.

## 9. Git và báo cáo cuối

Không stage hoặc commit file ngoài phạm vi.

Nếu repository rules cho phép và có thể tạo commit sạch chỉ chứa thay đổi của task này:

```text
feat(eval): add baseline scoring and evaluation runner
```

Nếu không thể commit an toàn vì working tree có thay đổi người dùng, không commit; báo rõ các file cần stage sau.

Báo cáo cuối phải gồm:

1. kết quả đạt được;
2. files changed;
3. commands/tests đã chạy;
4. test results;
5. metric thật nếu có;
6. labeled/unlabeled counts;
7. provenance decision;
8. known limitations/blockers;
9. rollback procedure;
10. bước hợp lệ tiếp theo.

Không hỏi lại người dùng trừ khi gặp hard stop về scoring contract, ground truth, quyền dữ liệu hoặc xung đột không thể bảo toàn an toàn. Trong mọi trường hợp khác, hãy tự kiểm tra repository và hoàn thành tối đa phạm vi được phép.

Bạn đang tiếp tục repository AIC 2026 với vai trò senior Python/ML systems engineer. Hãy trực tiếp kiểm tra, triển khai, kiểm thử và cập nhật trạng thái dự án; không chỉ viết kế hoạch.

## 1. Đọc trước khi làm

Đọc đầy đủ theo thứ tự:

1. `AGENTS.md`
2. `docs/PROJECT_OVERVIEW.md`
3. `docs/PROJECT_STATE.md`
4. `docs/TASKS.md`
5. `docs/DATA_CONTRACT.md`
6. `docs/DATA_CONTRACT_LOCK.md`
7. `docs/IMPLEMENTATION_SPEC.md`
8. `docs/RUNBOOK.md`
9. `docs/CLOUD_EXECUTION.md`
10. README và mã nguồn evaluation/retrieval hiện có.

Sau đó:

* kiểm tra `git status`, branch và commit hiện tại;
* chạy full test suite trước khi sửa;
* ghi nhận các thay đổi có sẵn của người dùng;
* không sửa, xóa, format lại hoặc commit các thay đổi ngoài phạm vi.

Các thay đổi ngoài phạm vi đã biết có thể gồm:

* `docs/IMPLEMENTATION_SPEC.md`;
* `docs/PROJECT_OVERVIEW.md`;
* `interrupt_test*.ps1` đang untracked.

Nếu trạng thái thực tế khác báo cáo, ưu tiên bằng chứng trong repository và ghi rõ khác biệt.

## 2. Trạng thái đã hoàn thành — không làm lại

M0 mapping validator đã DONE:

* 20/20 video PASS;
* 60/60 mapping row PASS;
* 0 anomaly.

M1 BTC CLIP + FAISS đã DONE:

* 873 video;
* 177.321 vector;
* dimension 512;
* metadata 177.321 dòng;
* OpenCLIP `ViT-B-32`, pretrained `openai`;
* FAISS `IndexIDMap2(IndexFlatIP)`;
* checksum hợp lệ;
* self-query top-1 đúng, score `0.99999994`;
* text smoke query đã chạy end-to-end;
* full suite gần nhất: 18 tests;
* commit M1: `3d7267a4529caa89263abb9be8e1db9c6bcb008f`.

Không rebuild hoặc refactor M0/M1 nếu không có lỗi được chứng minh.

## 3. Mục tiêu duy nhất của task này

Thực hiện **Evaluation Closure cho baseline M1**.

Chưa bắt đầu:

* ASR/Whisper production;
* OCR;
* Objects pipeline;
* SigLIP;
* Query Planner;
* multimodal fusion;
* TRAKE implementation;
* Q&A/VLM;
* UI/backend;
* full-corpus preprocessing.

Mọi modality mới chỉ được xem xét sau khi baseline CLIP có metric định lượng và failure analysis.

## 4. Công việc bắt buộc

### A. Audit evaluation hiện có

Kiểm tra:

* schema `eval_experiments`, `eval_queries`, `eval_runs`;
* scorer hoặc runner đã có;
* CLI liên quan evaluation;
* format prediction hiện tại;
* tài liệu BTC/scoring contract hiện có trong repo;
* 35 query Group A có tồn tại trong workspace/repo hay không;
* query nào có ground truth thật, query nào chỉ có text mô tả.

Không được tự bịa `video_id`, frame range hoặc đáp án ground truth.

### B. Khóa evaluation data contract

Xây hoặc hoàn thiện contract có version, tối thiểu biểu diễn được:

* `query_id`;
* `query_type`: `KIS`, `QA`, `TRAKE`;
* `query_text`;
* `question_text` nếu có;
* `trap_category`;
* `split`;
* trạng thái labeled/unlabeled;
* `gt_video_id`;
* một hoặc nhiều inclusive frame ranges;
* `gt_answer` nếu có;
* provenance của label.

Trap categories tối thiểu:

* `visual`;
* `micro_moment`;
* `ocr_only`;
* `asr_only`;
* `event_chain`;
* `count`;
* `spatial_motion`.

Giữ DEV và HOLDOUT/canary tách biệt. HOLDOUT nên chiếm khoảng 20–30% số query đã được gắn ground truth và không được dùng để chỉnh weight hằng ngày.

Nếu 35 query Group A chưa có ground truth, import/phân loại chúng ở trạng thái `unlabeled_reference`; không đưa chúng vào mẫu số Recall@K.

### C. Xây scorer có kiểm chứng

Triển khai scorer theo registry/adapter cho từng query type.

Đối với KIS, nếu contract trong repo/tài liệu xác nhận, dùng quy tắc:

* candidate đúng khi `video_id` khớp và `frame_idx` nằm trong ít nhất một inclusive GT range;
* `R@k = 1` nếu có ít nhất một candidate đúng trong top-k, ngược lại bằng 0;
* tính cho `k = 1, 5, 20, 50, 100`;
* tính `first_correct_rank`;
* giới hạn tối đa 100 predictions/query;
* kết quả không được phụ thuộc vào thứ tự dictionary hoặc row tình cờ.

Đối với QA và TRAKE:

* chỉ triển khai logic chính thức khi scoring contract có bằng chứng trong repo/tài liệu;
* không tự suy diễn cách normalize answer hoặc chấm chuỗi sự kiện;
* nếu chưa đủ bằng chứng, tạo interface + validation + synthetic tests cần thiết, đánh dấu rõ `BLOCKED_BY_SCORING_CONTRACT`;
* không báo rằng scorer hoàn chỉnh nếu mới chỉ có interface.

Scorer phải xử lý an toàn:

* prediction rỗng;
* query không có label;
* duplicate prediction;
* candidate malformed;
* hơn 100 prediction;
* frame range đảo ngược hoặc không hợp lệ;
* query type không hỗ trợ;
* nhiều GT ranges;
* đáp án đúng xuất hiện đúng tại rank 1/5/20/50/100 và ngay ngoài cutoff.

### D. Baseline evaluation runner

Xây hoặc hoàn thiện runner có thể:

1. đọc eval dataset đã validate;
2. mã hóa query text bằng OpenCLIP `ViT-B-32/openai`;
3. query production FAISS index;
4. map stable ID về metadata;
5. ghi predictions;
6. chấm các query đã có ground truth;
7. bỏ riêng query unlabeled khỏi metric aggregate;
8. đo latency từng query và tổng hợp p50/p95 nếu đủ mẫu;
9. ghi failure/error record thay vì làm mất toàn bộ run;
10. lưu kết quả theo experiment có provenance.

Mỗi eval run phải ghi tối thiểu:

* pipeline/config description;
* git commit và dirty state;
* model name/pretrained tag;
* index/artifact version;
* index và metadata checksum nếu có;
* feature flags;
* query dataset hash/version;
* timestamp;
* số labeled/unlabeled/scored/failed;
* R@1/5/20/50/100;
* first-correct-rank;
* latency;
* breakdown theo query type và trap category khi có đủ label.

Không được tính query unlabeled như một query sai.

### E. CLI và output

Thêm CLI nhất quán với cấu trúc hiện tại để:

* validate eval dataset;
* chạy baseline evaluation;
* xem summary một eval run;
* xuất JSON/JSONL hoặc format artifact đang được repo sử dụng.

Không tạo một CLI framework mới nếu CLI hiện tại đã có convention.

Các lệnh phải có:

* exit code khác 0 khi contract/integrity lỗi;
* thông báo rõ khi không có query labeled;
* UTF-8 an toàn trên Windows;
* `--help` đủ hiểu;
* không mutate raw BTC data;
* không ghi trực tiếp vào artifact đã hoàn tất.

### F. Provenance decision

Artifact M1 hiện hợp lệ về checksum nhưng có provenance cần lưu ý:

* marker được tạo từ commit cũ dạng `9b2ecd8...+dirty`;
* model revision ban đầu từng là `unknown`;
* mã nguồn M1 hiện ở clean commit `3d7267a...`.

Hãy:

1. kiểm tra bằng chứng thực tế;
2. viết quyết định rõ ràng: artifact hiện tại có đủ dùng cho baseline evaluation hay cần rebuild version mới;
3. không sửa `DONE.json` cũ;
4. không overwrite artifact hợp lệ;
5. nếu rebuild không cần thiết cho task này, ghi thành technical debt có acceptance condition;
6. chỉ rebuild production artifact khi có lý do đo được và tuân thủ versioned artifact contract.

## 5. Kiểm thử bắt buộc

Thêm synthetic fixtures nhỏ, không phụ thuộc corpus 100 GB.

Test tối thiểu:

* KIS correct/incorrect;
* inclusive range boundaries;
* multiple GT ranges;
* first correct rank;
* R@1/5/20/50/100;
* empty predictions;
* duplicate predictions;
* cap 100;
* malformed records fail closed;
* unlabeled query không vào aggregate;
* split DEV/HOLDOUT không bị trộn;
* eval-run provenance được ghi;
* runner vẫn ghi lỗi theo query mà không làm mất các kết quả hợp lệ khác;
* CLI trả exit code đúng;
* regression: toàn bộ 18 tests cũ vẫn pass.

Chạy:

* targeted tests;
* full test suite;
* CLI smoke test trên synthetic data;
* nếu production index khả dụng, chạy baseline thật nhưng không được coi smoke test là quality benchmark khi thiếu ground truth.

## 6. Artifact và độ tin cậy

Giữ nguyên các quy tắc:

* BTC raw data read-only;
* stable IDs;
* relative paths;
* atomic write;
* checkpoint/resume khi có batch;
* optional path fail open;
* integrity failure fail closed;
* artifact chỉ hợp lệ khi count, manifest/config hash, model provenance, checksum và `DONE.json` khớp;
* không giản lược `DONE.json` thành cờ tồn tại đơn giản;
* không thêm PostgreSQL, Elasticsearch, Milvus, Qdrant, Airflow hoặc service mới.

## 7. Cập nhật tài liệu

Sau khi code và test xong:

* cập nhật `docs/TASKS.md`;
* cập nhật `docs/PROJECT_STATE.md`;
* cập nhật tài liệu evaluation/runbook liên quan;
* chỉ cập nhật README nếu không đè lên thay đổi ngoài phạm vi; nếu có xung đột, ghi rõ và để lại;
* ghi rõ phần nào DONE, PARTIAL hoặc BLOCKED;
* không tuyên bố M0B/evaluation hoàn chỉnh nếu chưa có ground truth đủ để tính baseline.

## 8. Acceptance criteria

Task chỉ được coi là hoàn thành khi:

* eval contract có version và validator;
* scorer KIS có test đầy đủ;
* QA/TRAKE chỉ được đánh dấu hoàn chỉnh nếu contract chính thức đã xác minh;
* runner ghi predictions, metrics, latency và provenance;
* unlabeled queries được phân biệt rõ;
* DEV/HOLDOUT được bảo vệ;
* baseline CLIP-only có thể chạy bằng một lệnh;
* full tests pass;
* không sửa dữ liệu BTC;
* không bắt đầu modality mới;
* mọi thay đổi ngoài phạm vi được giữ nguyên.

Nếu thiếu ground truth thật, kết quả hợp lệ phải là:

* framework/scorer/runner hoàn chỉnh ở phần có thể xác minh;
* 35 query được import/phân loại nhưng đánh dấu unlabeled;
* baseline prediction artifact được tạo;
* metric quality được ghi `BLOCKED_BY_GROUND_TRUTH`, không bịa số Recall@K.

## 9. Git và báo cáo cuối

Không stage hoặc commit file ngoài phạm vi.

Nếu repository rules cho phép và có thể tạo commit sạch chỉ chứa thay đổi của task này:

```text
feat(eval): add baseline scoring and evaluation runner
```

Nếu không thể commit an toàn vì working tree có thay đổi người dùng, không commit; báo rõ các file cần stage sau.

Báo cáo cuối phải gồm:

1. kết quả đạt được;
2. files changed;
3. commands/tests đã chạy;
4. test results;
5. metric thật nếu có;
6. labeled/unlabeled counts;
7. provenance decision;
8. known limitations/blockers;
9. rollback procedure;
10. bước hợp lệ tiếp theo.

Không hỏi lại người dùng trừ khi gặp hard stop về scoring contract, ground truth, quyền dữ liệu hoặc xung đột không thể bảo toàn an toàn. Trong mọi trường hợp khác, hãy tự kiểm tra repository và hoàn thành tối đa phạm vi được phép.

# Báo cáo tổng quan dự án AIC 2026

**Ngày cập nhật:** 11/08/2026
**Commit mã nguồn hiện hành:** `3d7267a4529caa89263abb9be8e1db9c6bcb008f`
**Trạng thái:** M0 và M1 đã hoàn tất; milestone tiếp theo chưa được phê duyệt.

## 1. Giới thiệu

Dự án AIC 2026 xây dựng nền tảng truy hồi video trên bộ dữ liệu BTC. Repository hiện đóng vai trò **control plane** (lớp điều phối và kiểm soát độ tin cậy), quản lý cấu hình, hợp đồng dữ liệu, kiểm tra tính toàn vẹn, xử lý có checkpoint, metadata và chỉ mục truy hồi. Dữ liệu video, keyframe, vector đặc trưng và các artifact dung lượng lớn không được lưu trong Git.

Triết lý kỹ thuật của dự án là ưu tiên tính đúng đắn và khả năng khôi phục trước tốc độ phát triển tính năng. Mọi ánh xạ frame phải có bằng chứng; mọi batch job phải có thể tiếp tục sau gián đoạn; artifact chỉ hợp lệ khi có checksum và `DONE.json`; dữ liệu BTC nguồn luôn ở chế độ chỉ đọc.

## 2. Mục tiêu

Các mục tiêu đã được triển khai đến thời điểm hiện tại gồm:

1. Xây dựng scaffold chạy cục bộ, Colab và Kaggle có tính tái lập.
2. Bảo đảm batch job có checkpoint, resume, shard và cơ chế finalization atomic.
3. Khóa hợp đồng ánh xạ giữa video, CSV, keyframe và CLIP.
4. Xác thực mapping trên dữ liệu BTC thật trước khi xây retrieval.
5. Nạp toàn bộ vector CLIP hợp lệ và xây baseline FAISS.
6. Cung cấp truy hồi vector-to-keyframe và text-to-keyframe bằng encoder tương thích.

Các mục tiêu chưa triển khai gồm OCR, ASR, Objects, SigLIP, TRAKE, scorer hoàn chỉnh và giao diện ứng dụng.

## 3. Kiến trúc hệ thống

### 3.1. Phân chia trách nhiệm

| Thành phần            | Trách nhiệm                                                                                      |
| ----------------------- | -------------------------------------------------------------------------------------------------- |
| Git repository          | Mã nguồn, test, tài liệu, config mẫu và manifest nhỏ không chứa dữ liệu riêng tư      |
| Google Drive/BTC corpus | Nguồn video, keyframe, CSV mapping và feature CLIP ở chế độ chỉ đọc                       |
| Máy Windows cục bộ   | Control plane, SQLite authority, FAISS index, cache và artifact đã xác thực                   |
| Colab/Kaggle            | Worker tạm thời xử lý shard xác định trước; không ghi trực tiếp vào production SQLite |

### 3.2. Vòng đời xử lý

Quy trình chuẩn được quy định như sau:

```text
PILOT → VALIDATE → BENCHMARK → GO/NO-GO → SHARD
      → RUN → FINALIZE → VERIFY → LOCAL IMPORT
```

Một shard hoàn chỉnh có vòng đời:

```text
manifest shard
  → checkpoint.json
  → results.partial.jsonl
  → results.jsonl.tmp
  → results.jsonl
  → checksum
  → DONE.json
```

`DONE.json` luôn được ghi cuối. Artifact không có marker này hoặc có checksum không khớp phải bị từ chối.

## 4. Hợp đồng dữ liệu đã khóa

### 4.1. Quy mô canonical

| Chỉ số              | Giá trị đã xác nhận |
| --------------------- | ------------------------: |
| Video canonical       |                       873 |
| Keyframe BTC hợp lệ |                   177.321 |
| File feature CLIP     |                       873 |
| Dimension CLIP        |                       512 |

### 4.2. Quy tắc mapping

CSV keyframe có schema:

```text
n, pts_time, fps, frame_idx
```

Các bất biến bắt buộc:

```text
keyframe ordinal = CSV.n
clip_row          = CSV.n - 1
frame_idx         = tọa độ frame trong video gốc
```

`frame_idx` độc lập với tên keyframe và không được dùng để suy ra filename. Ví dụ hợp lệ:

| Keyframe    | CSV.n | CLIP row |        CSV.frame_idx | Kết luận |
| ----------- | ----: | -------: | -------------------: | ---------- |
| `001.jpg` |     1 |        0 |                    0 | Hợp lệ   |
| `002.jpg` |     2 |        1 |                   75 | Hợp lệ   |
| `154.jpg` |   154 |      153 | Giá trị video gốc | Hợp lệ   |

Do đó, `frame_idx=0` không yêu cầu file `000000.jpg`. Exact-frame extraction về sau phải dùng mapping đã xác minh và FFmpeg theo PTS; OpenCV `CAP_PROP_POS_FRAMES` không phải nguồn authoritative.

### 4.3. Quy tắc đường dẫn và stable ID

- Mọi đường dẫn lưu bền phải là POSIX-style relative path.
- Không lưu drive letter, đường dẫn Colab/Kaggle hoặc đường dẫn máy cá nhân trong manifest, SQLite và metadata FAISS.
- Stable ID không được phụ thuộc vào thứ tự duyệt file hoặc thứ tự row tình cờ.
- M1 dùng `keyframe_id = "<video_id>:<CSV.n>"` và sinh `embedding_id` dương 63-bit ổn định bằng BLAKE2b.

## 5. Thành phần mã nguồn hiện có

### 5.1. Core

Thư mục `src/aic2026/core/` cung cấp:

- nạp và merge cấu hình TOML;
- resolver cho data, work và artifact root;
- chuẩn hóa và từ chối absolute path;
- SHA-256 cho file/bytes;
- ghi text, bytes và JSON theo cơ chế atomic replace.

### 5.2. Job reliability

Thư mục `src/aic2026/jobs/` cung cấp:

- schema manifest và shard xác định;
- checkpoint theo item;
- khôi phục JSONL bị ngắt ở dòng cuối;
- retry có giới hạn;
- resume và bỏ qua item đã hoàn tất;
- finalization với checksum và marker;
- validator artifact và status scanner.

Batch operation được thiết kế theo các thuộc tính resumable, idempotent, shardable và atomic tại thời điểm finalization.

### 5.3. Dataset audit

Thư mục `src/aic2026/audit/` gồm:

- `discovery.py`: inventory video, keyframe và filesystem;
- `modalities.py`: kiểm tra metadata và modality tùy chọn;
- `mapping.py`: kiểm tra mapping video/CSV/keyframe, tách biệt `n` và `frame_idx`;
- `clip.py`: kiểm tra shape, dtype và count feature CLIP;
- `report.py`: tổng hợp báo cáo audit.

Objects là modality không đầy đủ và phải **fail open**. Trái lại, duplicate stable ID, count mismatch, dimension mismatch, mapping không chắc chắn hoặc checksum sai phải **fail closed**.

### 5.4. SQLite

`src/aic2026/db/schema.sql` hiện định nghĩa schema nền tảng cho:

- `videos` và `keyframes`;
- metadata `embeddings`;
- transcript và FTS5;
- OCR text và FTS5;
- processing jobs;
- eval experiments, queries và runs.

Schema hỗ trợ query type `KIS`, `QA` và `TRAKE`. SQLite hiện là authority cục bộ theo thiết kế; cloud worker không được mutate production database.

### 5.5. CLIP + FAISS retrieval

`src/aic2026/retrieval/clip_faiss.py` triển khai M1:

- tạo manifest từ ba thư mục canonical đã khóa;
- xác thực tập video giữa CSV, keyframe và CLIP;
- xác thực từng mapping `clip_row ↔ CSV.n ↔ keyframe ordinal`;
- từ chối manifest rỗng, video trùng, file thiếu, count lệch và dimension không đồng nhất;
- từ chối vector chứa NaN, infinity hoặc zero norm;
- chuẩn hóa L2 vector sang `float32`;
- xây `faiss.IndexIDMap2(faiss.IndexFlatIP)`;
- ghi `clip.index`, `metadata.jsonl` và `DONE.json` theo thứ tự an toàn;
- hỗ trợ query vector và query text.

Cosine similarity được tính qua inner product sau chuẩn hóa:

```text
x̂ = x / ||x||₂
q̂ = q / ||q||₂
cos(q, x) = q̂ᵀx̂
```

Text encoder được xác nhận từ notebook BTC là OpenCLIP `ViT-B-32` với pretrained tag `openai`.

## 6. CLI hiện có

CLI `aic2026.cli` hỗ trợ các nhóm lệnh:

| Nhóm         | Lệnh tiêu biểu                                                            | Chức năng                                           |
| ------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------- |
| Môi trường | `doctor`, `init-db`                                                      | Kiểm tra prerequisite và khởi tạo SQLite          |
| Manifest/job  | `demo-manifest`, `shard`, `run-shard`, `status`                      | Tạo workload, chia shard, chạy/resume và theo dõi |
| Artifact      | `validate-artifact`                                                        | Kiểm tra marker, count và checksum                  |
| Audit         | `audit-dataset`, `audit-frame-mapping`, `audit-clip`, `audit-report` | Kiểm tra corpus và mapping                          |
| M1 retrieval  | `build-clip-manifest`, `build-clip-index`                                | Tạo manifest và FAISS index                         |
| Search        | `search-clip-index`, `search-clip-text`                                  | Query bằng vector hoặc text                         |

CLI cấu hình UTF-8 cho stdout/stderr để tránh lỗi `cp1252` khi hiển thị tiếng Việt trên Windows.

## 7. Thực nghiệm và kết quả

### 7.1. M0 mapping validation

Validator M0 chạy trên 20 video canonical, chọn mẫu đầu–giữa–cuối của mỗi video:

| Chỉ số                      | Kết quả |
| ----------------------------- | --------: |
| Video được kiểm tra       |        20 |
| Mapping row được kiểm tra |        60 |
| Video PASS                    |        20 |
| Video FAIL                    |         0 |
| Anomaly                       |         0 |
| Verdict                       |      PASS |

Validator đã được sửa để trả `FAIL` và exit code khác 0 nếu không chọn được video nào. Điều này loại bỏ false PASS dạng `0/0` khi Google Drive chưa được mount.

### 7.2. M1 production index

| Chỉ số             |                           Kết quả |
| -------------------- | ----------------------------------: |
| Video trong manifest |                                 873 |
| Vector expected      |                             177.321 |
| Vector processed     |                             177.321 |
| Failure              |                                   0 |
| Dimension            |                                 512 |
| FAISS metric         | Cosine qua normalized inner product |
| Metadata row         |                             177.321 |
| Index checksum       |                            Hợp lệ |
| Metadata checksum    |                            Hợp lệ |

Artifact production có các file:

- `clip.index`: FAISS index, khoảng 365 MB;
- `metadata.jsonl`: stable-ID mapping, khoảng 40 MB;
- `DONE.json`: model/config/manifest metadata và checksum.

Self-query dùng vector đầu tiên trả đúng stable ID ở top-1 với score `0,99999994`.

### 7.3. Text-to-keyframe smoke test

Query thử nghiệm:

```text
a person riding a bicycle
```

OpenCLIP đã mã hóa query và FAISS trả top-5 kết quả. Stable ID được ánh xạ thành công về các keyframe thuộc `L23_V007`, `L28_V009` và `L30_V001`. Điều này chứng minh đường chạy end-to-end từ text encoder đến FAISS và metadata hoạt động.

Smoke test chỉ chứng minh khả năng vận hành, chưa phải đánh giá chất lượng retrieval. Chưa có ground-truth benchmark để kết luận Recall@K hoặc điểm AIC.

### 7.4. Kiểm thử phần mềm

Full test suite gần nhất:

```text
18 passed
```

Test hiện bao phủ:

- relative-path contract;
- manifest và deterministic shard;
- checkpoint/resume;
- artifact corruption detection;
- SQLite schema và FTS trigger;
- audit pipeline;
- mapping `001.jpg + n=1 + frame_idx=0`;
- mapping `002.jpg + n=2 + frame_idx=75`;
- `clip_row 0 → n=1` và `clip_row 1 → n=2`;
- M0 validator fail-closed khi không có sample;
- xây, đọc và query FAISS index;
- từ chối `CSV.n` không tuần tự;
- manifest M1 chỉ dùng relative path.

## 8. Artifact và khả năng tái lập

Artifact M1 ghi nhận:

- `expected_count = processed_count = 177321`;
- `failures = 0`;
- `vector_dim = 512`;
- SHA-256 cho input manifest, index và metadata;
- model, model revision, config hash và git state tại thời điểm build.

Có một khác biệt provenance cần lưu ý: artifact được dựng trước commit M1 cuối, vì vậy marker ghi `9b2ecd8...+dirty`, trong khi mã nguồn M1 sau khi commit là `3d7267a...`. Index và checksum đã được xác minh độc lập, nhưng nếu yêu cầu provenance tuyệt đối gắn với commit sạch thì phải tạo artifact version mới; không được sửa marker của artifact đã hoàn tất.

## 9. Rủi ro và hạn chế

### 9.1. Rủi ro kỹ thuật

1. **I/O Google Drive:** duyệt nhiều file riêng lẻ có độ trễ lớn. M1 đã tối ưu bằng cách liệt kê filename một lần cho mỗi video thay vì gọi `stat` cho từng keyframe.
2. **Model provenance:** notebook BTC xác nhận `ViT-B-32/openai`, nhưng artifact đầu tiên được tạo trước khi bằng chứng này được tìm thấy nên trường revision vẫn ghi unknown.
3. **QuickGELU warning:** OpenCLIP phát cảnh báo mismatch cấu hình QuickGELU với pretrained tag. Không được tự đổi model nếu chưa có benchmark và bằng chứng tương thích với vector BTC.
4. **Chất lượng retrieval chưa được đo:** mới có self-query và text smoke test; chưa có Recall@K, latency benchmark có kiểm soát hoặc scorer chính thức.
5. **Objects không đầy đủ:** Objects phải tiếp tục là modality tùy chọn; thiếu Objects không được làm hỏng baseline CLIP.
6. **README chưa đồng bộ:** README vẫn mô tả trạng thái trước M1 và cần được cập nhật ở một thay đổi tài liệu riêng.

### 9.2. Trạng thái working tree tại thời điểm lập báo cáo

Branch `main` đang đồng bộ với `origin/main` tại commit `3d7267a`. Working tree có các thay đổi ngoài M1 chưa được commit:

- `docs/IMPLEMENTATION_SPEC.md` có nội dung chỉnh sửa ngoài phạm vi;
- `docs/PROJECT_OVERVIEW.md` là báo cáo mới được tạo trong yêu cầu hiện tại;
- ba script `interrupt_test*.ps1` đang untracked.

Các file này không thuộc commit M1 và không được tự động sửa hoặc xóa.

## 10. Các hạng mục chưa thực hiện

| Hạng mục | Trạng thái                       | Ghi chú                                                                   |
| ---------- | ---------------------------------- | -------------------------------------------------------------------------- |
| OCR        | Chưa thực hiện                  | Không được khởi chạy trước khi milestone mới được phê duyệt  |
| ASR        | Chưa thực hiện                  | Whisper/ASR phải là modality fail-open                                   |
| Objects    | Dữ liệu nguồn không đầy đủ | Chưa có pipeline production                                              |
| SigLIP     | Chưa thực hiện                  | Cần pilot và benchmark trước full-corpus job                           |
| TRAKE      | Chưa thực hiện                  | Timestamp chỉ là anchor; frame nộp bài phải dùng mapping chính xác |
| AIC scorer | Chưa hoàn chỉnh                 | Schema eval đã hỗ trợ KIS/QA/TRAKE                                     |
| UI         | Chưa thực hiện                  | Chưa có backend/API giao diện được phê duyệt                       |

## 11. Đề xuất milestone tiếp theo

Milestone tiếp theo chưa được định nghĩa chính thức. Trước khi triển khai, nên phê duyệt rõ mục tiêu và acceptance criteria. Thứ tự khuyến nghị:

1. Xây eval set nhỏ và scorer baseline cho CLIP retrieval.
2. Đo Recall@1/5/20/50/100 và latency trên dev split.
3. Khóa model provenance và tái tạo artifact từ clean commit nếu cần.
4. Chỉ sau baseline định lượng mới chọn modality bổ sung bằng pilot có đo lường.

Không nên bắt đầu đồng thời OCR, ASR, Objects và SigLIP. Mỗi modality cần đi qua quy trình pilot → validate → benchmark → GO/NO-GO trước production shard.

## 12. Kết luận

Dự án đã hoàn tất hai cột mốc nền tảng. M0 thiết lập độ tin cậy và khóa chính xác hợp đồng mapping dữ liệu. M1 nạp đủ 177.321 vector CLIP, xây FAISS index có stable ID, checksum và atomic finalization, đồng thời chứng minh truy hồi vector và text hoạt động end-to-end.

Hệ thống hiện có nền tảng tốt để chuyển sang đánh giá định lượng và thiết kế milestone tiếp theo. Rủi ro chính không còn nằm ở mapping cơ bản mà nằm ở provenance model, chất lượng retrieval chưa được benchmark, độ trễ I/O và nguy cơ mở rộng quá sớm sang nhiều modality chưa có acceptance criteria.

## 13. Tài liệu liên quan

- `AGENTS.md`: quy tắc kỹ thuật bắt buộc.
- `docs/DATA_CONTRACT.md`: hợp đồng đường dẫn và artifact.
- `docs/DATA_CONTRACT_LOCK.md`: mapping canonical đã khóa.
- `docs/IMPLEMENTATION_SPEC.md`: đặc tả kiến trúc và lifecycle.
- `docs/PROJECT_STATE.md`: trạng thái milestone hiện tại.
- `docs/TASKS.md`: hàng đợi công việc.
- `docs/RUNBOOK.md`: hướng dẫn vận hành.
- `docs/CLOUD_EXECUTION.md`: quy tắc worker Colab/Kaggle.
