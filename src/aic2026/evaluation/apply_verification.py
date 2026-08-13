import json
import argparse
from pathlib import Path
import tempfile
import os
import shutil

from aic2026.core.config import load_config
from aic2026.core.paths import PathResolver
from aic2026.media.resolver import MediaResolver

def validate_exact_decision(dec, base_label):
    if dec["decision"] not in ["UNREVIEWED", "VERIFIED", "NEEDS_MORE_REVIEW", "NOT_FOUND_IN_CURRENT_POOL", "UNRESOLVED"]:
        raise ValueError(f"Invalid decision status: {dec['decision']}")

    if dec["decision"] == "VERIFIED":
        if base_label["query_type"] in ["KIS", "QA"]:
            if not dec.get("video_id"):
                raise ValueError("VERIFIED KIS/QA requires video_id")
            for field in ["start_frame_id", "representative_frame_id", "end_frame_id"]:
                if not isinstance(dec.get(field), int):
                    raise ValueError(f"VERIFIED KIS/QA requires integer {field}")

            s, r, e = dec["start_frame_id"], dec["representative_frame_id"], dec["end_frame_id"]
            if not (s <= r <= e):
                raise ValueError("Invalid KIS frame range")

        elif base_label["query_type"] == "TRAKE":
            if not dec.get("video_id"):
                raise ValueError("VERIFIED TRAKE requires video_id")
            events = dec.get("events", [])
            if not isinstance(events, list) or len(events) == 0:
                raise ValueError("VERIFIED TRAKE requires at least one event")
            for ev in events:
                if "start_frame_id" not in ev or "end_frame_id" not in ev:
                    raise ValueError("TRAKE events must have start and end frames")

def validate_video_decision(dec, base_label, media_resolver=None):
    if dec["decision"] not in ["UNREVIEWED", "VIDEO_VERIFIED", "NOT_FOUND_IN_CURRENT_POOL", "NEEDS_MORE_REVIEW", "UNRESOLVED"]:
        raise ValueError(f"Invalid video decision status: {dec['decision']}")

    if dec["decision"] == "VIDEO_VERIFIED":
        vid = dec.get("video_id")
        if not vid or not isinstance(vid, str):
            raise ValueError("VIDEO_VERIFIED requires video_id")

        if media_resolver:
            # Reuses MediaResolver's regex check + manifest check (no absolute paths or unknown IDs)
            media_resolver._validate_video_id(vid)

def apply_verifications(decisions_path: Path, labels_path: Path, mode: str):
    if not decisions_path.exists():
        print(f"File không tồn tại: {decisions_path}")
        return

    if not labels_path.exists():
        print(f"File không tồn tại: {labels_path}")
        return

    media_resolver = None
    if mode == "video":
        try:
            config = load_config()
            path_resolver = PathResolver.from_config(config)
            media_resolver = MediaResolver(path_resolver.data_root)
        except Exception as e:
            # Fallback if config isn't available, although we should strictly try to validate.
            pass

    decisions = {}
    with open(decisions_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            dec = json.loads(line)
            qid = dec["query_id"]
            if qid in decisions:
                raise ValueError(f"Quyết định trùng lặp cho {qid} ở dòng {idx+1}")
            decisions[qid] = dec

    labels = []
    with open(labels_path, "r", encoding="utf-8") as f:
        for line in f:
            labels.append(json.loads(line))

    for label in labels:
        qid = label["query_id"]
        if qid in decisions:
            dec = decisions[qid]

            if mode == "exact":
                validate_exact_decision(dec, label)
                if dec["decision"] == "VERIFIED":
                    label["label_status"] = "labeled"
                    label["label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
                    label["gt_video_id"] = dec["video_id"]
                    if label["query_type"] in ["KIS", "QA"]:
                        label["gt_frame_ranges"] = [{
                            "start_frame": dec["start_frame_id"],
                            "representative_frame": dec["representative_frame_id"],
                            "end_frame": dec["end_frame_id"]
                        }]
                    elif label["query_type"] == "TRAKE":
                        label["gt_events"] = [
                            {
                                "start_frame": ev["start_frame_id"],
                                "representative_frame": ev.get("representative_frame_id", ev["start_frame_id"]),
                                "end_frame": ev["end_frame_id"]
                            }
                            for ev in dec["events"]
                        ]
                elif dec["decision"] == "NOT_FOUND_IN_CURRENT_POOL":
                    label["label_status"] = "labeled"
                    label["label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
                    label["gt_video_id"] = None
                    label["gt_frame_ranges"] = None
                    label["gt_events"] = None

            elif mode == "video":
                validate_video_decision(dec, label, media_resolver)
                if dec["decision"] == "VIDEO_VERIFIED":
                    label["video_verification_status"] = "VERIFIED"
                    label["video_label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
                    label["verified_video_id"] = dec["video_id"]
                elif dec["decision"] == "NOT_FOUND_IN_CURRENT_POOL":
                    label["video_verification_status"] = "VERIFIED"
                    label["video_label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
                    label["verified_video_id"] = None

    fd, temp_path = tempfile.mkstemp(dir=labels_path.parent, prefix="labels_tmp_", suffix=".jsonl")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for label in labels:
                f.write(json.dumps(label, ensure_ascii=False) + "\n")

        backup_path = labels_path.with_suffix(".jsonl.bak")
        shutil.copy2(labels_path, backup_path)
        os.replace(temp_path, labels_path)
        print(f"Cập nhật thành công. Backup tại: {backup_path.name}")
    except Exception as e:
        os.remove(temp_path)
        raise e

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", type=str, required=True)
    parser.add_argument("--labels", type=str, required=True)
    parser.add_argument("--mode", type=str, choices=["exact", "video"], default="exact")
    args = parser.add_argument()
    apply_verifications(Path(args.decisions), Path(args.labels), args.mode)
