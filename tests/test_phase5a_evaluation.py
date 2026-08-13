import json
import pytest
from pathlib import Path
from aic2026.evaluation.labels import BaseLabel, KisLabel, QaLabel, TrakeLabel
from aic2026.evaluation.dataset import create_internal_verified_dataset

def test_manifest_determinism(tmp_path):
    combined_query_file = Path(r"F:\AIC_DEV\aic2026\query-p3-groupA_combined.txt")
    
    if not combined_query_file.exists():
        pytest.skip("Combined query file not available")
        
    sampled1 = create_internal_verified_dataset(combined_query_file, tmp_path / "run1")
    sampled2 = create_internal_verified_dataset(combined_query_file, tmp_path / "run2")
    
    assert len(sampled1) == 20
    assert len(sampled2) == 20
    assert [q['query_id'] for q in sampled1] == [q['query_id'] for q in sampled2]
    
    splits = [q['split'] for q in sampled1]
    assert splits.count('DEV') == 15
    assert splits.count('HOLDOUT') == 5
    
    kis = [q for q in sampled1 if q['query_type'] == 'KIS']
    assert len(kis) == 14
    
def test_label_schema_validation():
    # KIS
    kis_lbl = KisLabel(
        query_id="q1",
        query_text="Find car",
        split="DEV"
    )
    assert kis_lbl.verification_status == "UNVERIFIED"
    assert kis_lbl.frame_ranges == []
    assert kis_lbl.dataset_version == "internal_verified_v1"
    
    # QA
    qa_lbl = QaLabel(
        query_id="q2",
        query_text="Where is car?",
        split="HOLDOUT"
    )
    assert qa_lbl.answer_verification == "MANUAL"
    
    # TRAKE
    trake_lbl = TrakeLabel(
        query_id="q3",
        query_text="Car moving. Car stops.",
        split="DEV"
    )
    assert trake_lbl.query_type == "TRAKE"
    assert trake_lbl.events == []

def test_prediction_run_mode_isolation():
    # Read the run_manifest.json to ensure modes are properly isolated
    run_dir = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1\runs")
    if not run_dir.exists():
        pytest.skip("Runs not generated yet")
        
    for mode in ["visual_only", "asr_only", "fusion_baseline"]:
        manifest_path = run_dir / mode / "run_manifest.json"
        assert manifest_path.exists()
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
            if mode == "visual_only":
                assert manifest["routing_mode"]["enabled_lanes"] == ["visual"]
            elif mode == "asr_only":
                assert manifest["routing_mode"]["enabled_lanes"] == ["asr"]
            elif mode == "fusion_baseline":
                assert manifest["routing_mode"]["strategy"] == "auto"

def test_top100_cap():
    run_dir = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1\runs")
    if not run_dir.exists():
        pytest.skip("Runs not generated yet")
        
    # Check one run result
    for mode in ["visual_only"]:
        for file in (run_dir / mode).glob("*.json"):
            if file.name != "run_manifest.json":
                with open(file, 'r', encoding='utf-8') as f:
                    res = json.load(f)
                    assert len(res.get("candidates", [])) <= 100
                    
