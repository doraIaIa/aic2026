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
        if base_label["query_type"] == "KIS":
            if not dec.get("video_id"):
                raise ValueError("VERIFIED KIS requires video_id")
            for field in ["start_frame_id", "representative_frame_id", "end_frame_id"]:
                if type(dec.get(field)) is not int or dec[field] < 0:
                    raise ValueError(f"VERIFIED KIS requires non-negative integer {field}")

            s, r, e = dec["start_frame_id"], dec["representative_frame_id"], dec["end_frame_id"]
            if not (s <= r <= e):
                raise ValueError("Invalid KIS frame range: start <= representative <= end must hold")

        elif base_label["query_type"] == "QA":
            if not dec.get("video_id"):
                raise ValueError("VERIFIED QA requires video_id")
            for field in ["start_frame_id", "representative_frame_id", "end_frame_id"]:
                if type(dec.get(field)) is not int or dec[field] < 0:
                    raise ValueError(f"VERIFIED QA requires non-negative integer {field}")
            s, r, e = dec["start_frame_id"], dec["representative_frame_id"], dec["end_frame_id"]
            if not (s <= r <= e):
                raise ValueError("Invalid QA frame range")
            if not dec.get("answer_text"):
                raise ValueError("VERIFIED QA requires answer_text")

        elif base_label["query_type"] == "TRAKE":
            if not dec.get("video_id"):
                raise ValueError("VERIFIED TRAKE requires video_id")
            events = dec.get("events", [])
            if not isinstance(events, list) or len(events) == 0:
                raise ValueError("VERIFIED TRAKE requires at least one event")

            orders = set()
            for i, ev in enumerate(events):
                for field in ["event_order", "start_frame_id", "representative_frame_id", "end_frame_id"]:
                    if field not in ev or type(ev[field]) is not int or ev[field] < 0:
                        raise ValueError(f"TRAKE events must have non-negative integer {field}")
                s, r, e = ev["start_frame_id"], ev["representative_frame_id"], ev["end_frame_id"]
                if not (s <= r <= e):
                    raise ValueError("Invalid TRAKE frame range")
                orders.add(ev["event_order"])

            if sorted(list(orders)) != list(range(len(events))):
                raise ValueError("TRAKE event_order sequence must be 0, 1, 2...")

def validate_video_decision(dec, base_label, media_resolver=None):
    valid_decisions = ["UNREVIEWED", "VIDEO_VERIFIED", "NOT_FOUND_IN_CURRENT_POOL", "NEEDS_MORE_REVIEW", "UNRESOLVED"]
    if dec["decision"] not in valid_decisions:
        raise ValueError(f"Invalid video decision status: {dec['decision']}")

    if dec["decision"] == "VIDEO_VERIFIED":
        vid = dec.get("video_id")
        if not vid or not isinstance(vid, str):
            raise ValueError("VIDEO_VERIFIED requires video_id")

        if media_resolver:
            media_resolver._validate_video_id(vid)
            if not media_resolver.is_available(vid):
                raise ValueError(f"Video {vid} is unknown/not found in media manifest")

def apply_verifications(decisions_path: Path, labels_path: Path, mode: str):
    if not decisions_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {decisions_path}")

    if not labels_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {labels_path}")

    media_resolver = None
    if mode == "video":
        try:
            config = load_config()
            path_resolver = PathResolver.from_config(config)
            media_resolver = MediaResolver(path_resolver.data_root)
        except Exception as e:
            raise RuntimeError(f"Cannot initialize MediaResolver: {e}")

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

    # Audit for unknown queries
    label_qids = {l["query_id"] for l in labels}
    for qid in decisions:
        if qid not in label_qids:
            raise ValueError(f"Decision references unknown query_id: {qid}")

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
                    if label["query_type"] == "KIS":
                        label["gt_frame_ranges"] = [{
                            "start_frame": dec["start_frame_id"],
                            "representative_frame": dec["representative_frame_id"],
                            "end_frame": dec["end_frame_id"]
                        }]
                    elif label["query_type"] == "QA":
                        label["gt_frame_ranges"] = [{
                            "start_frame": dec["start_frame_id"],
                            "representative_frame": dec["representative_frame_id"],
                            "end_frame": dec["end_frame_id"]
                        }]
                        label["answer_text"] = dec["answer_text"]
                        if "answer_variants" in dec:
                            label["answer_variants"] = dec["answer_variants"]
                    elif label["query_type"] == "TRAKE":
                        sorted_events = sorted(dec["events"], key=lambda x: x["event_order"])
                        label["gt_events"] = [
                            {
                                "start_frame": ev["start_frame_id"],
                                "representative_frame": ev["representative_frame_id"],
                                "end_frame": ev["end_frame_id"]
                            }
                            for ev in sorted_events
                        ]
                elif dec["decision"] in ["NOT_FOUND_IN_CURRENT_POOL", "NEEDS_MORE_REVIEW", "UNRESOLVED"]:
                    label["label_status"] = "labeled" if dec["decision"] == "NOT_FOUND_IN_CURRENT_POOL" else "unlabeled_reference"
                    label["label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
                    label["gt_video_id"] = None
                    label["gt_frame_ranges"] = None
                    label["gt_events"] = None
                    label.pop("answer_text", None)
                    label.pop("answer_variants", None)

            elif mode == "video":
                validate_video_decision(dec, label, media_resolver)
                if dec["decision"] == "VIDEO_VERIFIED":
                    label["video_verification_status"] = "VERIFIED"
                    label["video_label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
                    label["verified_video_id"] = dec["video_id"]
                elif dec["decision"] == "NOT_FOUND_IN_CURRENT_POOL":
                    label["video_verification_status"] = "NOT_FOUND_IN_CURRENT_POOL"
                    label["video_label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
                    label["verified_video_id"] = None
                elif dec["decision"] in ["NEEDS_MORE_REVIEW", "UNRESOLVED"]:
                    label["video_verification_status"] = dec["decision"]
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
    args = parser.parse_args()
    apply_verifications(Path(args.decisions), Path(args.labels), args.mode)
