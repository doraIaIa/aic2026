import pytest
from aic2026.evaluation.scoring import score_video_retrieval, score_kis, score_trake, aggregate_video_scores
from aic2026.evaluation.apply_verification import validate_video_decision

def test_video_recall_kis():
    query = {
        "query_type": "KIS",
        "video_verification_status": "VERIFIED",
        "video_label_provenance": "INTERNAL_MANUAL_VERIFIED",
        "verified_video_id": "L01_V001",
    }
    preds = [
        {"video_id": "L02_V002", "frame_idx": 10},
        {"video_id": "L01_V001", "frame_idx": 50},
    ]
    res = score_video_retrieval(query, preds)
    assert res["status"] == "SCORED"
    assert res["first_video_rank"] == 2
    assert res["metrics"]["video_r_at_1"] == 0
    assert res["metrics"]["video_r_at_5"] == 1

def test_video_recall_qa():
    query = {
        "query_type": "QA",
        "video_verification_status": "VERIFIED",
        "video_label_provenance": "INTERNAL_MANUAL_VERIFIED",
        "verified_video_id": "L01_V001",
    }
    preds = [{"video_id": "L01_V001", "frame_idx": 50}]
    res = score_video_retrieval(query, preds)
    assert res["status"] == "SCORED"
    assert res["first_video_rank"] == 1
    assert res["metrics"]["video_r_at_1"] == 1

def test_video_recall_trake():
    query = {
        "query_type": "TRAKE",
        "video_verification_status": "VERIFIED",
        "video_label_provenance": "INTERNAL_MANUAL_VERIFIED",
        "verified_video_id": "L01_V001",
    }
    preds = [{"video_id": "L01_V001", "frame_idx": 50}]
    res = score_video_retrieval(query, preds)
    assert res["status"] == "SCORED"
    assert res["first_video_rank"] == 1

def test_asr_prediction_without_frame_idx():
    query = {
        "query_type": "KIS",
        "video_verification_status": "VERIFIED",
        "video_label_provenance": "INTERNAL_MANUAL_VERIFIED",
        "verified_video_id": "L01_V001",
    }
    # No frame_idx
    preds = [{"video_id": "L01_V001", "start_sec": 1.0, "end_sec": 5.0}]
    res = score_video_retrieval(query, preds)
    assert res["status"] == "SCORED"
    assert res["first_video_rank"] == 1

def test_duplicate_evidence_windows():
    query = {
        "query_type": "KIS",
        "video_verification_status": "VERIFIED",
        "video_label_provenance": "INTERNAL_MANUAL_VERIFIED",
        "verified_video_id": "L01_V001",
    }
    preds = [
        {"video_id": "L02_V002"},
        {"video_id": "L01_V001", "start_sec": 1.0},
        {"video_id": "L01_V001", "start_sec": 10.0},
    ]
    res = score_video_retrieval(query, preds)
    assert res["first_video_rank"] == 2

def test_correct_video_outside_top_k():
    query = {
        "query_type": "KIS",
        "video_verification_status": "VERIFIED",
        "video_label_provenance": "INTERNAL_MANUAL_VERIFIED",
        "verified_video_id": "L01_V001",
    }
    preds = [{"video_id": f"L99_V{i:03d}"} for i in range(1, 10)]
    preds.append({"video_id": "L01_V001"})
    res = score_video_retrieval(query, preds)
    assert res["first_video_rank"] == 10
    assert res["metrics"]["video_r_at_5"] == 0
    assert res["metrics"]["video_r_at_20"] == 1

def test_unverified_query_excluded():
    query = {
        "query_type": "KIS",
        "video_verification_status": "UNREVIEWED",
        "verified_video_id": "L01_V001",
    }
    preds = [{"video_id": "L01_V001"}]
    res = score_video_retrieval(query, preds)
    assert res["status"] == "UNVERIFIED"
    assert res["first_video_rank"] is None

def test_arbitrary_video_id_cannot_leak():
    query = {
        "query_type": "KIS",
        "video_id": "L99_V999", # Arbitrary generic field
        "video_verification_status": "VERIFIED",
        "video_label_provenance": "INTERNAL_MANUAL_VERIFIED",
        "verified_video_id": "L01_V001",
    }
    preds = [{"video_id": "L99_V999"}]
    res = score_video_retrieval(query, preds)
    # L99_V999 shouldn't trigger a match
    assert res["first_video_rank"] is None

def test_invalid_video_id_rejected():
    base_label = {"query_type": "KIS"}
    dec = {"decision": "VIDEO_VERIFIED", "video_id": ""}
    with pytest.raises(ValueError):
        validate_video_decision(dec, base_label)

    dec2 = {"decision": "VIDEO_VERIFIED"}
    with pytest.raises(ValueError):
        validate_video_decision(dec2, base_label)

def test_exact_kis_regression():
    query = {
        "query_type": "KIS",
        "gt_video_id": "L01_V001",
        "gt_frame_ranges": [{"start_frame": 100, "end_frame": 150}]
    }
    # Correct video, wrong frame
    preds1 = [{"video_id": "L01_V001", "frame_idx": 50}]
    res1 = score_kis(query, preds1)
    assert res1["first_correct_rank"] is None
    
    # Correct video, correct frame
    preds2 = [{"video_id": "L01_V001", "frame_idx": 120}]
    res2 = score_kis(query, preds2)
    assert res2["first_correct_rank"] == 1

def test_exact_trake_multi_event_regression():
    query = {
        "query_type": "TRAKE",
        "gt_video_id": "L01_V001",
        "gt_events": [
            {"start_frame": 100, "end_frame": 150},
            {"start_frame": 300, "end_frame": 350},
        ]
    }
    # One event matched
    preds1 = [{"video_id": "L01_V001", "frame_idx": 120}]
    res1 = score_trake(query, preds1)
    assert res1["metrics"]["r_at_1"] == 0.5
    
    # Another prediction matches the other event
    preds2 = [
        {"video_id": "L01_V001", "frame_idx": 120},
        {"video_id": "L01_V001", "frame_idx": 320},
    ]
    res2 = score_trake(query, preds2)
    assert res2["metrics"]["r_at_1"] == 0.5
    assert res2["metrics"]["r_at_5"] == 0.5
