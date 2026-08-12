from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aic2026.evaluation.contract import EvalContractError


CUTOFFS = (1, 5, 20, 50, 100)
BLOCKED_BY_SCORING_CONTRACT = "BLOCKED_BY_SCORING_CONTRACT"


def validate_predictions(predictions: Any) -> list[dict[str, Any]]:
    if not isinstance(predictions, list):
        raise EvalContractError("predictions phải là một danh sách")
    if len(predictions) > 100:
        raise EvalContractError("Mỗi query chỉ được có tối đa 100 predictions")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for index, item in enumerate(predictions):
        if not isinstance(item, dict):
            raise EvalContractError(f"Prediction rank {index + 1} không phải object")
        video_id = item.get("video_id")
        frame_idx = item.get("frame_idx")
        if not isinstance(video_id, str) or not video_id or type(frame_idx) is not int or frame_idx < 0:
            raise EvalContractError(f"Prediction rank {index + 1} thiếu video_id/frame_idx hợp lệ")
        embedding_id = item.get("embedding_id")
        identity = ("embedding", embedding_id) if embedding_id is not None else ("frame", video_id, frame_idx)
        if identity in seen:
            raise EvalContractError(f"Prediction trùng lặp tại rank {index + 1}")
        seen.add(identity)
        normalized.append(dict(item, rank=index + 1))
    return normalized


def score_kis(query: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = validate_predictions(predictions)
    first_correct_rank = None
    for candidate in candidates:
        if candidate["video_id"] != query["gt_video_id"]:
            continue
        frame_idx = candidate["frame_idx"]
        if any(item["start_frame"] <= frame_idx <= item["end_frame"] for item in query["gt_frame_ranges"]):
            first_correct_rank = candidate["rank"]
            break
    metrics = {
        f"r_at_{cutoff}": int(first_correct_rank is not None and first_correct_rank <= cutoff)
        for cutoff in CUTOFFS
    }
    return {"status": "SCORED", "first_correct_rank": first_correct_rank, "metrics": metrics}


def score_trake(query: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    """TRAKE scorer per BTC spec.

    R-Score = 0 if predicted_video_id != gt_video_id.
    Otherwise: (# events with frame_id in inclusive [s_j, e_j]) / N.
    R@k = max R-Score in first k candidates.
    Final Score = mean(R@1, R@5, R@20, R@50, R@100).
    """
    candidates = validate_predictions(predictions)
    gt_video_id = query.get("gt_video_id")
    gt_events: list[dict[str, Any]] = query.get("gt_events") or []
    n_events = len(gt_events)

    def r_score_for_candidate(candidate: dict[str, Any]) -> float:
        if candidate["video_id"] != gt_video_id:
            return 0.0
        if n_events == 0:
            return 0.0
        matched = sum(
            1
            for event in gt_events
            if event["start_frame"] <= candidate["frame_idx"] <= event["end_frame"]
        )
        return matched / n_events

    # R@k = max R-Score among first k candidates
    metrics: dict[str, float] = {}
    best_r_score = 0.0
    best_rank: int | None = None
    for cutoff in CUTOFFS:
        top_k = candidates[:cutoff]
        r_at_k = max((r_score_for_candidate(c) for c in top_k), default=0.0)
        metrics[f"r_at_{cutoff}"] = r_at_k
        if r_at_k > best_r_score:
            best_r_score = r_at_k

    # Find first candidate with r_score > 0 for first_correct_rank
    for candidate in candidates:
        if r_score_for_candidate(candidate) > 0.0:
            best_rank = candidate["rank"]
            break

    final_score = sum(metrics[f"r_at_{k}"] for k in CUTOFFS) / len(CUTOFFS)
    return {
        "status": "SCORED",
        "first_correct_rank": best_rank,
        "metrics": metrics,
        "trake_final_score": final_score,
    }


def _blocked_scorer(query: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    validate_predictions(predictions)
    return {"status": BLOCKED_BY_SCORING_CONTRACT, "first_correct_rank": None, "metrics": None}


SCORER_REGISTRY: dict[str, Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]]] = {
    "KIS": score_kis,
    "QA": _blocked_scorer,  # QA semantic answer contract not yet defined
    "TRAKE": score_trake,
}


def score_query(query: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = validate_predictions(predictions)
    if query["label_status"] == "unlabeled_reference":
        return {"status": "UNLABELED", "first_correct_rank": None, "metrics": None}
    scorer = SCORER_REGISTRY.get(query["query_type"])
    if scorer is None:
        raise EvalContractError(f"Không có scorer cho query_type={query['query_type']}")
    return scorer(query, candidates)


def aggregate_scores(records: list[dict[str, Any]], *, split: str) -> dict[str, Any]:
    if any(record.get("split") != split for record in records):
        raise EvalContractError("Không được trộn DEV và HOLDOUT trong cùng một aggregate")
    scored = [record for record in records if (record.get("score") or {}).get("status") == "SCORED"]
    labeled = [record for record in records if record.get("label_status") == "labeled"]
    blocked = [
        record for record in records
        if (record.get("score") or {}).get("status") == BLOCKED_BY_SCORING_CONTRACT
    ]
    failed = [record for record in records if record.get("status") == "ERROR"]
    metrics = None
    if scored:
        metrics = {
            f"r_at_{cutoff}": sum(record["score"]["metrics"][f"r_at_{cutoff}"] for record in scored)
            / len(scored)
            for cutoff in CUTOFFS
        }
    first_ranks = [
        record["score"]["first_correct_rank"]
        for record in scored
        if record["score"]["first_correct_rank"] is not None
    ]
    return {
        "split": split,
        "total": len(records),
        "labeled": len(labeled),
        "unlabeled": len(records) - len(labeled),
        "scored": len(scored),
        "blocked_by_scoring_contract": len(blocked),
        "failed": len(failed),
        "metrics": metrics,
        "mean_first_correct_rank": sum(first_ranks) / len(first_ranks) if first_ranks else None,
    }
