from __future__ import annotations

from aic2026.retrieval.providers.base import ProviderHit
from aic2026.retrieval.windowing import WindowPolicy, build_evidence_windows, rank_windows


POLICY = WindowPolicy("retrieval-policy-v1", merge_sec=4.0, max_span_sec=12.0, rrf_k=60)


def _hit(provider: str, evidence_id: str, video_id: str, anchor: float, rank: int, *, score: float = 1.0) -> ProviderHit:
    payload = {"text": evidence_id}
    start = end = anchor
    if provider == "asr":
        start, end = max(0, anchor - 1), anchor + 1
        payload = {"segment_id": evidence_id, "text": evidence_id}
    if provider == "visual":
        ordinal = int(evidence_id.split(":")[-1])
        payload = {"embedding_id": ordinal, "keyframe_id": evidence_id, "csv_n": ordinal, "clip_row": ordinal - 1, "frame_idx": (ordinal - 1) * 25, "pts_time": anchor, "keyframe_relpath": f"keyframes/{video_id}/{ordinal:03d}.jpg"}
    return ProviderHit(provider, evidence_id, video_id, rank, start, end, anchor, score, "cosine_ip_higher_is_better" if provider == "visual" else "bm25_lower_is_better", f"{provider}-v1", payload, f"video/{video_id}.mp4" if provider == "asr" else None, {})


def test_overlap_exact_boundary_cross_video_and_duplicate():
    duplicate = _hit("asr", "A1", "V1", 2, 5)
    windows = build_evidence_windows([
        _hit("visual", "V1:1", "V1", 0, 2),
        _hit("asr", "A1", "V1", 2, 1),
        duplicate,
        _hit("visual", "V1:2", "V1", 4, 3),
        _hit("asr", "B1", "V2", 2, 1),
    ], POLICY)
    assert len(windows) == 2
    v1 = next(window for window in windows if window["video_id"] == "V1")
    assert len(v1["evidence"]) == 3
    assert v1["start_sec"] == 0 and v1["end_sec"] == 4
    assert v1["representative"]["keyframe_id"] == "V1:1"


def test_anti_chain_merge_and_separate_windows():
    hits = [_hit("visual", f"V1:{index + 1}", "V1", float(index * 4), index + 1) for index in range(5)]
    windows = build_evidence_windows(hits, POLICY)
    assert len(windows) == 2
    assert windows[0]["start_sec"] == 0 and windows[0]["end_sec"] == 12
    assert windows[1]["start_sec"] == 16 and windows[1]["end_sec"] == 16


def test_asr_only_visual_only_fused_same_and_fused_separate():
    asr = build_evidence_windows([_hit("asr", "A1", "V1", 5, 1)], POLICY)[0]
    assert asr["representative"]["kind"] == "temporal_anchor"
    assert asr["representative"]["submit_valid"] is False
    assert asr["representative"]["keyframe_id"] is None
    visual = build_evidence_windows([_hit("visual", "V1:1", "V1", 5, 1)], POLICY)[0]
    assert visual["representative"]["submit_valid"] is True
    fused = build_evidence_windows([_hit("visual", "V1:1", "V1", 5, 2), _hit("asr", "A1", "V1", 7, 1)], POLICY)
    assert len(fused) == 1 and set(fused[0]["fusion"]["best_rank_by_lane"]) == {"visual", "asr"}
    separate = build_evidence_windows([_hit("visual", "V1:1", "V1", 0, 1), _hit("asr", "A1", "V1", 5, 1)], POLICY)
    assert len(separate) == 2


def test_rrf_collapses_lane_ignores_raw_scores_and_stable_ties():
    hits = [
        _hit("visual", "V1:1", "V1", 2, 2, score=999),
        _hit("visual", "V1:2", "V1", 3, 8, score=-999),
        _hit("asr", "A1", "V1", 2.5, 1, score=-100),
    ]
    first = build_evidence_windows(hits, POLICY)[0]
    expected = 1 / 62 + 1 / 61
    assert abs(first["fusion"]["rrf_score"] - expected) < 1e-12
    changed = [_hit(hit.provider, hit.evidence_id, hit.video_id, hit.anchor_sec, hit.rank, score=0) for hit in hits]
    assert build_evidence_windows(changed, POLICY)[0]["fusion"]["rrf_score"] == first["fusion"]["rrf_score"]
    ties = build_evidence_windows([_hit("asr", "B", "V2", 1, 1), _hit("asr", "A", "V1", 1, 1)], POLICY)
    assert [item["video_id"] for item in rank_windows(reversed(ties), 100)] == ["V1", "V2"]


def test_window_id_is_deterministic_and_result_limit_enforced():
    hits = [_hit("asr", "A1", "V1", 2, 1), _hit("visual", "V1:1", "V1", 3, 1)]
    first = build_evidence_windows(hits, POLICY)[0]
    second = build_evidence_windows(reversed(hits), POLICY)[0]
    assert first["evidence_window_id"] == second["evidence_window_id"]
    assert len(rank_windows([first, second], 1)) == 1
