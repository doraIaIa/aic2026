# 📦 AIC 2026 — TÀI LIỆU HƯỚNG DẪN BÀN GIAO TOÀN DIỆN (HANDOVER GUIDE)

Tài liệu này dành cho thành viên mới tiếp nhận dự án **AIC 2026** (Hệ thống tìm kiếm video đa phương thức Multi-modal Video Retrieval).

---

## 🗺️ 1. TỔNG QUAN KIẾN TRÚC DỰ ÁN

Dự án gồm **3 phần tách biệt**:

```
                              HỆ THỐNG AIC 2026
 ┌───────────────────────────┬───────────────────────────┬───────────────────────────┐
 │   1. BACKEND CORE (Git)   │   2. FRONTEND UI (Git)    │ 3. DATA & ARTIFACTS (Ổ đĩa│
 ├───────────────────────────┼───────────────────────────┼───────────────────────────┤
 │ Thư mục: aic2026/         │ Thư mục:                  │ Thư mục:                  │
 │ (Repo: doraIaIa/aic2026)  │ aic-video-search-demo/    │ F:\AIC_WORK\artifacts\    │
 │                           │                           │                           │
 │ • 10 Search Lanes         │ • React + TypeScript      │ • mapping.sqlite (1.1 GB) │
 │   (Visual, ASR, OCR,      │ • Vite + TailwindCSS      │ • FAISS Dense Index (.faiss│
 │    Qwen, Media)           │ • Evidence Preview Player │ • SQLite Lexical/FTS Index│
 │ • FastAPI Server (port    │ • Video Timeline Viewer   │ • Keyframe image maps     │
 │   8000)                   │ • Multi-modal Filter UI   │                           │
 │ • CLI & Benchmark Runner  │                           │                           │
 └───────────────────────────┴───────────────────────────┴───────────────────────────┘
```

---

## 🗄️ 2. DANH SÁCH DỮ LIỆU & INDEX CẦN BÀN GIAO (KHÔNG COMMIT LÊN GIT)

Bạn chỉ cần copy **thư mục `artifacts`** (qua ổ cứng di động hoặc Google Drive) và đặt vào máy mới:

```text
F:\AIC_WORK\artifacts\
├── retrieval_data_v1\
│   └── runtime\
│       └── mapping.sqlite          <-- DATABASE TRUNG TÂM (116,767 keyframes, ASR, OCR, Qwen, Media)
│
└── retrieval_v2\
    ├── siglip_custom_v1\          <-- Visual SigLIP FAISS Index (342 MB)
    │   ├── siglip_custom.faiss
    │   └── siglip_custom_passport.json
    │
    ├── btc_clip_v1\               <-- Visual BTC CLIP FAISS Index (435 MB)
    │   ├── btc_clip.faiss
    │   └── btc_clip_passport.json
    │
    ├── asr_bge_v1\                <-- ASR Dense BGE-M3 Index (420 MB, 107,540 segments)
    │   ├── asr_bge.faiss
    │   ├── asr_bge_rowmap.jsonl
    │   └── asr_bge_passport.json
    │
    ├── ocr_bge_v1\                <-- OCR Dense BGE-M3 Index (2.4 GB, 612,813 items)
    │   ├── ocr_bge.faiss
    │   ├── ocr_bge_rowmap.jsonl
    │   └── ocr_bge_passport.json
    │
    ├── ocr_trigram_v1\            <-- OCR Typo-tolerant Index (186 MB)
    │   ├── ocr_trigram.sqlite
    │   └── ocr_trigram_passport.json
    │
    └── qwen_structured_v1\        <-- Qwen Facet SQLite Index (752 MB, 670,787 facets)
        ├── qwen_facets.sqlite
        └── qwen_structured_passport.json
```

---

## 🚀 3. HƯỚNG DẪN CÀI ĐẶT & CHẠY DỰ ÁN TRÊN MÁY MỚI (3 BƯỚC)

### BƯỚC 1: Cài đặt Backend Python
```powershell
# 1. Clone repo Backend
git clone https://github.com/doraIaIa/aic2026.git aic2026
cd aic2026

# 2. Tạo virtualenv và cài đặt dependencies
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
pip install fastapi uvicorn

# 3. Cài đặt PyTorch CUDA (nếu máy có GPU NVIDIA)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

---

### BƯỚC 2: Kiểm tra dữ liệu bàn giao (1 Lệnh duy nhất)
Chạy script kiểm tra tự động để đảm bảo máy mới nhận đủ data, GPU và index:
```powershell
python scripts/verify_handover.py
```
> *Nếu bạn đặt data ở ổ đĩa khác (ví dụ `D:\AIC_WORK`), chỉ cần đặt biến môi trường:*
> ```powershell
> $env:AIC_MAPPING_DB="D:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite"
> $env:AIC_ARTIFACTS_DIR="D:\AIC_WORK\artifacts\retrieval_v2"
> python scripts/verify_handover.py
> ```

---

### BƯỚC 3: Khởi động Hệ thống

#### 1. Khởi động Backend API (Cổng 8000):
```powershell
cd aic2026
.\.venv\Scripts\activate
uvicorn aic2026.search.api:app --host 0.0.0.0 --port 8000 --reload
```
* API Docs Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

#### 2. Khởi động Frontend UI (Cổng 5173):
```powershell
cd ..\aic-video-search-demo\client
npm install
npm run dev
```
* Mở trình duyệt: [http://localhost:5173](http://localhost:5173)

---

## 🔍 4. DANH SÁCH 10 SEARCH LANES ĐÃ SẴN SÀNG

| STT | Tên Lane | Modality | Loại Index / Thuật toán | Evidence Type |
| :---: | :--- | :--- | :--- | :--- |
| 1 | `siglip_custom` | Visual | Google SigLIP (1152D) FAISS FlatIP | `CUSTOM_FRAME` |
| 2 | `btc_clip` | Visual | OpenCLIP ViT-B/32 (512D) FAISS FlatIP | `BTC_KEYFRAME` |
| 3 | `asr_bm25` | ASR / Speech | SQLite FTS5 BM25 | `ASR_SEGMENT` |
| 4 | `asr_bge` | ASR / Speech | BAAI/bge-m3 (1024D) FAISS FlatIP | `ASR_SEGMENT` |
| 5 | `ocr_bm25` | Text on screen | SQLite FTS5 BM25 | `OCR_ITEM` |
| 6 | `ocr_trigram`| Text on screen | SQLite Trigram Typo-tolerant | `OCR_ITEM` |
| 7 | `ocr_bge` | Text on screen | BAAI/bge-m3 (1024D) FAISS FlatIP | `OCR_ITEM` |
| 8 | `media_bm25` | Metadata | Video Title / Author / Tags BM25 | `VIDEO` |
| 9 | `qwen_structured` | Semantic Vision | 6 Namespaces (Obj/Attr/Scn/Act/Rel/Cnt) | `CUSTOM_FRAME` |
| 10 | `qwen_bm25` | Semantic Vision | Qwen Caption FTS5 BM25 | `CUSTOM_FRAME` |

---

## 🛠️ 5. CÁC LỆNH CLI HỮU ÍCH

```powershell
# Kiểm tra sức khỏe lane
aic qwen-structured-health
aic asr-bm25-health
aic ocr-bge-health

# Tìm kiếm trực tiếp trên dòng lệnh
aic search-qwen-structured "motorcycle riding" --top-k 10
aic search-asr-bm25 "thành phố Hồ Chí Minh" --top-k 10
aic search-ocr-trigram "truyền hình" --top-k 10
aic search-media-bm25 "thời sự" --top-k 10
```

---

## 📞 HỖ TRỢ KỸ THUẬT & LIÊN HỆ
Mọi thắc mắc về data schema, FAISS indexing hoặc backend API, vui lòng tham khảo các tài liệu chi tiết tại `docs/retrieval_v2/` hoặc trao đổi trực tiếp với team.
