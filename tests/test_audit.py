import json
import os
from pathlib import Path
import numpy as np
import pytest

from aic2026.audit.discovery import run_discovery
from aic2026.audit.modalities import run_modalities
from aic2026.audit.clip import run_clip
from aic2026.audit.report import generate_reports
from aic2026.audit.mapping import clip_row_to_csv_n, resolve_keyframe_name

@pytest.fixture
def synthetic_corpus(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    
    # Nested corpus discovery (1)
    vid_dir = data_root / "Videos" / "Batch1"
    vid_dir.mkdir(parents=True)
    
    # 2 duplicate video IDs (2)
    (vid_dir / "L01_V001.mp4").write_text("fake video")
    # Same ID, different extension
    (vid_dir / "L01_V001.mkv").write_text("fake video duplicate")
    
    (vid_dir / "L01_V002.mp4").write_text("fake video 2")
    
    # Keyframes (5, 6)
    kf_dir1 = data_root / "Keyframes" / "L01_V001"
    kf_dir1.mkdir(parents=True)
    (kf_dir1 / "000001.jpg").write_text("kf")
    (kf_dir1 / "000002.jpg").write_text("kf")
    (kf_dir1 / "000004.jpg").write_text("kf") # Gap
    (kf_dir1 / "000004_copy.jpg").write_text("kf") # Duplicate ordinal
    
    kf_dir2 = data_root / "Keyframes" / "L01_V002"
    kf_dir2.mkdir(parents=True)
    for i in range(10):
        (kf_dir2 / f"{i:06d}.jpg").write_text("kf")
        
    # Metadata (3, 10)
    meta_dir = data_root / "Metadata"
    meta_dir.mkdir()
    (meta_dir / "L01_V001.json").write_text(json.dumps([{"frame_idx": 1}, {"frame_idx": 2}]))
    (meta_dir / "L01_V003.json").write_text("corrupt { json") # Malformed (10), L01_V003 is orphan
    
    # Objects (4)
    # L01_V001 is missing objects
    obj_dir = data_root / "Objects"
    obj_dir.mkdir()
    (obj_dir / "L01_V002.json").write_text(json.dumps([{"label": "person"}]))
    
    # CLIP (7, 8, 9)
    clip_dir = data_root / "CLIP"
    clip_dir.mkdir()
    # Mismatch count (L01_V001 has 4 keyframes, array has 5)
    np.save(clip_dir / "L01_V001.npy", np.zeros((5, 512)))
    # Match count
    np.save(clip_dir / "L01_V002.npy", np.zeros((10, 512)))
    # Corrupt
    (clip_dir / "L01_V003.npy").write_text("corrupt npy data")
    
    return data_root

def test_audit_pipeline(tmp_path, synthetic_corpus):
    audit_dir = tmp_path / "audit"
    
    # Step A, B, C
    run_discovery(synthetic_corpus, audit_dir)
    
    assert (audit_dir / "dataset_tree.json").exists()
    assert (audit_dir / "videos.jsonl").exists()
    assert (audit_dir / "keyframes.jsonl").exists()
    
    # Modalities
    run_modalities(synthetic_corpus, audit_dir)
    
    assert (audit_dir / "objects.json").exists()
    assert (audit_dir / "metadata.json").exists()
    
    # Check absolute path rejection / relative path enforcement (11, 13)
    manifest_path = tmp_path / "AIC_WORK" / "manifests" / "corpus_manifest.jsonl"
    assert manifest_path.exists()
    with open(manifest_path, "r") as f:
        for line in f:
            item = json.loads(line)
            # Paths must not start with / or C:\ or be absolute
            assert not Path(item["video_relpath"]).is_absolute()
            
    # CLIP
    run_clip(synthetic_corpus, audit_dir)
    assert (audit_dir / "clip_features.json").exists()
    with open(audit_dir / "clip_features.json", "r") as f:
        clip = json.load(f)
        assert clip["mismatches"] >= 1
        assert clip["corrupted_files"] >= 1
        
    # Generate final report
    generate_reports(audit_dir)
    report_path = audit_dir / "M0A_REPORT.md"
    assert report_path.exists()
    
    report_content = report_path.read_text()
    assert "M0A DATASET AUDIT" in report_content
    # Missing objects
    assert "Missing objects       1" in report_content
    # Missing metadata
    assert "Missing metadata      1" in report_content


def test_keyframe_filename_uses_csv_n_not_frame_idx():
    keyframe_info = {"first_filename": "001.jpg"}

    row_1 = {"n": "1", "pts_time": "0.0", "fps": "25", "frame_idx": "0"}
    assert resolve_keyframe_name(row_1, keyframe_info) == "001.jpg"

    row_2 = {"n": "2", "pts_time": "3.0", "fps": "25", "frame_idx": "75"}
    assert resolve_keyframe_name(row_2, keyframe_info) == "002.jpg"


def test_clip_row_maps_to_csv_n():
    assert clip_row_to_csv_n(0) == 1
    assert clip_row_to_csv_n(1) == 2
