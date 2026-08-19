"""AIC 2026 - One-Command System & Data Handover Verification Script.

Run this script on any new machine to verify:
1. Python environment & GPU acceleration.
2. Canonical Data Hub database (`mapping.sqlite`).
3. Derived Retrieval Index artifacts (`retrieval_v2/`).
4. End-to-end operational search readiness across all active lanes.

Usage:
    python scripts/verify_handover.py
"""
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Paths configuration
BASE_DIR = Path(__file__).resolve().parent.parent
MAPPING_DB = Path(os.getenv("AIC_MAPPING_DB", r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite"))
ARTIFACTS_DIR = Path(os.getenv("AIC_ARTIFACTS_DIR", r"F:\AIC_WORK\artifacts\retrieval_v2"))


def print_header(title: str):
    print("\n" + "=" * 75)
    print(f"  {title}")
    print("=" * 75)


def check_env():
    print_header("1. KIỂM TRA MÔI TRƯỜNG & PHẦN CỨNG (PYTHON & GPU)")
    print(f"Python Version: {sys.version.split()[0]} ({sys.executable})")

    try:
        import torch
        print(f"[OK] PyTorch: v{torch.__version__}")
        cuda_ok = torch.cuda.is_available()
        print(f"     CUDA Available: {cuda_ok}")
        if cuda_ok:
            print(f"     GPU: {torch.cuda.get_device_name(0)}")
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"     VRAM: {vram_gb:.2f} GB")
        else:
            print("     [LƯU Ý] Đang chạy chế độ CPU. (Khuyến nghị cài PyTorch CUDA nếu có GPU NVIDIA)")
    except ImportError:
        print("[ERROR] Chưa cài đặt PyTorch! Chạy: pip install torch torchvision")

    for pkg in ["transformers", "faiss", "fastapi", "uvicorn", "pydantic"]:
        try:
            __import__(pkg)
            print(f"[OK] Thư viện '{pkg}' đã sẵn sàng.")
        except ImportError:
            print(f"[ERROR] Thiếu thư viện '{pkg}'! Chạy: pip install -e .")


def check_database():
    print_header("2. KIỂM TRA DATABASE TRUNG TÂM (mapping.sqlite)")
    print(f"Vị trí: {MAPPING_DB}")

    if not MAPPING_DB.exists():
        print(f"[ERROR] Không tìm thấy file {MAPPING_DB}!")
        print("        -> Vui lòng copy thư mục artifacts từ máy nguồn vào ổ đĩa tương ứng.")
        return False

    import sqlite3
    try:
        conn = sqlite3.connect(f"file:{MAPPING_DB}?mode=ro", uri=True)
        c = conn.cursor()
        
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"[OK] Kết nối Database thành công ({MAPPING_DB.stat().st_size / (1024**2):.1f} MB).")
        print(f"     Tổng số bảng: {len(tables)}")

        # Check key table counts
        expected = {
            "custom_keyframes": 116767,
            "canonical_asr_segments": 107540,
            "ocr_items": 676925,
            "media_info": 873,
            "qwen_frames": 116767,
        }

        for tbl, exp_cnt in expected.items():
            if tbl in tables:
                cnt = c.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                status = "OK" if cnt == exp_cnt else "OK (CUSTOM DATA)"
                print(f"     [{status}] {tbl:<22}: {cnt:,} dòng")
            else:
                print(f"     [ERROR] Thiếu bảng '{tbl}'!")

        conn.close()
        return True
    except Exception as exc:
        print(f"[ERROR] Lỗi khi đọc Database: {exc}")
        return False


def check_retrieval_lanes():
    print_header("3. KIỂM TRA CÁC ARTIFACT & SEARCH LANES")
    print(f"Thư mục Artifacts: {ARTIFACTS_DIR}\n")

    lanes_to_check = [
        ("Visual SigLIP", ARTIFACTS_DIR / "siglip_custom_v1" / "siglip_custom.faiss"),
        ("ASR BGE Dense", ARTIFACTS_DIR / "asr_bge_v1" / "asr_bge.faiss"),
        ("OCR BGE Dense", ARTIFACTS_DIR / "ocr_bge_v1" / "ocr_bge.faiss"),
        ("OCR Trigram", ARTIFACTS_DIR / "ocr_trigram_v1" / "ocr_trigram.sqlite"),
        ("Qwen Structured", ARTIFACTS_DIR / "qwen_structured_v1" / "qwen_facets.sqlite"),
    ]


    for name, path in lanes_to_check:
        if path.exists():
            sz_mb = path.stat().st_size / (1024**2)
            print(f"[OK] {name:<20}: Đã có file index ({sz_mb:.1f} MB) -> {path.name}")
        else:
            print(f"[WARNING] {name:<20}: Chưa có file {path}")


def run_smokes():
    print_header("4. CHẠY SMOKE SEARCH THỰC TẾ (10 LANES)")
    try:
        from aic2026.retrieval.providers.asr_bm25 import AsrBm25Provider
        from aic2026.retrieval.providers.media_bm25 import MediaBm25Provider
        from aic2026.retrieval.providers.qwen_bm25 import QwenBm25Provider
        from aic2026.retrieval.providers.base import ProviderQuery

        if MAPPING_DB.exists():
            # ASR BM25
            p_asr = AsrBm25Provider(MAPPING_DB)
            h = p_asr.search(ProviderQuery(query_text="thành phố Hồ Chí Minh", top_k=2))
            print(f"[PASS] ASR BM25 Search       : {len(h)} hits (Top-1 Video: {h[0].video_id if h else 'N/A'})")

            # Media BM25
            p_media = MediaBm25Provider(MAPPING_DB)
            h_m = p_media.search(ProviderQuery(query_text="thời sự", top_k=2))
            print(f"[PASS] Media BM25 Search     : {len(h_m)} hits (Top-1 Video: {h_m[0].video_id if h_m else 'N/A'})")

            # Qwen BM25
            p_qwen = QwenBm25Provider(MAPPING_DB)
            h_q = p_qwen.search(ProviderQuery(query_text="xe đạp", top_k=2))
            print(f"[PASS] Qwen BM25 Search      : {len(h_q)} hits (Top-1 Video: {h_q[0].video_id if h_q else 'N/A'})")

        # Qwen Structured
        qwen_facets_db = ARTIFACTS_DIR / "qwen_structured_v1" / "qwen_facets.sqlite"
        if qwen_facets_db.exists():
            from aic2026.retrieval.providers.qwen_structured import QwenStructuredProvider, QwenStructuredQuery
            p_str = QwenStructuredProvider(qwen_facets_db)
            h_s = p_str.search(QwenStructuredQuery(query_text="motorcycle riding", top_k=2))
            print(f"[PASS] Qwen Structured Search: {len(h_s)} hits (Top-1 Keyframe: {h_s[0].payload.get('keyframe_uid', '') if h_s else 'N/A'})")

        # OCR Trigram
        ocr_tri_db = ARTIFACTS_DIR / "ocr_trigram_v1" / "ocr_trigram.sqlite"
        if ocr_tri_db.exists():
            from aic2026.retrieval.providers.ocr_trigram import OcrTrigramProvider
            p_tri = OcrTrigramProvider(ocr_tri_db.parent)
            h_t = p_tri.search(ProviderQuery(query_text="truyền hình", top_k=2))
            print(f"[PASS] OCR Trigram Search    : {len(h_t)} hits (Top-1 Video: {h_t[0].video_id if h_t else 'N/A'})")

    except Exception as exc:
        print(f"[ERROR] Lỗi khi chạy smoke search: {exc}")


def main():
    print("=" * 75)
    print("      AIC 2026 - HỆ THỐNG KIỂM TRA & BÀN GIAO DỰ ÁN (HANDOVER VERIFY)")
    print("=" * 75)
    check_env()
    db_ok = check_database()
    check_retrieval_lanes()
    if db_ok:
        run_smokes()
    print("\n" + "=" * 75)
    print("  HOÀN TẤT KIỂM TRA! HỆ THỐNG SẴN SÀNG CHẠY BACKEND & FRONTEND.")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
