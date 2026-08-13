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


def validate_video_predictions(predictions: Any) -> list[dict[str, Any]]:
    if not isinstance(predictions, list):
        raise EvalContractError("predictions phải là một danh sách")
    if len(predictions) > 100:
        raise EvalContractError("Mỗi query chỉ được có tối đa 100 predictions")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(predictions):
        if not isinstance(item, dict):
            raise EvalContractError(f"Prediction rank {index + 1} không phải object")
        video_id = item.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            raise EvalContractError(f"Prediction rank {index + 1} thiếu video_id hợp lệ")
        normalized.append(dict(item, rank=index + 1))
    return normalized


def score_video_retrieval(query: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = validate_video_predictions(predictions)

    status = "UNVERIFIED"
    target_video_id = None

    if query.get("video_verification_status") == "VERIFIED" and query.get("video_label_provenance") == "INTERNAL_MANUAL_VERIFIED":
        target_video_id = query.get("verified_video_id")

    if not target_video_id:
        return {
            "status": status,
            "first_video_rank": None,
            "metrics": {f"video_r_at_{k}": 0 for k in CUTOFFS}
        }

    status = "SCORED"
    first_video_rank = None

    for candidate in candidates:
        if candidate["video_id"] == target_video_id:
            first_video_rank = candidate["rank"]
            break

    metrics = {
        f"video_r_at_{cutoff}": int(first_video_rank is not None and first_video_rank <= cutoff)
        for cutoff in CUTOFFS
    }

    return {
        "status": status,
        "first_video_rank": first_video_rank,
        "metrics": metrics
    }


def score_kis(query: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = validate_predictions(predictions)
    first_correct_rank = None
    for candidate in candidates:
        if candidate["video_id"] != query.get("gt_video_id"):
            continue
        frame_idx = candidate["frame_idx"]
        if query.get("gt_frame_ranges") and any(item["start_frame"] <= frame_idx <= item["end_frame"] for item in query["gt_frame_ranges"]):
            first_correct_rank = candidate["rank"]
            break
    metrics = {
        f"r_at_{cutoff}": int(first_correct_rank is not None and first_correct_rank <= cutoff)
        for cutoff in CUTOFFS
    }
    return {"status": "SCORED", "first_correct_rank": first_correct_rank, "metrics": metrics}


def validate_trake_predictions(predictions: Any, expected_n_events: int) -> list[dict[str, Any]]:
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
        if not isinstance(video_id, str) or not video_id:
            raise EvalContractError(f"Prediction rank {index + 1} thiếu video_id hợp lệ")

        frame_ids = item.get("frame_ids")
        if not isinstance(frame_ids, list) or (not frame_ids and expected_n_events > 0):
            raise EvalContractError(f"Prediction rank {index + 1} thiếu frame_ids hợp lệ")

        if len(frame_ids) != expected_n_events:
            raise EvalContractError(f"Prediction rank {index + 1} có số lượng frame_ids ({len(frame_ids)}) không khớp với số events ({expected_n_events})")

        for f_idx in frame_ids:
            if type(f_idx) is not int or f_idx < 0:
                raise EvalContractError(f"Prediction rank {index + 1} có frame_idx không hợp lệ: {f_idx}")

        # Identity can be video_id + tuple of frame_ids
        identity = ("trake", video_id, tuple(frame_ids))
        if identity in seen:
            raise EvalContractError(f"Prediction trùng lặp tại rank {index + 1}")
        seen.add(identity)
        normalized.append(dict(item, rank=index + 1))
    return normalized


def score_trake(query: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    gt_video_id = query.get("gt_video_id")
    gt_events: list[dict[str, Any]] = query.get("gt_events") or []
    n_events = len(gt_events)

    candidates = validate_trake_predictions(predictions, n_events)

    def r_score_for_candidate(candidate: dict[str, Any]) -> float:
        if candidate["video_id"] != gt_video_id:
            return 0.0
        if n_events == 0:
            return 0.0

        frame_ids = candidate["frame_ids"]
        matched = sum(
            1
            for j in range(n_events)
            if gt_events[j]["start_frame"] <= frame_ids[j] <= gt_events[j]["end_frame"]
        )
        return matched / n_events

    metrics: dict[str, float] = {}
    best_r_score = 0.0
    best_rank: int | None = None
    for cutoff in CUTOFFS:
        top_k = candidates[:cutoff]
        r_at_k = max((r_score_for_candidate(c) for c in top_k), default=0.0)
        metrics[f"r_at_{cutoff}"] = r_at_k
        if r_at_k > best_r_score:
            best_r_score = r_at_k

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
    "QA": _blocked_scorer,
    "TRAKE": score_trake,
}


def score_query(query: dict[str, Any], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    if query.get("label_status") == "unlabeled_reference":
        return {"status": "UNLABELED", "first_correct_rank": None, "metrics": None}
    scorer = SCORER_REGISTRY.get(query["query_type"])
    if scorer is None:
        raise EvalContractError(f"Không có scorer cho query_type={query['query_type']}")
    return scorer(query, predictions)


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


def aggregate_video_scores(records: list[dict[str, Any]], *, split: str) -> dict[str, Any]:
    if any(record.get("split") != split for record in records):
        raise EvalContractError("Không được trộn DEV và HOLDOUT trong cùng một aggregate")

    scored = [record for record in records if (record.get("video_score") or {}).get("status") == "SCORED"]

    metrics = None
    if scored:
        metrics = {
            f"VIDEO_RECALL@{cutoff}": sum(record["video_score"]["metrics"][f"video_r_at_{cutoff}"] for record in scored) / len(scored)
            for cutoff in CUTOFFS
        }

    first_ranks = [
        record["video_score"]["first_video_rank"]
        for record in scored
        if record["video_score"]["first_video_rank"] is not None
    ]

    return {
        "split": split,
        "total": len(records),
        "verified_video_queries": len(scored),
        "metrics": metrics,
        "mean_first_video_rank": sum(first_ranks) / len(first_ranks) if first_ranks else None,
    }
