from pathlib import Path
import json
import random
from typing import Any
from aic2026.evaluation.importers import parse_combined_queries

DATASET_VERSION = "internal_verified_v1"

def create_internal_verified_dataset(combined_query_file: Path, output_dir: Path):
    text = combined_query_file.read_text(encoding='utf-8')
    queries = parse_combined_queries(text)
    
    kis = [q for q in queries if q['query_type'] == 'KIS']
    qa = [q for q in queries if q['query_type'] == 'QA']
    trake = [q for q in queries if q['query_type'] == 'TRAKE']
    
    rng = random.Random(42)
    rng.shuffle(kis)
    rng.shuffle(qa)
    rng.shuffle(trake)
    
    # 14 KIS, 4 QA, 2 TRAKE
    selected_kis = kis[:14]
    selected_qa = qa[:4]
    selected_trake = trake[:2]
    
    # DEV: 11 KIS, 3 QA, 1 TRAKE
    # HOLDOUT: 3 KIS, 1 QA, 1 TRAKE
    dev = selected_kis[:11] + selected_qa[:3] + selected_trake[:1]
    holdout = selected_kis[11:] + selected_qa[3:] + selected_trake[1:]
    
    for q in dev:
        q['split'] = 'DEV'
    for q in holdout:
        q['split'] = 'HOLDOUT'
        
    sampled = dev + holdout
    # Re-sort to maintain deterministic original order
    sampled.sort(key=lambda x: x['query_id'])
    
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "query_manifest.jsonl"
    
    with open(manifest_path, 'w', encoding='utf-8') as f:
        for q in sampled:
            manifest_q = {
                "dataset_version": DATASET_VERSION,
                "query_id": q["query_id"],
                "query_type": q["query_type"],
                "query_text": q["query_text"],
                "split": q["split"]
            }
            f.write(json.dumps(manifest_q, ensure_ascii=False) + '\n')
            
    print(f"Created {manifest_path} with {len(sampled)} queries")
    return sampled

if __name__ == '__main__':
    combined_query_file = Path(r"F:\AIC_DEV\aic2026\query-p3-groupA_combined.txt")
    output_dir = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1")
    create_internal_verified_dataset(combined_query_file, output_dir)
