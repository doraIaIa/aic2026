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
    preds = [{"video_id": "L01_V001", "frame_ids": [50]}]
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

def test_exact_trake_correct_model():
    query = {
        "query_type": "TRAKE",
        "gt_video_id": "A",
        "gt_events": [
            {"start_frame": 100, "end_frame": 110},
            {"start_frame": 200, "end_frame": 210},
        ]
    }
    # Expected cases:
    # A, [105,205] -> 1.0
    # A, [105,500] -> 0.5
    # A, [500,205] -> 0.5
    # A, [500,500] -> 0.0
    # B, [105,205] -> 0.0

    preds = [
        {"video_id": "A", "frame_ids": [105, 500]}, # rank 1
        {"video_id": "B", "frame_ids": [105, 205]}, # rank 2
        {"video_id": "A", "frame_ids": [500, 500]}, # rank 3
        {"video_id": "A", "frame_ids": [105, 205]}, # rank 4
        {"video_id": "A", "frame_ids": [500, 205]}, # rank 5
    ]

    res = score_trake(query, preds)
    # The scores would be: 0.5, 0.0, 0.0, 1.0, 0.5
    # Max in top 1: 0.5
    # Max in top 5: 1.0
    assert res["metrics"]["r_at_1"] == 0.5
    assert res["metrics"]["r_at_5"] == 1.0
