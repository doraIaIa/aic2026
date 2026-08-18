import hashlib
import json
import time
from pathlib import Path
from aic2026.core.data_registry import DATA_REGISTRY
from aic2026.data_hub import CustomKeyframeRegistry, VideoRegistry
from aic2026.data_hub.asr_ocr_builder import normalize_canonical_text
from aic2026.data_hub.asr_ocr_models import (
    OcrBgeRowmapRecord,
    OcrItemRecord,
)

t0 = time.time()
print("=== COMPREHENSIVE RAW OCR UNIVERSE SCAN & BGE RECONCILIATION ===")

cache_dir = Path(r"F:\AIC_WORK\raw_ocr_cache")
video_dir = Path(r"F:\AIC_WORK\artifacts\canonical_universe_v1")
custom_dir = Path(r"F:\AIC_WORK\artifacts\canonical_custom_qwen_v1")
dense_dir = DATA_REGISTRY.btc_drive_root / "ocr_single_text_retrieval"
out_dir = Path(r"F:\AIC_WORK\artifacts\canonical_asr_ocr_v1")

v_reg = VideoRegistry.load_from_directory(video_dir, validate=False)
c_reg = CustomKeyframeRegistry.load_from_directory(custom_dir, video_registry=v_reg, validate=False)

# Map (video_id, file_stem) -> CustomKeyframeRecord
kf_map = {}
for kf in c_reg.iter_custom_keyframes():
    stem = kf.file_name.rsplit(".", 1)[0]
    kf_map[(kf.video_id, stem)] = kf

print(f"Indexed {len(kf_map)} custom keyframes in {time.time() - t0:.2f}s")

# 1. Load BGE metadata shards and build BGE lookup: (video_id, keyframe_id, text_index) -> (shard_str, row_idx, meta_dict)
t_bge = time.time()
bge_map = {}
bge_total_rows = 0
for shard_idx in range(10):
    shard_str = f"{shard_idx:03d}"
    meta_p = dense_dir / f"metadata_shard_{shard_str}.json"
    with open(meta_p, "r", encoding="utf-8") as f:
        m_rows = json.load(f)
    bge_total_rows += len(m_rows)
    for r_idx, r in enumerate(m_rows):
        key = (r["video_id"], str(r["keyframe_id"]), int(r.get("text_index", 0)))
        bge_map[key] = (shard_str, r_idx, r)

print(f"Loaded {bge_total_rows:,} BGE metadata rows in {time.time() - t_bge:.2f}s")

# 2. Iterate through all custom keyframes deterministically and read raw OCR JSON
raw_metrics = {
    "raw_ocr_json_files": 0,
    "raw_ocr_text_items": 0,
    "keyframes_with_zero_items": 0,
    "keyframes_with_one_or_more_items": 0,
    "items_with_confidence": 0,
    "items_without_confidence": 0,
    "items_confidence_lt_0_5": 0,
    "items_confidence_ge_0_5": 0,
    "empty_text_items": 0,
    "nonempty_text_items": 0,
    "bbox_present": 0,
    "bbox_missing": 0,
    "bbox_structural_failures": 0,
    "covered_videos": set(),
    "unknown_keyframes": 0,
    "unknown_videos": 0,
    "parse_failures": 0,
}

canonical_items = []
bge_mapped_count = 0
bge_ambiguous_count = 0
seen_bge_keys = set()

sorted_kfs = sorted(c_reg.iter_custom_keyframes(), key=lambda k: (k.video_ordinal, k.frame_idx))
print("Scanning all 116,767 raw OCR JSON files and building canonical item universe...", flush=True)

for kf in sorted_kfs:
    vid = kf.video_id
    stem = kf.file_name.rsplit(".", 1)[0]
    jf = cache_dir / vid / f"{stem}.json"
    
    if not jf.exists():
        raw_metrics["parse_failures"] += 1
        continue
        
    try:
        with open(jf, "rb") as f:
            d = json.loads(f.read().decode("utf-8"))
        raw_metrics["raw_ocr_json_files"] += 1
        raw_metrics["covered_videos"].add(vid)
    except Exception:
        raw_metrics["parse_failures"] += 1
        continue
        
    texts = d.get("texts", [])
    if len(texts) == 0:
        raw_metrics["keyframes_with_zero_items"] += 1
    else:
        raw_metrics["keyframes_with_one_or_more_items"] += 1
        
    for t_idx, t in enumerate(texts):
        raw_metrics["raw_ocr_text_items"] += 1
        text_raw = str(t.get("text", ""))
        if not text_raw.strip():
            raw_metrics["empty_text_items"] += 1
        else:
            raw_metrics["nonempty_text_items"] += 1
            
        score = t.get("score")
        if score is None:
            raw_metrics["items_without_confidence"] += 1
            score_float = None
        else:
            raw_metrics["items_with_confidence"] += 1
            score_float = float(score)
            if score_float >= 0.5:
                raw_metrics["items_confidence_ge_0_5"] += 1
            else:
                raw_metrics["items_confidence_lt_0_5"] += 1
                
        bbox_raw = t.get("bbox")
        if bbox_raw is not None:
            raw_metrics["bbox_present"] += 1
            if not isinstance(bbox_raw, list) or len(bbox_raw) != 4:
                raw_metrics["bbox_structural_failures"] += 1
        else:
            raw_metrics["bbox_missing"] += 1
            
        # Reconcile with BGE dense subset
        bge_key = (vid, stem, t_idx)
        bge_match = bge_map.get(bge_key)
        dense_ref = None
        if bge_match is not None:
            shard_str, r_idx, bge_meta = bge_match
            dense_ref = f"bge-m3:{shard_str}:{r_idx}"
            if bge_key in seen_bge_keys:
                bge_ambiguous_count += 1
            seen_bge_keys.add(bge_key)
            bge_mapped_count += 1
            
        ocr_uid = f"OCR:{kf.keyframe_uid}:T{t_idx}"
        text_norm = normalize_canonical_text(text_raw)
        
        item_rec = OcrItemRecord(
            ocr_uid=ocr_uid,
            video_id=vid,
            video_ordinal=kf.video_ordinal,
            ordinal_space_id=kf.ordinal_space_id,
            frame_space="CUSTOM",
            keyframe_uid=kf.keyframe_uid,
            frame_idx=kf.frame_idx,
            timestamp_ms=kf.timestamp_ms,
            raw_pts_time=kf.raw_pts_time,
            local_text_index=t_idx,
            text_raw=text_raw,
            text_norm=text_norm,
            bbox=bbox_raw,
            ocr_confidence=score_float,
            ocr_type="single",
            dense_embedding_ref=dense_ref,
            source_id="ocr_results_ppocrv6_v1",
            schema_version="v1",
        )
        canonical_items.append(item_rec)

print(f"\nScan finished in {time.time() - t0:.2f}s!")
print(f"Total raw OCR files: {raw_metrics['raw_ocr_json_files']:,} / 116,767")
print(f"Total raw OCR items: {len(canonical_items):,}")
print(f"BGE mapped to raw:   {bge_mapped_count:,} / {bge_total_rows:,}")
print(f"BGE unmapped count:  {bge_total_rows - bge_mapped_count:,}")
print(f"BGE ambiguous count: {bge_ambiguous_count:,}")
print(f"Raw without dense:   {len(canonical_items) - bge_mapped_count:,}")
print(f"Items conf < 0.5:    {raw_metrics['items_confidence_lt_0_5']:,}")
print(f"Items conf >= 0.5:   {raw_metrics['items_confidence_ge_0_5']:,}")
print(f"Zero-item keyframes: {raw_metrics['keyframes_with_zero_items']:,}")
print(f"1+-item keyframes:   {raw_metrics['keyframes_with_one_or_more_items']:,}")
print(f"Covered videos:      {len(raw_metrics['covered_videos'])}")
print(f"Parse failures:      {raw_metrics['parse_failures']}")

# Write canonical items to output
print("\nWriting canonical OCR items to ocr_items_canonical.jsonl...", flush=True)
items_out_path = out_dir / "ocr_items_canonical.jsonl"
with open(items_out_path, "w", encoding="utf-8") as f:
    for item in canonical_items:
        f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

# Compute checksum of canonical items
h_items = hashlib.sha256()
for item in canonical_items:
    line = f"{item.ocr_uid}:{item.keyframe_uid}:{item.local_text_index}:{item.text_raw}:{item.ocr_confidence}\n"
    h_items.update(line.encode("utf-8"))
items_checksum = h_items.hexdigest()
print(f"Canonical OCR items SHA256 checksum: {items_checksum}")

# Save full inventory JSON
inventory_data = {
    "raw_ocr_json_files": raw_metrics["raw_ocr_json_files"],
    "raw_ocr_text_items": raw_metrics["raw_ocr_text_items"],
    "keyframes_with_zero_items": raw_metrics["keyframes_with_zero_items"],
    "keyframes_with_one_or_more_items": raw_metrics["keyframes_with_one_or_more_items"],
    "items_with_confidence": raw_metrics["items_with_confidence"],
    "items_without_confidence": raw_metrics["items_without_confidence"],
    "items_confidence_lt_0_5": raw_metrics["items_confidence_lt_0_5"],
    "items_confidence_ge_0_5": raw_metrics["items_confidence_ge_0_5"],
    "empty_text_items": raw_metrics["empty_text_items"],
    "nonempty_text_items": raw_metrics["nonempty_text_items"],
    "bbox_present": raw_metrics["bbox_present"],
    "bbox_missing": raw_metrics["bbox_missing"],
    "bbox_structural_failures": raw_metrics["bbox_structural_failures"],
    "covered_videos": len(raw_metrics["covered_videos"]),
    "unknown_keyframes": 0,
    "unknown_videos": 0,
    "parse_failures": raw_metrics["parse_failures"],
    "bge_vector_rows": bge_total_rows,
    "bge_mapped_to_raw": bge_mapped_count,
    "bge_unmapped_rows": bge_total_rows - bge_mapped_count,
    "bge_ambiguous_rows": bge_ambiguous_count,
    "raw_without_dense_vector": len(canonical_items) - bge_mapped_count,
    "canonical_ocr_items_checksum": items_checksum,
}

inv_path = Path(r"F:\AIC_WORK\artifacts\ocr_raw_inventory_v1\ocr_raw_inventory.json")
with open(inv_path, "w", encoding="utf-8") as f:
    json.dump(inventory_data, f, ensure_ascii=False, indent=2)

print("Inventory saved to:", inv_path)
print(f"Total script elapsed time: {time.time() - t0:.2f}s")
