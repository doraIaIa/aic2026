import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

def run_modalities(data_root: Path, audit_dir: Path) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting Modalities and Manifest Generation...")
    
    # Load videos and keyframes to cross-reference
    videos = {}
    if (audit_dir / "videos.jsonl").exists():
        with open(audit_dir / "videos.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                v = json.loads(line)
                videos[v["video_id"]] = v
                
    keyframes = {}
    if (audit_dir / "keyframes.jsonl").exists():
        with open(audit_dir / "keyframes.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                k = json.loads(line)
                keyframes[k["video_id"]] = k
                
    objects_report = {
        "total_videos_with_objects": 0,
        "total_videos_missing_objects": 0,
        "total_object_files": 0,
        "orphan_object_files": 0,
        "sample_schema": None
    }
    
    metadata_report = {
        "videos_with_metadata": 0,
        "videos_without_metadata": 0,
        "orphan_metadata": 0,
        "sample_schema": None
    }
    
    manifest_items = []
    
    # Simple recursive scan for .json files
    json_files = []
    def _scan_json(d: Path):
        try:
            with os.scandir(d) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".json"):
                        json_files.append(Path(entry.path))
                    elif entry.is_dir(follow_symlinks=False):
                        _scan_json(Path(entry.path))
        except OSError:
            pass
            
    _scan_json(data_root)
    
    object_files = {}
    metadata_files = {}
    
    for jp in json_files:
        rel_path = jp.relative_to(data_root).as_posix()
        parts = Path(rel_path).parts
        
        # Heuristics to separate metadata and objects based on naming or folder
        # Typical AIC folder struct: Objects/L01_V001.json or Metadata/L01_V001.json
        if len(parts) > 0:
            if "object" in parts[0].lower():
                video_id = jp.stem
                object_files[video_id] = rel_path
                objects_report["total_object_files"] += 1
                if not objects_report["sample_schema"]:
                    try:
                        with open(jp, "r", encoding="utf-8") as f:
                            sample = json.load(f)
                            if isinstance(sample, list) and len(sample) > 0:
                                objects_report["sample_schema"] = list(sample[0].keys()) if isinstance(sample[0], dict) else type(sample[0]).__name__
                            elif isinstance(sample, dict):
                                objects_report["sample_schema"] = list(sample.keys())
                    except Exception:
                        pass
            elif "metadata" in parts[0].lower():
                video_id = jp.stem
                metadata_files[video_id] = rel_path
                if not metadata_report["sample_schema"]:
                    try:
                        with open(jp, "r", encoding="utf-8") as f:
                            sample = json.load(f)
                            if isinstance(sample, dict):
                                metadata_report["sample_schema"] = list(sample.keys())
                    except Exception:
                        pass
                        
    # Evaluate completeness
    for vid in videos:
        has_obj = vid in object_files
        has_meta = vid in metadata_files
        
        if has_obj:
            objects_report["total_videos_with_objects"] += 1
        else:
            objects_report["total_videos_missing_objects"] += 1
            
        if has_meta:
            metadata_report["videos_with_metadata"] += 1
        else:
            metadata_report["videos_without_metadata"] += 1
            
        manifest_items.append({
            "schema_version": 1,
            "video_id": vid,
            "video_relpath": videos[vid]["relative_path"],
            "metadata_relpath": metadata_files.get(vid),
            "keyframe_group_relpath": keyframes.get(vid, {}).get("directory"),
            "keyframe_count": keyframes.get(vid, {}).get("count", 0),
            "object_status": "present" if has_obj else "missing",
        })
        
    for vid in object_files:
        if vid not in videos:
            objects_report["orphan_object_files"] += 1
            
    for vid in metadata_files:
        if vid not in videos:
            metadata_report["orphan_metadata"] += 1
            
    with open(audit_dir / "objects.json", "w", encoding="utf-8") as f:
        json.dump(objects_report, f, indent=2)
        
    with open(audit_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata_report, f, indent=2)
        
    # Generate canonical manifest
    manifests_dir = data_root.parent / "AIC_WORK" / "manifests" if "AIC_WORK" not in str(audit_dir) else audit_dir.parent / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    
    with open(manifests_dir / "corpus_manifest.jsonl", "w", encoding="utf-8") as f:
        for item in manifest_items:
            f.write(json.dumps(item) + "\n")
            
    logger.info("Modalities and Manifest Generation complete.")
