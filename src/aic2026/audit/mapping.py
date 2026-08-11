import json
import csv
import logging
import random
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def clip_row_to_csv_n(clip_row: int) -> int:
    """Map 0-based CLIP row index to 1-based CSV/keyframe ordinal."""
    if clip_row < 0:
        raise ValueError("clip_row must be non-negative")
    return clip_row + 1


def _keyframe_name_from_ordinal(ordinal: int, keyframe_info: dict | None = None) -> str:
    if ordinal < 1:
        raise ValueError("keyframe ordinal must be 1-based")

    width = 3
    suffix = ".jpg"
    if keyframe_info:
        first_filename = keyframe_info.get("first_filename")
        if first_filename:
            first_path = Path(first_filename)
            suffix = first_path.suffix or suffix
            if first_path.stem.isdigit():
                width = len(first_path.stem)

    return f"{ordinal:0{width}d}{suffix}"


def _resolve_mapping_fields(sample_row: dict) -> tuple[str | None, str | None, str | None]:
    n_field = None
    frame_idx_field = None
    keyframe_relpath_field = None

    for key in sample_row.keys():
        key_lower = key.lower()
        if key_lower == "n":
            n_field = key
        elif key_lower == "frame_idx":
            frame_idx_field = key
        elif "frame" in key_lower and "idx" in key_lower:
            frame_idx_field = key

        if "path" in key_lower or "name" in key_lower or "file" in key_lower:
            keyframe_relpath_field = key

    return n_field, frame_idx_field, keyframe_relpath_field


def resolve_keyframe_name(
    row: dict,
    keyframe_info: dict | None = None,
    keyframe_relpath_field: str | None = None,
    n_field: str | None = "n",
) -> str:
    if keyframe_relpath_field:
        return str(row[keyframe_relpath_field])

    if not n_field or n_field not in row:
        raise ValueError("Cannot resolve keyframe filename without CSV.n or explicit keyframe path")

    return _keyframe_name_from_ordinal(int(row[n_field]), keyframe_info)


def _mse(img1: Image.Image, img2: Image.Image) -> float:
    i1 = np.asarray(img1.resize((320, 240)).convert("RGB")).astype(np.float32)
    i2 = np.asarray(img2.resize((320, 240)).convert("RGB")).astype(np.float32)
    return float(np.mean((i1 - i2) ** 2))

def run_frame_mapping(data_root: Path, audit_dir: Path) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Starting Frame Mapping Forensics...")
    
    videos = {}
    if (audit_dir / "videos.jsonl").exists():
        with open(audit_dir / "videos.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                v = json.loads(line)
                if v.get("accessible"):
                    videos[v["video_id"]] = v
                    
    if not videos:
        logger.error("No accessible videos found in videos.jsonl. Run audit-dataset first.")
        return
        

    # Common locations: map-keyframes/, Metadata/
    mapping_files = {}
    
    # Preload keyframe dirs from keyframes.jsonl for fast lookup
    keyframe_dirs = {}
    keyframe_infos = {}
    if (audit_dir / "keyframes.jsonl").exists():
        with open(audit_dir / "keyframes.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                k = json.loads(line)
                keyframe_dirs[k["video_id"]] = k["directory"]
                keyframe_infos[k["video_id"]] = k

    for vid in videos:
        # Check standard mapping paths
        paths_to_check = [
            data_root / "data_extracted" / "map-keyframes" / f"{vid}.csv",
            data_root / "data_extracted" / "map-keyframes" / f"{vid}.json",
            data_root / "data_extracted" / "Metadata" / f"{vid}.json",
            data_root / "data_extracted" / "Metadata" / f"{vid}.csv",
            data_root / "map-keyframes" / f"{vid}.csv",
            data_root / "map-keyframes" / f"{vid}.json",
            data_root / "Metadata" / f"{vid}.json",
            data_root / "Metadata" / f"{vid}.csv"
        ]
        found = [p for p in paths_to_check if p.exists()]
        if found:
            mapping_files[vid] = found
        
    rng = random.Random(42)
    # Pick 5 videos that have a mapping file (fast audit)
    candidate_videos = [vid for vid in videos if vid in mapping_files]
    sample_videos = rng.sample(candidate_videos, min(5, len(candidate_videos)))
    
    results = []
    
    for vid in sample_videos:
        video_path = data_root / videos[vid]["relative_path"]
        mappings_for_video = mapping_files[vid]
        
        # Try to parse the mapping file
        mapping_data = []
        mapping_format = "unknown"
        for mp in mappings_for_video:
            try:
                if mp.suffix.lower() == ".csv":
                    with open(mp, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            mapping_data.append(row)
                    mapping_format = "csv"
                    break
                elif mp.suffix.lower() == ".json":
                    with open(mp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            mapping_data = data
                            mapping_format = "json_list"
                            break
                        elif isinstance(data, dict):
                            # Try to extract a list of frames from dict
                            for k, v in data.items():
                                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                                    mapping_data = v
                                    mapping_format = f"json_dict_key_{k}"
                                    break
                            if mapping_data:
                                break
            except Exception:
                continue
                
        if not mapping_data:
            results.append({"video_id": vid, "error": "No valid mapping data found"})
            continue
            
        # Discover fields. CSV.n is the 1-based keyframe ordinal; CSV.frame_idx is
        # the original-video frame index. They are intentionally separate.
        sample_row = mapping_data[0]
        n_field, frame_idx_field, keyframe_relpath_field = _resolve_mapping_fields(sample_row)
                
        if not frame_idx_field:
            results.append({"video_id": vid, "error": "Could not identify frame_idx field in mapping", "sample_row": sample_row})
            continue
            
        # Pick 1 sample. Prefer CSV.n order because keyframe filenames are
        # ordinal-based and must not be inferred from frame_idx.
        sort_field = n_field or frame_idx_field
        mapping_data = sorted(mapping_data, key=lambda x: int(x.get(sort_field, 0)) if str(x.get(sort_field, 0)).isdigit() else 0)
        
        samples_to_test = [mapping_data[0]] if mapping_data else []
            
        for row in samples_to_test:
            try:
                frame_idx = int(row[frame_idx_field])
            except ValueError:
                continue
                
            try:
                kf_name = resolve_keyframe_name(row, keyframe_infos.get(vid), keyframe_relpath_field, n_field)
            except ValueError as e:
                results.append({"video_id": vid, "btc_frame_idx": frame_idx, "error": str(e)})
                continue
                
            kf_paths = []
            if vid in keyframe_dirs:
                expected_path = data_root / keyframe_dirs[vid] / kf_name
                if expected_path.exists():
                    kf_paths.append(expected_path)
                
            if not kf_paths:
                results.append({"video_id": vid, "btc_frame_idx": frame_idx, "error": f"Keyframe image not found for {kf_name}"})
                continue
                
            kf_path = kf_paths[0]
            try:
                kf_img = Image.open(kf_path)
                kf_img.load()
            except Exception as e:
                results.append({"video_id": vid, "btc_frame_idx": frame_idx, "error": f"Failed to load keyframe image: {e}"})
                continue
                
            # Decode N-2 to N+2
            # Using ffmpeg select filter
            candidates = {}
            with tempfile.TemporaryDirectory() as tmpdir:
                for offset in (-2, -1, 0, 1, 2):
                    target_frame = max(0, frame_idx + offset)
                    out_path = Path(tmpdir) / f"frame_{offset}.jpg"
                    cmd = [
                        "ffmpeg", "-y", "-v", "error", "-i", str(video_path),
                        "-vf", f"select='eq(n,{target_frame})'", "-vsync", "vfr",
                        "-vframes", "1", str(out_path)
                    ]
                    res = subprocess.run(cmd, capture_output=True)
                    if out_path.exists():
                        try:
                            candidates[offset] = Image.open(out_path).copy()
                        except Exception:
                            pass
                            
            if not candidates:
                results.append({"video_id": vid, "btc_frame_idx": frame_idx, "error": "FFmpeg failed to extract any candidate frames"})
                continue
                
            # Compare
            best_offset = None
            best_mse = float('inf')
            
            for offset, cand_img in candidates.items():
                err = _mse(kf_img, cand_img)
                if err < best_mse:
                    best_mse = err
                    best_offset = offset
                    
            results.append({
                "video_id": vid,
                "keyframe_relpath": kf_path.relative_to(data_root).as_posix(),
                "csv_n": int(row[n_field]) if n_field else None,
                "btc_frame_idx": frame_idx,
                "best_decoded_frame": frame_idx + best_offset if best_offset is not None else None,
                "offset": best_offset,
                "match_mse": best_mse,
                "notes": f"Format: {mapping_format}, NField: {n_field}, FrameField: {frame_idx_field}"
            })

    with open(audit_dir / "frame_mapping_verification.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
            
    logger.info("Frame Mapping Forensics complete.")
