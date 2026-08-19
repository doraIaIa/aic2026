import hashlib
import json
from pathlib import Path

out_dir = Path(r"F:\AIC_WORK\artifacts\canonical_btc_v1")
obj_jsonl = out_dir / "btc_objects.jsonl"

print("Computing canonical object checksum from btc_objects.jsonl...")
hasher = hashlib.sha256()
count = 0
with open(obj_jsonl, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            count += 1
            det = json.loads(line)
            bbox_str = ",".join(f"{x:.6f}" for x in det["bbox"])
            line_hash = (
                f"{det['detection_uid']}|{det['keyframe_uid']}|{det['video_id']}|{det['local_keyframe_no']}|"
                f"{det['frame_idx']}|{det['local_detection_index']}|{det['class_name']}|"
                f"{det.get('class_entity') or ''}|{det.get('class_label') or ''}|{det['confidence']:.6f}|{bbox_str}\n"
            )
            hasher.update(line_hash.encode("utf-8"))

checksum = hasher.hexdigest()
print(f"Total detections: {count:,}")
print(f"Object Canonical Checksum: {checksum}")

# Update btc_object_space.json
obj_space_p = out_dir / "btc_object_space.json"
with open(obj_space_p, "r", encoding="utf-8") as f:
    obj_space = json.load(f)
obj_space["canonical_checksum"] = checksum
with open(obj_space_p, "w", encoding="utf-8") as f:
    json.dump(obj_space, f, indent=2)

# Update source_registry.jsonl
src_p = out_dir / "source_registry.jsonl"
lines = []
with open(src_p, "r", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r["source_id"] == "btc_objects_raw_v1":
            r["checksum"] = checksum
        lines.append(r)
with open(src_p, "w", encoding="utf-8") as f:
    for r in lines:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

# Update build_manifest_m1d.json
manifest_p = out_dir / "build_manifest_m1d.json"
with open(manifest_p, "r", encoding="utf-8") as f:
    manifest = json.load(f)
manifest["validation"]["object_canonical_checksum"] = checksum
with open(manifest_p, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)

print("Successfully updated btc_object_space.json, source_registry.jsonl, and build_manifest_m1d.json")
