from pathlib import Path
import json
import csv
from aic2026.retrieval.providers import AsrProvider, VisualProvider
from aic2026.retrieval.capabilities import CapabilityService
from aic2026.retrieval.orchestrator import SearchOrchestrator
from aic2026.core.config import load_config
from aic2026.core.paths import PathResolver
import os

def run_predictions():
    config = {
        "paths": {
            "work_root": "F:/AIC_WORK",
            "data_root": "G:/.shortcut-targets-by-id/1DRuEcR4suoHb4rKrPDtzt9FRfkvfqfHv/AIC_2026",
            "artifact_root": "F:/AIC_WORK/artifacts"
        }
    }
    resolver = PathResolver.from_config(config)
    database = resolver.work("db/aic.sqlite")
    capability_service = CapabilityService(
        {
            "asr": AsrProvider(database),
            "visual": VisualProvider(resolver.artifact("m1/clip-faiss-btc-v1")),
        },
        media_root=resolver.data_root,
    )
    orchestrator = SearchOrchestrator(capability_service.providers)
    
    internal_verified_dir = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1")
    manifest_path = internal_verified_dir / "query_manifest.jsonl"
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        queries = [json.loads(line) for line in f]
        
    runs_dir = internal_verified_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    
    modes = {
        "visual_only": {"strategy": "manual", "enabled_lanes": ["visual"], "object_match": "soft"},
        "asr_only": {"strategy": "manual", "enabled_lanes": ["asr"], "object_match": "soft"},
        "fusion_baseline": {"strategy": "auto", "enabled_lanes": ["visual", "asr"], "object_match": "soft"}
    }
    
    for mode, routing in modes.items():
        mode_dir = runs_dir / mode
        mode_dir.mkdir(exist_ok=True)
        
        run_manifest = {
            "run_id": mode,
            "query_set_version": "internal_verified_v1",
            "routing_mode": routing,
        }
        with open(mode_dir / "run_manifest.json", 'w') as f:
            json.dump(run_manifest, f)
            
    review_queue = {}
    
    for q in queries:
        qid = q["query_id"]
        qtext = q["query_text"]
        
        for mode, routing in modes.items():
            req = {
                "contract_version": "retrieval.v1",
                "request_id": f"eval_{mode}_{qid}",
                "mode": q["query_type"],
                "query_text": qtext,
                "routing": routing,
                "filters": {},
                "result_limit": 100
            }
            res = orchestrator.search(req)
            
            with open(runs_dir / mode / f"{qid}.json", 'w', encoding='utf-8') as f:
                json.dump(res, f, ensure_ascii=False)
                
            for i, c in enumerate(res.get("results", [])[:10]):
                vid = c["video_id"]
                key = (qid, vid)
                if key not in review_queue:
                    review_queue[key] = {
                        "query_id": qid,
                        "query_text": qtext,
                        "query_type": q["query_type"],
                        "video_id": vid,
                        "visual_rank": None,
                        "asr_rank": None,
                        "fusion_rank": None,
                        "start_frame_id": "",
                        "end_frame_id": "",
                        "representative_frame_idx": c.get("representative", {}).get("frame_idx", ""),
                        "asr_transcript": "",
                        "visual_anchor": ""
                    }
                
                if mode == "visual_only" and review_queue[key]["visual_rank"] is None:
                    review_queue[key]["visual_rank"] = i + 1
                    for evid in c.get("evidence", []):
                        if evid.get("modality") == "visual" and evid.get("payload", {}).get("keyframe_id"):
                            review_queue[key]["visual_anchor"] = evid["payload"]["keyframe_id"]
                            break
                            
                elif mode == "asr_only" and review_queue[key]["asr_rank"] is None:
                    review_queue[key]["asr_rank"] = i + 1
                    for evid in c.get("evidence", []):
                        if evid.get("modality") == "asr" and evid.get("payload", {}).get("text"):
                            review_queue[key]["asr_transcript"] = evid["payload"]["text"]
                            break
                            
                elif mode == "fusion_baseline" and review_queue[key]["fusion_rank"] is None:
                    review_queue[key]["fusion_rank"] = i + 1
                    
    rq_list = list(review_queue.values())
    rq_list.sort(key=lambda x: (x["query_id"], x["fusion_rank"] or 999, x["visual_rank"] or 999, x["asr_rank"] or 999))
    
    with open(internal_verified_dir / "review_queue.jsonl", 'w', encoding='utf-8') as f:
        for r in rq_list:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            
    with open(internal_verified_dir / "review_queue.csv", 'w', encoding='utf-8', newline='') as f:
        if rq_list:
            writer = csv.DictWriter(f, fieldnames=rq_list[0].keys())
            writer.writeheader()
            writer.writerows(rq_list)
            
    print(f"Generated {len(rq_list)} review queue items")
    orchestrator.close()

if __name__ == '__main__':
    run_predictions()
