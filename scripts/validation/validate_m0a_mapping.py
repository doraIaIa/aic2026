import json
import logging
import os
import csv
import sys
from pathlib import Path
import argparse
import numpy as np
try:
    import tomllib
except ImportError:
    import tomli as tomllib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/local.toml")
    args = parser.parse_args()
    
    with open(args.config, "rb") as f:
        config = tomllib.load(f)
        
    data_root = Path(config["paths"]["data_root"])
    work_root = Path(config["paths"]["work_root"])
    
    audit_dir = work_root / "audit"
    val_dir = work_root / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    
    out_jsonl = val_dir / "m0a_mapping_fix_validation.jsonl"
    out_report = val_dir / "M0A_MAPPING_FIX_REPORT.md"
    
    # 1. Load video list
    videos = []
    with open(audit_dir / "videos.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            v = json.loads(line)
            if v.get("accessible"):
                videos.append(v["video_id"])
                
    # Lexicographical sort
    videos.sort() 
    
    # Filter to only videos that have a map-keyframes CSV
    valid_videos = []
    for vid in videos:
        p1 = data_root / "data_extracted" / "map-keyframes" / f"{vid}.csv"
        p2 = data_root / "map-keyframes" / f"{vid}.csv"
        p3 = data_root / "data_extracted" / "Metadata" / f"{vid}.csv"
        p4 = data_root / "Metadata" / f"{vid}.csv"
        if p1.exists() or p2.exists() or p3.exists() or p4.exists():
            valid_videos.append(vid)
            
    videos = valid_videos
    
    # Select 20 canonical videos
    # 5 early, 5 middle, 5 late, 5 known (e.g. L26_V434, L24_V025, L21_V027, L29_V007, L26_V066 from previous run)
    known = ["L26_V434", "L24_V025", "L21_V027", "L29_V007", "L26_V066"]
    
    # Filter known if they exist
    known_available = [v for v in known if v in videos]
    
    remaining = [v for v in videos if v not in known_available]
    
    early = remaining[:5]
    middle_idx = len(remaining) // 2
    middle = remaining[max(0, middle_idx-2) : middle_idx+3]
    late = remaining[-5:]
    
    selected_videos = early + middle + late + known_available
    
    # Deduplicate and limit to exactly 20
    selected_videos = list(dict.fromkeys(selected_videos))[:20]
    
    # Ensure exactly 20
    if len(selected_videos) < 20:
        for v in videos:
            if v not in selected_videos:
                selected_videos.append(v)
            if len(selected_videos) == 20:
                break
                
    logger.info(f"Selected videos: {selected_videos}")
    
    results = []
    pass_count = 0
    fail_count = 0
    anomalies = 0
    rows_tested = 0
    
    with open(out_jsonl, "w", encoding="utf-8") as out_f:
        for vid in selected_videos:
            vid_result = {
                "video_id": vid,
                "status": "PASS",
                "counts": {},
                "checks": [],
                "errors": []
            }
            
            # Paths
            csv_paths = [
                data_root / "data_extracted" / "map-keyframes" / f"{vid}.csv",
                data_root / "map-keyframes" / f"{vid}.csv",
                data_root / "data_extracted" / "Metadata" / f"{vid}.csv",
                data_root / "Metadata" / f"{vid}.csv"
            ]
            csv_path = None
            for p in csv_paths:
                if p.exists():
                    csv_path = p
                    break
            
            kf_dir1 = data_root / "data_extracted" / "keyframes" / vid
            kf_dir2 = data_root / "output" / "keyframes" / vid
            kf_dir = kf_dir1 if kf_dir1.exists() else kf_dir2
            
            clip_path = data_root / "data_extracted" / "clip-features-32" / f"{vid}.npy"
            
            # Load CSV
            csv_rows = []
            if csv_path and csv_path.exists():
                with open(csv_path, "r", encoding="utf-8") as cf:
                    reader = csv.DictReader(cf)
                    csv_rows = list(reader)
            else:
                vid_result["errors"].append(f"CSV not found for {vid}")
                
            # Load Keyframes (sort by name)
            keyframes = []
            if kf_dir.exists():
                keyframes = sorted([p.name for p in kf_dir.glob("*.jpg")])
            else:
                vid_result["errors"].append(f"Keyframes dir not found: {kf_dir1}")
                
            # Load CLIP shape
            clip_rows = 0
            if clip_path.exists():
                try:
                    arr = np.load(str(clip_path), mmap_mode='r')
                    clip_rows = arr.shape[0] if arr.ndim > 0 else 0
                except Exception as e:
                    vid_result["errors"].append(f"Error loading CLIP {clip_path}: {e}")
            else:
                vid_result["errors"].append(f"CLIP not found: {clip_path}")
                
            vid_result["counts"] = {
                "csv_rows": len(csv_rows),
                "keyframe_count": len(keyframes),
                "clip_rows": clip_rows
            }
            
            if not (len(csv_rows) == len(keyframes) == clip_rows):
                vid_result["errors"].append("Count mismatch")
                
            # Perform first, middle, last checks
            if len(csv_rows) > 0 and len(keyframes) > 0:
                indices_to_test = [0, len(csv_rows)//2, len(csv_rows)-1]
                # Deduplicate if small
                indices_to_test = sorted(list(set(indices_to_test)))
                
                for idx in indices_to_test:
                    row = csv_rows[idx]
                    
                    try:
                        n_val = int(row.get("n", 0))
                        frame_idx = int(row.get("frame_idx", -1))
                        
                        # Data contract: n is 1-based ordinal
                        expected_ordinal = n_val
                        
                        # Actual keyframe index (0-based list)
                        actual_kf_index = expected_ordinal - 1
                        actual_kf_filename = keyframes[actual_kf_index] if 0 <= actual_kf_index < len(keyframes) else None
                        
                        # CLIP row is 0-based
                        clip_row = expected_ordinal - 1
                        
                        chk = {
                            "sample_index": idx,
                            "csv_n": n_val,
                            "csv_frame_idx": frame_idx,
                            "jpg_ordinal": expected_ordinal,
                            "actual_kf_filename": actual_kf_filename,
                            "clip_row_index": clip_row,
                            "valid": False
                        }
                        
                        if actual_kf_filename and 0 <= clip_row < clip_rows:
                            chk["valid"] = True
                        else:
                            chk["valid"] = False
                            vid_result["errors"].append(f"Row {idx} mapping failed")
                            
                        vid_result["checks"].append(chk)
                        rows_tested += 1
                    except Exception as e:
                        vid_result["errors"].append(f"Exception at row {idx}: {e}")
                        
            if len(vid_result["errors"]) > 0:
                vid_result["status"] = "FAIL"
                fail_count += 1
            else:
                vid_result["status"] = "PASS"
                pass_count += 1
                
            results.append(vid_result)
            out_f.write(json.dumps(vid_result) + "\n")
            
    # Write Report
    commit_sha = os.popen("git rev-parse HEAD").read().strip() if os.path.exists(".git") else "UNKNOWN"
    env_info = "Windows PowerShell / " + os.popen("python --version").read().strip()
    
    for r in results:
        if r["status"] == "FAIL":
            anomalies += len(r["errors"])
            
    report_content = f"""# M0A MAPPING FIX VALIDATION REPORT

COMMIT TESTED: {commit_sha}
ENVIRONMENT: {env_info}

## VERDICT
{"PASS" if fail_count == 0 else "FAIL"}

## SUMMARY
VIDEOS TESTED: {len(selected_videos)}
ROWS TESTED: {rows_tested}
PASS COUNT: {pass_count}
FAIL COUNT: {fail_count}
ANOMALIES: {anomalies}

## DETAILS
"""
    for r in results:
        report_content += f"\n### Video {r['video_id']} - {r['status']}\n"
        report_content += f"- Counts: CSV={r['counts']['csv_rows']}, JPG={r['counts']['keyframe_count']}, CLIP={r['counts']['clip_rows']}\n"
        if r['errors']:
            report_content += "- Errors:\n"
            for e in r['errors']:
                report_content += f"  - {e}\n"
        if r['checks']:
            report_content += "- Sample Checks:\n"
            for c in r['checks']:
                report_content += f"  - [idx={c['sample_index']}] csv.n={c['csv_n']} -> jpg_ord={c['jpg_ordinal']} ({c['actual_kf_filename']}), clip_row={c['clip_row_index']} | Valid: {c['valid']}\n"
                
    with open(out_report, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    logger.info(f"Report generated at {out_report}")

if __name__ == "__main__":
    main()
