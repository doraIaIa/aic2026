import json

import pytest

from aic2026.evaluation.contract import EvalContractError, validate_eval_dataset


def _query(query_id="q1", **overrides):
    query = {
        "query_id": query_id,
        "query_type": "KIS",
        "query_text": "một người đi xe đạp",
        "question_text": None,
        "trap_category": "visual",
        "split": "dev",
        "label_status": "labeled",
        "gt_video_id": "V1",
        "gt_frame_ranges": [{"start_frame": 10, "end_frame": 20}],
        "gt_answer": None,
        "label_provenance": {"source": "synthetic-test"},
    }
    query.update(overrides)
    return query


def _dataset(queries):
    return {"schema_version": 1, "dataset_id": "synthetic", "dataset_version": "v1", "queries": queries}


def test_eval_contract_accepts_labeled_and_unlabeled_queries():
    unlabeled = _query(
        "q2",
        label_status="unlabeled_reference",
        gt_video_id=None,
        gt_frame_ranges=[],
        label_provenance=None,
    )
    normalized, summary = validate_eval_dataset(_dataset([_query(), unlabeled]))
    assert normalized["schema_version"] == 1
    assert summary["labeled"] == 1
    assert summary["unlabeled"] == 1


@pytest.mark.parametrize(
    "bad_range",
    [
        {"start_frame": 20, "end_frame": 10},
        {"start_frame": -1, "end_frame": 10},
        {"start_frame": 1.0, "end_frame": 10},
    ],
)
def test_eval_contract_rejects_invalid_ranges(bad_range):
    with pytest.raises(EvalContractError, match="start_frame"):
        validate_eval_dataset(_dataset([_query(gt_frame_ranges=[bad_range])]))


def test_eval_contract_rejects_duplicate_query_id_and_hidden_unlabeled_gt():
    with pytest.raises(EvalContractError, match="query_id phải duy nhất"):
        validate_eval_dataset(_dataset([_query(), _query()]))
    with pytest.raises(EvalContractError, match="không được chứa ground truth"):
        validate_eval_dataset(_dataset([_query(label_status="unlabeled_reference", label_provenance=None)]))
