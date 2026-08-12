from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from aic2026.retrieval.contract import CONTRACT_VERSION, POLICY_VERSION, load_retrieval_policy
from aic2026.retrieval.providers.base import ProviderHit, ProviderIntegrityError


@dataclass(frozen=True)
class WindowPolicy:
    version: str
    merge_sec: float
    max_span_sec: float
    rrf_k: int

    @classmethod
    def authority(cls) -> "WindowPolicy":
        policy = load_retrieval_policy()
        return cls(
            version=str(policy["policy_version"]),
            merge_sec=float(policy["windowing"]["merge_anchor_distance_sec"]),
            max_span_sec=float(policy["windowing"]["max_window_span_sec"]),
            rrf_k=int(policy["fusion"]["rrf_k"]),
        )


def _validate_hit(hit: ProviderHit) -> None:
    if hit.provider not in {"visual", "asr", "ocr", "object"}:
        raise ProviderIntegrityError("PROVIDER_HIT_MODALITY_INVALID")
    if hit.rank < 1 or hit.start_sec < 0 or hit.end_sec < hit.start_sec:
        raise ProviderIntegrityError("PROVIDER_HIT_RANGE_OR_RANK_INVALID")
    if not hit.start_sec <= hit.anchor_sec <= hit.end_sec:
        raise ProviderIntegrityError("PROVIDER_HIT_ANCHOR_OUTSIDE_RANGE")
    if hit.provider == "visual":
        payload = hit.payload
        try:
            csv_n = int(payload["csv_n"])
            clip_row = int(payload["clip_row"])
            frame_idx = int(payload["frame_idx"])
            keyframe_id = str(payload["keyframe_id"])
            pts_time = float(payload["pts_time"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderIntegrityError("VISUAL_HIT_MAPPING_MISSING") from exc
        if csv_n < 1 or clip_row != csv_n - 1 or frame_idx < 0:
            raise ProviderIntegrityError("VISUAL_HIT_MAPPING_INVALID")
        if keyframe_id != f"{hit.video_id}:{csv_n}" or keyframe_id != hit.evidence_id:
            raise ProviderIntegrityError("VISUAL_HIT_KEYFRAME_ID_INVALID")
        if abs(pts_time - hit.anchor_sec) > 1e-6:
            raise ProviderIntegrityError("VISUAL_HIT_PTS_INVALID")


def deduplicate_hits(hits: Iterable[ProviderHit]) -> list[ProviderHit]:
    selected: dict[tuple[str, str], ProviderHit] = {}
    for hit in hits:
        _validate_hit(hit)
        key = (hit.provider, hit.evidence_id)
        current = selected.get(key)
        candidate_key = (hit.rank, hit.anchor_sec, hit.video_id, hit.evidence_id)
        current_key = (current.rank, current.anchor_sec, current.video_id, current.evidence_id) if current else None
        if current is None or candidate_key < current_key:
            selected[key] = hit
    return sorted(selected.values(), key=lambda hit: (hit.video_id, hit.anchor_sec, hit.provider, hit.rank, hit.evidence_id))


def _bounded_interval(hit: ProviderHit, max_span_sec: float) -> tuple[float, float]:
    if hit.end_sec - hit.start_sec <= max_span_sec:
        return hit.start_sec, hit.end_sec
    half = max_span_sec / 2
    return max(0.0, hit.anchor_sec - half), hit.anchor_sec + half


def _window_id(policy: WindowPolicy, video_id: str, start: float, end: float, hits: list[ProviderHit]) -> str:
    identity = {
        "policy_version": policy.version,
        "video_id": video_id,
        "start_sec": round(start, 6),
        "end_sec": round(end, 6),
        "evidence_ids": sorted(f"{hit.provider}:{hit.evidence_id}" for hit in hits),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return f"ew_{digest}"


def _representative(hits: list[ProviderHit]) -> dict[str, Any]:
    visual = sorted((hit for hit in hits if hit.provider == "visual"), key=lambda hit: (hit.rank, hit.evidence_id))
    if visual:
        hit = visual[0]
        return {
            "kind": "visual_keyframe",
            "timestamp_sec": float(hit.payload["pts_time"]),
            "keyframe_id": str(hit.payload["keyframe_id"]),
            "frame_idx": int(hit.payload["frame_idx"]),
            "submit_valid": True,
            "operator_confirmation_required": True,
        }
    best = min(hits, key=lambda hit: (hit.rank, hit.anchor_sec, hit.provider, hit.evidence_id))
    return {
        "kind": "temporal_anchor",
        "timestamp_sec": best.anchor_sec,
        "keyframe_id": None,
        "frame_idx": None,
        "submit_valid": False,
        "operator_confirmation_required": True,
    }


def _finalize(video_id: str, hits: list[ProviderHit], start: float, end: float, policy: WindowPolicy) -> dict[str, Any]:
    evidence = []
    for hit in sorted(hits, key=lambda item: (item.provider, item.rank, item.evidence_id)):
        evidence.append({
            "modality": hit.provider,
            "evidence_id": hit.evidence_id,
            "rank": hit.rank,
            "raw_score": hit.raw_score,
            "score_kind": hit.score_kind,
            "anchor_sec": hit.anchor_sec,
            "artifact_version": hit.artifact_version,
            "payload": {**hit.payload, "source_start_sec": hit.start_sec, "source_end_sec": hit.end_sec, "provenance": hit.provenance},
        })
    best_rank: dict[str, int] = {}
    for hit in hits:
        best_rank[hit.provider] = min(hit.rank, best_rank.get(hit.provider, hit.rank))
    rrf_score = sum(1.0 / (policy.rrf_k + rank) for rank in best_rank.values())
    representative = _representative(hits)
    video_paths = sorted({hit.source_video_relpath for hit in hits if hit.source_video_relpath})
    if len(video_paths) > 1:
        raise ProviderIntegrityError("WINDOW_SOURCE_VIDEO_PATH_CONFLICT")
    keyframe_relpath = None
    if representative["kind"] == "visual_keyframe":
        chosen = next(hit for hit in hits if hit.provider == "visual" and hit.evidence_id == representative["keyframe_id"])
        keyframe_relpath = chosen.payload.get("keyframe_relpath")
    return {
        "evidence_window_id": _window_id(policy, video_id, start, end, hits),
        "video_id": video_id,
        "start_sec": round(start, 6),
        "end_sec": round(end, 6),
        "representative": representative,
        "evidence": evidence,
        "fusion": {"method": "rrf", "rrf_score": rrf_score, "best_rank_by_lane": dict(sorted(best_rank.items()))},
        "sources": {"video_relpath": video_paths[0] if video_paths else None, "keyframe_relpath": keyframe_relpath, "media_url": None},
        "provenance": {"contract_version": CONTRACT_VERSION, "policy_version": POLICY_VERSION},
    }


def build_evidence_windows(hits: Iterable[ProviderHit], policy: WindowPolicy | None = None) -> list[dict[str, Any]]:
    config = policy or WindowPolicy.authority()
    deduplicated = deduplicate_hits(hits)
    windows: list[dict[str, Any]] = []
    cluster: list[ProviderHit] = []
    cluster_video = ""
    cluster_start = cluster_end = last_anchor = 0.0
    for hit in deduplicated:
        hit_start, hit_end = _bounded_interval(hit, config.max_span_sec)
        can_merge = bool(cluster) and hit.video_id == cluster_video and hit.anchor_sec - last_anchor <= config.merge_sec and max(cluster_end, hit_end) - min(cluster_start, hit_start) <= config.max_span_sec
        if not can_merge:
            if cluster:
                windows.append(_finalize(cluster_video, cluster, cluster_start, cluster_end, config))
            cluster = [hit]
            cluster_video = hit.video_id
            cluster_start, cluster_end, last_anchor = hit_start, hit_end, hit.anchor_sec
        else:
            cluster.append(hit)
            cluster_start = min(cluster_start, hit_start)
            cluster_end = max(cluster_end, hit_end)
            last_anchor = hit.anchor_sec
    if cluster:
        windows.append(_finalize(cluster_video, cluster, cluster_start, cluster_end, config))
    return windows


def rank_windows(windows: Iterable[dict[str, Any]], result_limit: int) -> list[dict[str, Any]]:
    if type(result_limit) is not int or not 1 <= result_limit <= 100:
        raise ValueError("result_limit phải nằm trong 1..100")
    return sorted(
        windows,
        key=lambda window: (
            -float(window["fusion"]["rrf_score"]),
            min(window["fusion"]["best_rank_by_lane"].values()),
            window["video_id"],
            float(window["start_sec"]),
            window["evidence_window_id"],
        ),
    )[:result_limit]
