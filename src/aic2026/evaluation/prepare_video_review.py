import json
import csv
from pathlib import Path
from typing import Any

def main():
    base = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1")
    manifest = base / "query_manifest.jsonl"
    
    with open(manifest, "r", encoding="utf-8") as f:
        queries = [json.loads(line) for line in f if json.loads(line)["split"] == "DEV"]
        
    all_candidates = []
    
    for q in queries:
        qid = q["query_id"]
        qtype = q["query_type"]
        
        vis_path = base / "runs" / "visual_only" / f"{qid}.json"
        asr_path = base / "runs" / "asr_only" / f"{qid}.json"
        fus_path = base / "runs" / "fusion_baseline" / f"{qid}.json"
        
        cands = {}
        
        def process_run(path, lane):
            if not path.exists(): return
            with open(path, "r", encoding="utf-8") as f:
                res = json.load(f).get("results", [])
                for i, r in enumerate(res):
                    vid = r["video_id"]
                    start = r["start_sec"]
                    end = r["end_sec"]
                    key = (vid, start, end)
                    if key not in cands:
                        cands[key] = {
                            "query_id": qid,
                            "query_type": qtype,
                            "query_text": q["query_text"],
                            "video_id": vid,
                            "window_start_sec": start,
                            "window_end_sec": end,
                            "visual_rank": None,
                            "asr_rank": None,
                            "fusion_rank": None,
                            "visual_anchor": "",
                            "asr_transcript": "",
                            "review_source_lanes": []
                        }
                    cands[key][f"{lane}_rank"] = i + 1
                    if lane not in cands[key]["review_source_lanes"]:
                        cands[key]["review_source_lanes"].append(lane)
                    
                    for evid in r.get("evidence", []):
                        if evid.get("modality") == "visual" and evid.get("payload", {}).get("keyframe_id") and not cands[key]["visual_anchor"]:
                            cands[key]["visual_anchor"] = evid["payload"]["keyframe_id"]
                        if evid.get("modality") == "asr" and evid.get("payload", {}).get("text") and not cands[key]["asr_transcript"]:
                            cands[key]["asr_transcript"] = evid["payload"]["text"]
                            
        process_run(vis_path, "visual")
        process_run(asr_path, "asr")
        process_run(fus_path, "fusion")
        
        cand_list = list(cands.values())
        cand_list.sort(key=lambda x: (
            -len(x["review_source_lanes"]),
            x["fusion_rank"] or 999,
            x["visual_rank"] or 999,
            x["asr_rank"] or 999
        ))
        
        final_list = cand_list[:12]
        
        for c in final_list:
            c["review_source_lanes"] = ",".join(c["review_source_lanes"])
            all_candidates.append(c)
            
    with open(base / "dev15_video_review.jsonl", "w", encoding="utf-8") as f:
        for c in all_candidates:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
            
    if all_candidates:
        fields = ["query_id", "query_type", "query_text", "video_id", "window_start_sec", "window_end_sec", "visual_rank", "asr_rank", "fusion_rank", "visual_anchor", "asr_transcript", "review_source_lanes"]
        with open(base / "dev15_video_review.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_candidates)
            
    with open(base / "operator_video_decisions_dev15.template.jsonl", "w", encoding="utf-8") as f:
        for q in queries:
            tpl = {
                "query_id": q["query_id"],
                "decision": "UNREVIEWED",
                "video_id": None,
                "note": None
            }
            f.write(json.dumps(tpl, ensure_ascii=False) + '\n')
            
    html = ["<!DOCTYPE html><html><head><meta charset='utf-8'><title>DEV15 Fast Review</title><style>body{font-family:sans-serif; margin:20px; background:#121212; color:#fff;} .cand{border:1px solid #333; padding:10px; margin-bottom:10px;} img{max-width:320px; margin-right:10px;} a {color:#4da6ff}</style></head><body><h1>DEV15 Fast Review (No thumbnails)</h1>"]
    for q in queries:
        qid = q["query_id"]
        cands = [c for c in all_candidates if c["query_id"] == qid]
        html.append(f"<h2>{qid} ({q['query_type']}): {q['query_text']}</h2>")
        for i, c in enumerate(cands):
            html.append(f"<div class='cand'><h3>Cand {i}: <a href='http://localhost:5173/media/{c['video_id']}' target='_blank'>{c['video_id']}</a> ({c['window_start_sec']} - {c['window_end_sec']}s)</h3>")
            html.append(f"<p>Ranks: Visual={c['visual_rank']}, ASR={c['asr_rank']}, Fusion={c['fusion_rank']} | Lanes: {c['review_source_lanes']}</p>")
            if c.get("visual_anchor"): html.append(f"<p>Anchor: {c['visual_anchor']}</p>")
            if c.get("asr_transcript"): html.append(f"<p>ASR: {c['asr_transcript']}</p>")
            html.append("</div>")
    html.append("</body></html>")
    
    with open(base / "dev15_video_review.html", "w", encoding="utf-8") as f:
        f.write("\n".join(html))

if __name__ == '__main__':
    main()
