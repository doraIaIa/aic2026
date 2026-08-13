import json
import argparse
from pathlib import Path
import tempfile
import os
import shutil

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
                raise ValueError(f"Invalid frame range: {s} <= {r} <= {e} is false")
                
            if base_label["query_type"] == "QA":
                if not dec.get("answer_text"):
                    raise ValueError("VERIFIED QA requires answer_text")
                    
        elif base_label["query_type"] == "TRAKE":
            if not dec.get("video_id"):
                raise ValueError("VERIFIED TRAKE requires video_id")
            events = dec.get("events", [])
            if not events:
                raise ValueError("VERIFIED TRAKE requires events")
            
            orders = set()
            for ev in events:
                orders.add(ev["event_order"])
                for field in ["start_frame_id", "representative_frame_id", "end_frame_id"]:
                    if not isinstance(ev.get(field), int):
                        raise ValueError(f"TRAKE event requires integer {field}")
                s, r, e = ev["start_frame_id"], ev["representative_frame_id"], ev["end_frame_id"]
                if not (s <= r <= e):
                    raise ValueError(f"Invalid frame range in TRAKE event: {s} <= {r} <= {e} is false")
            
            if len(orders) != len(events):
                raise ValueError("TRAKE events contain duplicate event_order")

def validate_video_decision(dec, base_label):
    if dec["decision"] not in ["UNREVIEWED", "VIDEO_VERIFIED", "NEEDS_MORE_REVIEW", "NOT_FOUND_IN_CURRENT_POOL", "UNRESOLVED"]:
        raise ValueError(f"Invalid decision status: {dec['decision']}")
        
    if dec["decision"] == "VIDEO_VERIFIED":
        if not dec.get("video_id"):
            raise ValueError("VIDEO_VERIFIED requires video_id")
        vid = dec["video_id"]
        if not isinstance(vid, str) or not vid.strip():
            raise ValueError("video_id must be a valid string")

def apply_verifications(labels_path: Path, decisions_path: Path, mode: str):
    if not labels_path.exists():
        raise FileNotFoundError(f"Labels file missing: {labels_path}")
    if not decisions_path.exists():
        raise FileNotFoundError(f"Decisions file missing: {decisions_path}")
        
    with open(labels_path, 'r', encoding='utf-8') as f:
        labels = [json.loads(line) for line in f]
        
    label_map = {lbl["query_id"]: lbl for lbl in labels}
    
    with open(decisions_path, 'r', encoding='utf-8') as f:
        decisions = [json.loads(line) for line in f]
        
    # Prevent duplicate decisions
    seen_queries = set()
    for dec in decisions:
        qid = dec.get("query_id")
        if not qid:
            raise ValueError("Missing query_id in decision")
        if qid in seen_queries:
            raise ValueError(f"Duplicate decision for query_id: {qid}")
        seen_queries.add(qid)
        if qid not in label_map:
            raise ValueError(f"Decision references unknown query_id: {qid}")
            
        base_lbl = label_map[qid]
        if mode == "exact":
            validate_exact_decision(dec, base_lbl)
        elif mode == "video":
            validate_video_decision(dec, base_lbl)
        
    applied_count = 0
    for dec in decisions:
        qid = dec["query_id"]
        lbl = label_map[qid]
        
        if mode == "exact" and dec["decision"] == "VERIFIED":
            lbl["verification_status"] = "VERIFIED"
            lbl["label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
            lbl["verified_by"] = "operator"
            lbl["video_id"] = dec["video_id"]
            
            if lbl["query_type"] in ["KIS", "QA"]:
                lbl["representative_frame_id"] = dec["representative_frame_id"]
                lbl["frame_ranges"] = [{"start_frame_id": dec["start_frame_id"], "end_frame_id": dec["end_frame_id"]}]
                if lbl["query_type"] == "QA":
                    lbl["answer_text"] = dec["answer_text"]
            elif lbl["query_type"] == "TRAKE":
                lbl["events"] = dec["events"]
            applied_count += 1
            
        elif mode == "video" and dec["decision"] == "VIDEO_VERIFIED":
            lbl["video_verification_status"] = "VERIFIED"
            lbl["verified_video_id"] = dec["video_id"]
            lbl["video_label_provenance"] = "INTERNAL_MANUAL_VERIFIED"
            lbl["video_verified_by"] = "operator"
            applied_count += 1
            
    if applied_count == 0:
        print("No VERIFIED decisions to apply.")
        return
        
    backup_path = labels_path.with_name(f"labels.before-{'video' if mode == 'video' else 'exact'}.jsonl")
    if not backup_path.exists():
        shutil.copy2(labels_path, backup_path)
        print(f"Created backup at {backup_path}")
        
    fd, temp_path = tempfile.mkstemp(dir=labels_path.parent, suffix=".jsonl")
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        for lbl in labels:
            f.write(json.dumps(lbl, ensure_ascii=False) + '\n')
            
    os.replace(temp_path, labels_path)
    print(f"Successfully applied {applied_count} verified decisions to {labels_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--mode", type=str, choices=["exact", "video"], default="exact")
    args = parser.parse_args()
    apply_verifications(args.labels, args.decisions, args.mode)
