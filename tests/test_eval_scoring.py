import pytest

from aic2026.evaluation.contract import EvalContractError
from aic2026.evaluation.scoring import aggregate_scores, score_query


def _kis_query(**overrides):
    query = {
        "query_id": "q1",
        "query_type": "KIS",
        "trap_category": "visual",
        "split": "dev",
        "label_status": "labeled",
        "gt_video_id": "V1",
        "gt_frame_ranges": [
            {"start_frame": 10, "end_frame": 20},
            {"start_frame": 40, "end_frame": 45},
        ],
    }
    query.update(overrides)
    return query


def _candidate(index, *, video_id="WRONG", frame_idx=None):
    return {
        "embedding_id": index + 1,
        "video_id": video_id,
        "frame_idx": index if frame_idx is None else frame_idx,
    }


@pytest.mark.parametrize("boundary", [10, 20, 40, 45])
def test_kis_inclusive_boundaries_and_multiple_ranges(boundary):
    score = score_query(_kis_query(), [_candidate(0, video_id="V1", frame_idx=boundary)])
    assert score["first_correct_rank"] == 1
    assert all(value == 1 for value in score["metrics"].values())


@pytest.mark.parametrize("rank", [1, 5, 20, 50, 100])
def test_kis_first_correct_rank_and_recall_cutoffs(rank):
    predictions = [_candidate(index) for index in range(rank - 1)]
    predictions.append(_candidate(1000, video_id="V1", frame_idx=15))
    score = score_query(_kis_query(), predictions)
    assert score["first_correct_rank"] == rank
    for cutoff in (1, 5, 20, 50, 100):
        assert score["metrics"][f"r_at_{cutoff}"] == int(rank <= cutoff)


def test_kis_empty_incorrect_and_outside_top_100():
    empty = score_query(_kis_query(), [])
    assert empty["first_correct_rank"] is None
    assert not any(empty["metrics"].values())
    wrong = score_query(_kis_query(), [_candidate(index) for index in range(100)])
    assert not any(wrong["metrics"].values())


def test_prediction_duplicate_cap_and_malformed_fail_closed():
    duplicate = [_candidate(1), _candidate(1)]
    with pytest.raises(EvalContractError, match="trùng lặp"):
        score_query(_kis_query(), duplicate)
    with pytest.raises(EvalContractError, match="tối đa 100"):
        score_query(_kis_query(), [_candidate(index) for index in range(101)])
    with pytest.raises(EvalContractError, match="video_id/frame_idx"):
        score_query(_kis_query(), [{"video_id": "V1", "frame_idx": "10"}])


def test_unlabeled_excluded_and_split_cannot_mix():
    scored = {
        "query_id": "q1", "query_type": "KIS", "trap_category": "visual",
        "split": "dev", "label_status": "labeled", "status": "OK",
        "score": score_query(_kis_query(), [_candidate(0, video_id="V1", frame_idx=15)]),
    }
    unlabeled_query = _kis_query(label_status="unlabeled_reference")
    unlabeled = {
        "query_id": "q2", "query_type": "KIS", "trap_category": "visual",
        "split": "dev", "label_status": "unlabeled_reference", "status": "OK",
        "score": score_query(unlabeled_query, []),
    }
    aggregate = aggregate_scores([scored, unlabeled], split="dev")
    assert aggregate["labeled"] == 1 and aggregate["unlabeled"] == 1
    assert aggregate["metrics"]["r_at_1"] == 1.0
    with pytest.raises(EvalContractError, match="trộn DEV"):
        aggregate_scores([scored, dict(unlabeled, split="holdout")], split="dev")


@pytest.mark.parametrize("query_type", ["QA", "TRAKE"])
def test_qa_and_trake_are_explicitly_blocked(query_type):
    score = score_query(_kis_query(query_type=query_type), [])
    assert score["status"] == "BLOCKED_BY_SCORING_CONTRACT"
    assert score["metrics"] is None


def test_unsupported_query_type_fails_closed():
    with pytest.raises(EvalContractError, match="Không có scorer"):
        score_query(_kis_query(query_type="UNKNOWN"), [])
