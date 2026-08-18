import json
import os
import shutil
from pathlib import Path
from collections import defaultdict

from aic2026.retrieval.providers import AsrProvider, VisualProvider
from aic2026.retrieval.capabilities import CapabilityService
from aic2026.retrieval.orchestrator import SearchOrchestrator
from aic2026.core.config import load_config
from aic2026.core.paths import PathResolver

# Manual annotations for assist
DECOMPOSITION = {
    'query-p3-1-trake': {'visual': ['chef stirring sauce', 'chef pouring sauce on fish'], 'asr': []},
    'query-p3-11-kis': {'visual': ['traffic police extinguishing burning car', 'burning car speed limit sign 120'], 'asr': ['120']},
    'query-p3-12-kis': {'visual': ['dragon dance soccer uniform', 'dragon dance performers'], 'asr': []},
    'query-p3-13-qa': {'visual': ['mâm bánh xèo', 'gian hàng bánh', 'bánh xèo stall'], 'asr': ['"Bánh Dân Gian Miền Tây"']},
    'query-p3-14-kis': {'visual': ['fruit decoration', 'fruit art portrait', 'fruit art tank'], 'asr': ['"Bác Hồ"', '"Dinh Độc Lập"', '390']},
    'query-p3-15-kis': {'visual': ['peeling shrimp', 'plate of peeled shrimp'], 'asr': []},
    'query-p3-17-kis': {'visual': ['women ao dai holding flowers', 'women ao dai walking street'], 'asr': ['"chợ Bến Thành"']},
    'query-p3-18-kis': {'visual': ['durian fruit', 'aerial view pushing durian cart'], 'asr': []},
    'query-p3-20-qa': {'visual': ['table full of CD cases', 'CD album cover close up'], 'asr': ['"Khung trời mơ ước"', '"Nhớ ai"']},
    'query-p3-22-kis': {'visual': ['opening snack bag inside view', 'plate of potato chips'], 'asr': []},
    'query-p3-26-kis': {'visual': ['flooded street walking', 'milestone road sign'], 'asr': ['QL60', 'KM00', '"Tân An"']},
    'query-p3-27-kis': {'visual': ['Donald Trump female officer airport', 'Donald Trump walking airport'], 'asr': []},
    'query-p3-35-qa': {'visual': ['vaccine lab', 'virus graphics'], 'asr': ['vaccine', '88%', '88']},
    'query-p3-7-kis': {'visual': ['boy blue pants girl looking at fire', 'firefighters putting out fire', 'people livestreaming fire'], 'asr': ['"Đồng Xoài"']},
    'query-p3-8-kis': {'visual': ['3D spacecraft orbit', 'spacecraft scanning surface waves'], 'asr': []}
}

def run_assist():
    base = Path(r'F:\AIC_WORK\artifacts\evaluation\internal-verified-v1')
    assist_dir = base / 'annotation_assist_v1'
    assist_dir.mkdir(exist_ok=True)
    
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
    
    manifest_path = base / "query_manifest.jsonl"
    with open(manifest_path, 'r', encoding='utf-8') as f:
        queries = [json.loads(line) for line in f if json.loads(line)['split'] == 'DEV']
        
    visual_dir = base / 'runs' / 'visual_only'
    
    html_lines = [
        "<html><head><meta charset='utf-8'><title>RESCUE CONTACT SHEET</title></head><body>",
        "<h1>ANNOTATION ASSIST ONLY - NOT BASELINE RESULTS - NOT VERIFIED LABELS</h1>"
    ]
    
    jsonl_out = []
    
    for q in queries:
        q_id = q['query_id']
        html_lines.append(f"<hr><h2>Query: {q_id} ({q['query_type']})</h2>")
        text = q.get('query_text', q.get('query', ''))
        html_lines.append(f"<p><b>Text:</b> {text}</p>")
        
        # Aggregate candidates
        video_cands = defaultdict(lambda: {'score': 0, 'reasons': []})
        
        # Stage A
        vf = visual_dir / f"{q_id}.json"
        if vf.exists():
            with open(vf, 'r', encoding='utf-8') as f:
                v_data = json.load(f).get('results', [])
            for c in v_data[8:40]: # rank 9 to 40
                vid = c['video_id']
                v_rank = c['evidence'][0]['rank']
                if 'thumb' not in video_cands[vid]:
                    video_cands[vid]['thumb'] = c['sources']['keyframe_relpath']
                video_cands[vid]['score'] += (50 - v_rank) # heuristic
                video_cands[vid]['reasons'].append(f"Visual Rank {v_rank}")
                
        # Stage B
        decomp = DECOMPOSITION.get(q_id, {})
        for v_phrase in decomp.get('visual', []):
            try:
                # Need to use the proper internal search parameters matching the contract.
                req_params = {"q": [v_phrase], "limit": ["20"], "mode": ["visual"], "object_match": ["soft"]}
                # Actually, orchestrator.search(query, ...)
                # Let's see the orchestrator signature, it might be (query, config...)
                # The prompt implies we can just search. I'll mock the api call via capability service directly if orchestrator needs specific request objects.
                # Since capability_service.providers['visual'].search(v_phrase, 20) is easier.
                res = capability_service.providers['visual'].search(v_phrase, limit=20)
                for i, c in enumerate(res):
                    vid = c['video_id']
                    if 'thumb' not in video_cands[vid]:
                        video_cands[vid]['thumb'] = c['keyframe_relpath']
                    video_cands[vid]['score'] += (20 - i)
                    video_cands[vid]['reasons'].append(f"Visual hit: '{v_phrase}' (rank {i+1})")
            except Exception as e:
                print(f"Error visual assist {v_phrase}: {e}")
                
        # Stage C
        for a_phrase in decomp.get('asr', []):
            try:
                res = capability_service.providers['asr'].search(a_phrase, limit=20)
                for i, c in enumerate(res):
                    vid = c['video_id']
                    if 'thumb' not in video_cands[vid]:
                        video_cands[vid]['thumb'] = c['keyframe_relpath'] # or similar
                    video_cands[vid]['score'] += 30 # ASR is strong evidence
                    video_cands[vid]['reasons'].append(f"ASR hit: '{a_phrase}'")
            except Exception as e:
                print(f"Error asr assist {a_phrase}: {e}")
                
        # Sort and take top 20
        sorted_cands = sorted(video_cands.items(), key=lambda x: x[1]['score'], reverse=True)[:20]
        
        html_lines.append(f"<h3>Rescue Candidates ({len(sorted_cands)})</h3>")
        html_lines.append("<div style='display:flex; flex-wrap:wrap;'>")
        
        for cand_idx, (vid, c_data) in enumerate(sorted_cands):
            reasons_str = "<br>".join(set(c_data['reasons']))
            img_src = resolver.data(c_data['thumb']).as_posix() if c_data.get('thumb') else ""
            
            html_lines.append(f"<div style='margin:10px; border:1px solid #ccc; padding:5px; width:300px'>")
            html_lines.append(f"<b>Cand {cand_idx+1}: {vid}</b><br>")
            html_lines.append(f"<i>Priority Score: {c_data['score']}</i><br>")
            if img_src:
                html_lines.append(f"<img src='file:///{img_src}' style='width:100%'><br>")
            html_lines.append(f"<p style='font-size:12px'>{reasons_str}</p>")
            html_lines.append("</div>")
            
            jsonl_out.append({
                "query_id": q_id,
                "video_id": vid,
                "annotation_assist_priority": c_data['score'],
                "reasons": list(set(c_data['reasons'])),
                "thumbnail_path": img_src,
                "assist_type": "ANNOTATION_ASSIST_ONLY"
            })
            
        html_lines.append("</div>")

    html_lines.append("</body></html>")
    
    with open(assist_dir / 'dev15_rescue_review.html', 'w', encoding='utf-8') as f:
        f.write("\n".join(html_lines))
        
    with open(assist_dir / 'dev15_rescue_review.jsonl', 'w', encoding='utf-8') as f:
        for d in jsonl_out:
            f.write(json.dumps(d, ensure_ascii=False) + '\n')
            
    print(f"Generated {len(jsonl_out)} total assist candidates across {len(queries)} queries.")

if __name__ == '__main__':
    run_assist()
