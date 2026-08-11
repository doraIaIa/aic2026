import json
import logging
import os
import random
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

def run_clip(data_root: Path, audit_dir: Path) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Starting CLIP Feature Forensics...")
    
    keyframes = {}
    if (audit_dir / "keyframes.jsonl").exists():
        with open(audit_dir / "keyframes.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                k = json.loads(line)
                keyframes[k["video_id"]] = k
                
    features = []
    seen_features = set()
    
    def _scan_npy(d: Path):
        try:
            if not d.exists():
                return
            with os.scandir(d) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".npy"):
                        feature_path = Path(entry.path)
                        if feature_path not in seen_features:
                            seen_features.add(feature_path)
                            features.append(feature_path)
                    elif entry.is_dir(follow_symlinks=False):
                        _scan_npy(Path(entry.path))
        except OSError:
            pass
            
    for clip_dir in (
        data_root / "data_extracted" / "clip-features-32",
        data_root / "CLIP",
        data_root / "clip-features-32",
    ):
        _scan_npy(clip_dir)
    
    report = {
        "total_feature_files": len(features),
        "total_videos_with_features": 0,
        "total_rows": 0,
        "mismatches": 0,
        "corrupted_files": 0,
    }
    
    samples = []
    
    rng = random.Random(42)
    sample_features = rng.sample(features, min(10, len(features)))
    
    for npy_path in sample_features:
        video_id = npy_path.stem
        rel_path = npy_path.relative_to(data_root).as_posix()
        
        try:
            st = npy_path.stat()
            # Safely read shape without loading entire array
            arr = np.load(str(npy_path), mmap_mode='r')
            shape = arr.shape
            dtype = str(arr.dtype)
            ndim = arr.ndim
            
            rows = shape[0] if ndim > 0 else 0
            dim = shape[1] if ndim > 1 else 0
            
            report["total_videos_with_features"] += 1
            report["total_rows"] += rows
            
            expected_keyframes = keyframes.get(video_id, {}).get("count")
            
            mismatch = False
            if expected_keyframes is not None and expected_keyframes != rows:
                mismatch = True
                report["mismatches"] += 1
                
            samples.append({
                "video_id": video_id,
                "relative_path": rel_path,
                "dtype": dtype,
                "shape": list(shape),
                "ndim": ndim,
                "rows": rows,
                "dimension": dim,
                "file_size": st.st_size,
                "keyframe_count": expected_keyframes,
                "count_mismatch": mismatch
            })
            
        except Exception as e:
            logger.error(f"Error reading {rel_path}: {e}")
            report["corrupted_files"] += 1
            samples.append({
                "video_id": video_id,
                "relative_path": rel_path,
                "error": str(e)
            })
            
    with open(audit_dir / "clip_features.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    with open(audit_dir / "clip_mapping_samples.jsonl", "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")
            
    logger.info("CLIP Feature Forensics complete.")
