import json
import logging
import math
import os
import random
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Windows specific file attributes for cloud files
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000

def _get_cloud_status(st: os.stat_result) -> str:
    if not hasattr(st, "st_file_attributes"):
        return "unknown"
    attrs = st.st_file_attributes
    if attrs & FILE_ATTRIBUTE_OFFLINE:
        return "offline"
    if attrs & FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS:
        return "on_demand"
    return "hydrated"

def run_discovery(data_root: Path, audit_dir: Path) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting Filesystem Discovery...")
    
    tree: list[dict[str, Any]] = []
    extensions: dict[str, int] = defaultdict(int)
    storage_report: list[dict[str, Any]] = []
    
    videos: list[Path] = []
    keyframe_dirs: list[Path] = []
    
    def _scan(directory: Path, rel_parent: str):
        try:
            with os.scandir(directory) as it:
                file_count = 0
                dir_count = 0
                total_bytes = 0
                sample_paths = []
                inaccessible = 0
                
                for entry in it:
                    rel_path = f"{rel_parent}/{entry.name}" if rel_parent else entry.name
                    
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if entry.is_file(follow_symlinks=False):
                            file_count += 1
                            total_bytes += st.st_size
                            ext = Path(entry.name).suffix.lower()
                            extensions[ext] += 1
                            if len(sample_paths) < 10:
                                sample_paths.append(rel_path)
                            
                            # Collect video and keyframe paths
                            if ext in {".mp4", ".mkv", ".avi", ".mov", ".webm"}:
                                videos.append(Path(entry.path))
                            elif ext in {".jpg", ".jpeg", ".png"}:
                                # Check if it's in a keyframe directory
                                # Typical pattern: Keyframes/L01_V001/000123.jpg
                                parts = Path(rel_path).parts
                                if len(parts) >= 3 and (parts[0].lower() == "keyframes" or parts[0].lower() == "frames"):
                                    parent_dir = Path(entry.path).parent
                                    if not keyframe_dirs or keyframe_dirs[-1] != parent_dir:
                                        keyframe_dirs.append(parent_dir)

                        elif entry.is_dir(follow_symlinks=False):
                            dir_count += 1
                            _scan(Path(entry.path), rel_path)
                    except OSError:
                        inaccessible += 1
                
                if file_count > 0 or dir_count > 0:
                    report_entry = {
                        "relative_path": rel_parent or ".",
                        "file_count": file_count,
                        "dir_count": dir_count,
                        "logical_total_bytes": total_bytes,
                        "example_paths": sample_paths,
                        "inaccessible_entries": inaccessible,
                    }
                    storage_report.append(report_entry)
        except OSError as e:
            logger.error(f"Error scanning {directory}: {e}")
            storage_report.append({
                "relative_path": rel_parent or ".",
                "error": str(e)
            })

    _scan(data_root, "")
    
    with open(audit_dir / "dataset_tree.json", "w", encoding="utf-8") as f:
        json.dump(storage_report, f, indent=2)
    with open(audit_dir / "extensions.json", "w", encoding="utf-8") as f:
        json.dump(dict(extensions), f, indent=2)
    with open(audit_dir / "storage_report.json", "w", encoding="utf-8") as f:
        # Same as tree for now, can be aggregated
        json.dump(storage_report, f, indent=2)
        
    logger.info(f"Discovered {len(videos)} videos and {len(keyframe_dirs)} keyframe directories.")
    
    # Step B: Video Inventory
    logger.info("Starting Video Inventory...")
    rng = random.Random(42)
    sample_videos = rng.sample(videos, min(20, len(videos)))
    
    video_inventory = []
    for vp in videos:
        try:
            st = vp.stat()
            rel_path = vp.relative_to(data_root).as_posix()
            video_id = vp.stem
            
            info = {
                "video_id": video_id,
                "relative_path": rel_path,
                "extension": vp.suffix.lower(),
                "logical_size": st.st_size,
                "accessible": True,
                "cloud_status": _get_cloud_status(st)
            }
            
            if vp in sample_videos:
                # Run ffprobe
                try:
                    cmd = [
                        "ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=r_frame_rate,avg_frame_rate,duration,width,height,codec_name,nb_frames,time_base",
                        "-of", "json", str(vp)
                    ]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if res.returncode == 0:
                        ffprobe_data = json.loads(res.stdout)
                        if ffprobe_data.get("streams"):
                            s = ffprobe_data["streams"][0]
                            info.update({
                                "duration": s.get("duration"),
                                "avg_frame_rate": s.get("avg_frame_rate"),
                                "r_frame_rate": s.get("r_frame_rate"),
                                "width": s.get("width"),
                                "height": s.get("height"),
                                "codec": s.get("codec_name"),
                                "reported_frame_count": s.get("nb_frames"),
                                "time_base": s.get("time_base")
                            })
                except Exception as e:
                    info["ffprobe_error"] = str(e)
                    
            video_inventory.append(info)
        except OSError:
            video_inventory.append({
                "video_id": vp.stem,
                "relative_path": vp.relative_to(data_root).as_posix(),
                "accessible": False
            })
            
    with open(audit_dir / "videos.jsonl", "w", encoding="utf-8") as f:
        for item in video_inventory:
            f.write(json.dumps(item) + "\n")
            
    # Step C: Keyframe Inventory
    logger.info("Starting Keyframe Inventory...")
    keyframe_inventory = []
    for kp_dir in keyframe_dirs:
        try:
            # We don't read the file contents, just the filenames
            frames = sorted([entry.name for entry in os.scandir(kp_dir) if entry.is_file() and entry.name.lower().endswith(('.jpg', '.jpeg', '.png'))])
            if not frames:
                continue
                
            video_id = kp_dir.name
            first_filename = frames[0]
            last_filename = frames[-1]
            count = len(frames)
            
            # Check for gaps and duplicates if filenames are numeric
            gaps = 0
            duplicates = 0
            try:
                nums = [int(Path(f).stem) for f in frames]
                for i in range(1, len(nums)):
                    if nums[i] == nums[i-1]:
                        duplicates += 1
                    elif nums[i] > nums[i-1] + 1:
                        gaps += (nums[i] - nums[i-1] - 1)
            except ValueError:
                # Not purely numeric
                pass
                
            keyframe_inventory.append({
                "video_id": video_id,
                "directory": kp_dir.relative_to(data_root).as_posix(),
                "count": count,
                "first_filename": first_filename,
                "last_filename": last_filename,
                "gaps": gaps,
                "duplicates": duplicates
            })
        except OSError as e:
            logger.error(f"Error reading keyframe dir {kp_dir}: {e}")
            
    with open(audit_dir / "keyframes.jsonl", "w", encoding="utf-8") as f:
        for item in keyframe_inventory:
            f.write(json.dumps(item) + "\n")
