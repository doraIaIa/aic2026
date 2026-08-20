"""M7 — Manual Temporal Sequence Engine V1.

Enables multi-step temporal sequence retrieval across independent temporal-capable lanes.
Joins evidence by canonical video_id and temporal occurrences with strict order or co-occurrence
constraints, without cross-lane raw-score fusion or automatic query decomposition.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

TEMPORAL_CAPABLE_LANES: Set[str] = {
    "siglip_custom",
    "btc_clip",
    "asr_bm25",
    "asr_bge",
    "ocr_bm25",
    "ocr_trigram",
    "ocr_bge",
    "qwen_bm25",
    "qwen_bge",
    "qwen_structured",
    "btc_objects",
}

EXCLUDED_NON_TEMPORAL_LANES: Set[str] = {
    "media_bm25",
}


class StepStatus(str, Enum):
    OK = "OK"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
    INVALID_CONFIG = "INVALID_CONFIG"
    NO_TEMPORAL_AUTHORITY = "NO_TEMPORAL_AUTHORITY"


class MatchGroup(str, Enum):
    FULL_MATCH = "FULL_MATCH"
    PREFIX_MATCH = "PREFIX_MATCH"
    SUFFIX_MATCH = "SUFFIX_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    STEP_ONLY_MATCH = "STEP_ONLY_MATCH"


class SequenceOverallStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


@dataclass
class StepConfig:
    step_id: str
    lane: str
    query: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, Optional[str]]:
        if not self.step_id or not isinstance(self.step_id, str):
            return False, "step_id must be a non-empty string"
        if not self.lane or not isinstance(self.lane, str):
            return False, "lane must be specified"
        if self.lane in EXCLUDED_NON_TEMPORAL_LANES:
            return False, f"Lane '{self.lane}' has no temporal authority and cannot be used in Sequence"
        if self.lane not in TEMPORAL_CAPABLE_LANES:
            return False, f"Lane '{self.lane}' is not recognized as a temporal-capable lane"

        # Structured lane options checks
        if self.lane == "btc_objects":
            classes = self.options.get("classes") or self.options.get("class")
            if not classes:
                return False, "btc_objects step requires manual 'classes' in options"
        elif self.lane == "qwen_structured":
            has_facets = bool(
                self.options.get("objects")
                or self.options.get("attributes")
                or self.options.get("relations")
                or self.options.get("counts")
                or self.options.get("scenes")
                or self.options.get("actions")
                or self.options.get("facets")
            )
            if not self.query and not has_facets:
                return False, "qwen_structured step requires query or explicit facets in options"
        else:
            if not self.query or not str(self.query).strip():
                return False, f"Step '{self.step_id}' ({self.lane}) requires non-empty query string"

        return True, None


@dataclass
class TemporalOccurrence:
    step_id: str
    step_index: int
    lane: str
    video_id: str
    start_ms: int
    end_ms: int
    anchor_ms: int
    native_rank: int
    native_score: Optional[float]
    score_type: str
    score_direction: str
    evidence_id: str
    raw_hit: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_index": self.step_index,
            "lane": self.lane,
            "video_id": self.video_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "anchor_ms": self.anchor_ms,
            "native_rank": self.native_rank,
            "native_score": self.native_score,
            "score_type": self.score_type,
            "score_direction": self.score_direction,
            "evidence_id": self.evidence_id,
            "raw_hit": self.raw_hit,
        }


@dataclass
class SequenceStepResult:
    step_id: str
    step_index: int
    lane: str
    status: StepStatus
    latency_ms: float
    requested_top_k: int
    result_count: int
    error: Optional[str] = None
    warning: Optional[str] = None
    occurrences: list[TemporalOccurrence] = field(default_factory=list)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_index": self.step_index,
            "lane": self.lane,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "requested_top_k": self.requested_top_k,
            "result_count": self.result_count,
            "error": self.error,
            "warning": self.warning,
        }


@dataclass
class SequenceChain:
    chain_id: str
    video_id: str
    group: MatchGroup
    matched_step_ids: list[str]
    matched_step_indices: list[int]
    total_steps: int
    matched_step_count: int
    occurrences: list[TemporalOccurrence]
    consecutive_gaps_ms: list[int]
    total_span_ms: int
    sum_native_ranks: int
    worst_native_rank: int
    min_start_ms: int
    max_end_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "video_id": self.video_id,
            "group": self.group.value,
            "matched_step_ids": self.matched_step_ids,
            "matched_step_indices": self.matched_step_indices,
            "total_steps": self.total_steps,
            "matched_step_count": self.matched_step_count,
            "consecutive_gaps_ms": self.consecutive_gaps_ms,
            "total_span_ms": self.total_span_ms,
            "sum_native_ranks": self.sum_native_ranks,
            "worst_native_rank": self.worst_native_rank,
            "min_start_ms": self.min_start_ms,
            "max_end_ms": self.max_end_ms,
            "occurrences": [occ.to_dict() for occ in self.occurrences],
        }


@dataclass
class SequenceDiagnostics:
    videos_considered: int
    videos_with_multi_step_evidence: int
    order_violations: int
    gap_too_small_violations: int
    gap_too_large_violations: int
    span_violations: int
    chains_evaluated: int
    chains_emitted: int
    failure_reasons: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "videos_considered": self.videos_considered,
            "videos_with_multi_step_evidence": self.videos_with_multi_step_evidence,
            "order_violations": self.order_violations,
            "gap_too_small_violations": self.gap_too_small_violations,
            "gap_too_large_violations": self.gap_too_large_violations,
            "span_violations": self.span_violations,
            "chains_evaluated": self.chains_evaluated,
            "chains_emitted": self.chains_emitted,
            "failure_reasons": self.failure_reasons,
        }


@dataclass
class SequenceResponse:
    mode: str = "SEQUENCE"
    status: SequenceOverallStatus = SequenceOverallStatus.OK
    total_steps: int = 0
    total_latency_ms: float = 0.0
    steps: list[SequenceStepResult] = field(default_factory=list)
    groups: dict[str, list[SequenceChain]] = field(default_factory=dict)
    diagnostics: SequenceDiagnostics = field(default_factory=lambda: SequenceDiagnostics(0, 0, 0, 0, 0, 0, 0, 0))
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status.value,
            "total_steps": self.total_steps,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "steps": [s.to_summary_dict() for s in self.steps],
            "groups": {
                g: [c.to_dict() for c in chains]
                for g, chains in self.groups.items()
            },
            "diagnostics": self.diagnostics.to_dict(),
            "error": self.error,
        }


def extract_temporal_occurrence(
    step_id: str,
    step_index: int,
    lane: str,
    raw_hit: dict[str, Any],
) -> Optional[TemporalOccurrence]:
    """Converts a native provider hit dict to a standardized TemporalOccurrence."""
    video_id = raw_hit.get("video_id")
    if not video_id:
        return None

    native_rank = int(raw_hit.get("rank") or 1)
    native_score = raw_hit.get("score")
    if native_score is None:
        native_score = raw_hit.get("raw_score")
    score_type = str(raw_hit.get("score_type") or raw_hit.get("score_kind") or "native")
    score_direction = str(raw_hit.get("score_direction") or "HIGHER_IS_BETTER")
    evidence_id = str(raw_hit.get("evidence_id") or f"{video_id}_{native_rank}")

    payload = raw_hit.get("payload") or {}

    # 1. Segment Interval Evidence (ASR)
    if lane in ("asr_bm25", "asr_bge"):
        start_sec = raw_hit.get("start_sec")
        if start_sec is None:
            start_sec = raw_hit.get("start_time")
        if start_sec is None and "start_ms" in payload:
            start_sec = payload["start_ms"] / 1000.0
        if start_sec is None:
            start_sec = raw_hit.get("anchor_sec", 0.0)

        end_sec = raw_hit.get("end_sec")
        if end_sec is None:
            end_sec = raw_hit.get("end_time")
        if end_sec is None and "end_ms" in payload:
            end_sec = payload["end_ms"] / 1000.0
        if end_sec is None:
            end_sec = start_sec

        start_ms = max(0, int(round(float(start_sec) * 1000)))
        end_ms = max(start_ms, int(round(float(end_sec) * 1000)))
        anchor_ms = int(round((start_ms + end_ms) / 2))

    # 2. Point Frame / OCR Item Evidence
    else:
        pts_time = raw_hit.get("pts_time")
        if pts_time is None:
            pts_time = raw_hit.get("timestamp_sec")
        if pts_time is None:
            pts_time = raw_hit.get("anchor_sec")
        if pts_time is None:
            pts_time = raw_hit.get("start_sec")
        if pts_time is None:
            pts_time = raw_hit.get("start_time")
        if pts_time is None and "pts_time" in payload:
            pts_time = payload["pts_time"]
        if pts_time is None:
            pts_time = 0.0

        anchor_ms = max(0, int(round(float(pts_time) * 1000)))
        start_ms = anchor_ms
        end_ms = anchor_ms

    return TemporalOccurrence(
        step_id=step_id,
        step_index=step_index,
        lane=lane,
        video_id=str(video_id),
        start_ms=start_ms,
        end_ms=end_ms,
        anchor_ms=anchor_ms,
        native_rank=native_rank,
        native_score=float(native_score) if native_score is not None else None,
        score_type=score_type,
        score_direction=score_direction,
        evidence_id=evidence_id,
        raw_hit=raw_hit,
    )


def deduplicate_dense_occurrences(
    occurrences: list[TemporalOccurrence],
    dedup_window_ms: int = 1000,
) -> list[TemporalOccurrence]:
    """Lightweight temporal deduplication for dense shot frames in the same step & video.
    Retains the occurrence with best (lowest) native_rank within dedup_window_ms.
    """
    if len(occurrences) <= 1:
        return occurrences

    # Sort by start_ms, then native_rank
    sorted_occs = sorted(occurrences, key=lambda o: (o.start_ms, o.native_rank))
    deduped: list[TemporalOccurrence] = []

    current_cluster: list[TemporalOccurrence] = [sorted_occs[0]]

    for occ in sorted_occs[1:]:
        last_occ = current_cluster[-1]
        if occ.start_ms - last_occ.start_ms <= dedup_window_ms:
            current_cluster.append(occ)
        else:
            # Pick best rank representative in cluster
            best_rep = min(current_cluster, key=lambda o: o.native_rank)
            deduped.append(best_rep)
            current_cluster = [occ]

    if current_cluster:
        best_rep = min(current_cluster, key=lambda o: o.native_rank)
        deduped.append(best_rep)

    return deduped


def classify_chain_group(
    matched_indices: list[int],
    total_steps: int,
) -> MatchGroup:
    """Classifies matched step indices into FULL, PREFIX, SUFFIX, PARTIAL, or STEP_ONLY."""
    m = len(matched_indices)
    if m == total_steps:
        return MatchGroup.FULL_MATCH
    if m == 1:
        return MatchGroup.STEP_ONLY_MATCH

    # Check if indices form a consecutive sequence
    is_consecutive = all(
        matched_indices[i] + 1 == matched_indices[i + 1]
        for i in range(m - 1)
    )

    if is_consecutive:
        if matched_indices[0] == 0:
            return MatchGroup.PREFIX_MATCH
        if matched_indices[-1] == total_steps - 1:
            return MatchGroup.SUFFIX_MATCH
        return MatchGroup.PARTIAL_MATCH

    return MatchGroup.PARTIAL_MATCH


def rank_chains(chains: list[SequenceChain]) -> list[SequenceChain]:
    """Deterministic lexicographical ranking within match groups:
    1. matched_step_count DESC
    2. sum_native_ranks ASC
    3. worst_native_rank ASC
    4. total_span_ms ASC
    5. total_consecutive_gap_ms ASC
    6. video_id ASC
    7. min_start_ms ASC
    8. chain_id ASC
    """
    return sorted(
        chains,
        key=lambda c: (
            -c.matched_step_count,
            c.sum_native_ranks,
            c.worst_native_rank,
            c.total_span_ms,
            sum(c.consecutive_gaps_ms),
            c.video_id,
            c.min_start_ms,
            c.chain_id,
        ),
    )


class SequenceOrchestrator:
    """Executes multi-step temporal sequence retrieval and performs bounded temporal joins."""

    def __init__(self, api_adapter: Any):
        self.api = api_adapter

    def _dispatch_step(self, step_cfg: StepConfig, top_k: int, candidate_video_ids: Optional[list[str]] = None) -> tuple[StepStatus, float, list[dict[str, Any]], Optional[str], Optional[str]]:
        t0 = time.perf_counter()
        req: dict[str, Any] = {
            "top_k": top_k,
            "query": step_cfg.query,
            "q": step_cfg.query,
            "candidate_video_ids": candidate_video_ids,
        }

        # Merge lane-specific options
        req.update(step_cfg.options)

        lane = step_cfg.lane
        status_code = 500
        data: dict[str, Any] = {}

        try:
            if lane == "siglip_custom":
                status_code, data = self.api.siglip_search(req)
            elif lane == "btc_clip":
                status_code, data = self.api.btc_clip_search(req)
            elif lane == "asr_bm25":
                status_code, data = self.api.asr_bm25_search(req)
            elif lane == "asr_bge":
                status_code, data = self.api.asr_bge_search(req)
            elif lane == "ocr_bm25":
                status_code, data = self.api.ocr_bm25_search(req)
            elif lane == "ocr_trigram":
                status_code, data = self.api.ocr_trigram_search(req)
            elif lane == "ocr_bge":
                status_code, data = self.api.ocr_bge_search(req)
            elif lane == "qwen_bm25":
                status_code, data = self.api.qwen_bm25_search(req)
            elif lane == "qwen_bge":
                status_code, data = self.api.qwen_bge_search(req)
            elif lane == "qwen_structured":
                status_code, data = self.api.qwen_structured_search(req)
            elif lane == "btc_objects":
                status_code, data = self.api.btc_objects_search(req)
            else:
                return StepStatus.NO_TEMPORAL_AUTHORITY, 0.0, [], f"Unsupported lane '{lane}'", None
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.exception("Error executing sequence step %s on lane %s", step_cfg.step_id, lane)
            return StepStatus.ERROR, elapsed_ms, [], str(e), None

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if status_code == 200:
            hits = data.get("hits") or data.get("results") or []
            if not hits:
                return StepStatus.EMPTY, elapsed_ms, [], None, None
            return StepStatus.OK, elapsed_ms, hits, None, None
        elif status_code == 503:
            return StepStatus.UNAVAILABLE, elapsed_ms, [], data.get("error", "Lane unavailable"), None
        elif status_code == 400:
            return StepStatus.INVALID_CONFIG, elapsed_ms, [], data.get("error", "Invalid step configuration"), None
        else:
            return StepStatus.ERROR, elapsed_ms, [], data.get("error", f"HTTP {status_code}"), None

    def execute_sequence(
        self,
        steps: list[StepConfig],
        top_k_per_step: int = 50,
        strict_order: bool = True,
        min_gap_ms: int = 0,
        max_gap_ms: int = 60000,
        max_span_ms: Optional[int] = None,
        candidate_video_ids: Optional[list[str]] = None,
        max_chains_per_group: int = 50,
        max_chains_per_video: int = 5,
    ) -> SequenceResponse:
        """Executes independent retrieval per step, extracts temporal occurrences,
        and performs bounded temporal join into match groups.
        """
        total_t0 = time.perf_counter()
        total_steps = len(steps)

        # 1. Validate step counts
        if total_steps < 2:
            return SequenceResponse(
                status=SequenceOverallStatus.ERROR,
                total_steps=total_steps,
                error="Sequence requires at least 2 steps (got %d)" % total_steps,
            )
        if total_steps > 5:
            return SequenceResponse(
                status=SequenceOverallStatus.ERROR,
                total_steps=total_steps,
                error="Sequence supports at most 5 steps in V1 (got %d)" % total_steps,
            )

        # 2. Validate gap boundaries
        if min_gap_ms < 0:
            return SequenceResponse(
                status=SequenceOverallStatus.ERROR,
                total_steps=total_steps,
                error="min_gap_ms cannot be negative (got %d)" % min_gap_ms,
            )
        if max_gap_ms < min_gap_ms:
            return SequenceResponse(
                status=SequenceOverallStatus.ERROR,
                total_steps=total_steps,
                error="max_gap_ms (%d) cannot be less than min_gap_ms (%d)" % (max_gap_ms, min_gap_ms),
            )
        if max_span_ms is not None and max_span_ms <= 0:
            return SequenceResponse(
                status=SequenceOverallStatus.ERROR,
                total_steps=total_steps,
                error="max_span_ms must be positive if specified",
            )

        # 3. Validate each step config
        step_results: list[SequenceStepResult] = []
        has_errors = False
        has_success = False

        for idx, step_cfg in enumerate(steps):
            is_valid, err = step_cfg.validate()
            if not is_valid:
                step_results.append(
                    SequenceStepResult(
                        step_id=step_cfg.step_id,
                        step_index=idx,
                        lane=step_cfg.lane,
                        status=StepStatus.INVALID_CONFIG,
                        latency_ms=0.0,
                        requested_top_k=top_k_per_step,
                        result_count=0,
                        error=err,
                    )
                )
                has_errors = True
                continue

            status, latency_ms, hits, error_msg, warn_msg = self._dispatch_step(
                step_cfg=step_cfg,
                top_k=top_k_per_step,
                candidate_video_ids=candidate_video_ids,
            )

            occurrences: list[TemporalOccurrence] = []
            if status == StepStatus.OK:
                has_success = True
                for h in hits:
                    occ = extract_temporal_occurrence(
                        step_id=step_cfg.step_id,
                        step_index=idx,
                        lane=step_cfg.lane,
                        raw_hit=h,
                    )
                    if occ:
                        occurrences.append(occ)

            if status in (StepStatus.ERROR, StepStatus.UNAVAILABLE, StepStatus.INVALID_CONFIG):
                has_errors = True

            step_results.append(
                SequenceStepResult(
                    step_id=step_cfg.step_id,
                    step_index=idx,
                    lane=step_cfg.lane,
                    status=status,
                    latency_ms=latency_ms,
                    requested_top_k=top_k_per_step,
                    result_count=len(occurrences),
                    error=error_msg,
                    warning=warn_msg,
                    occurrences=occurrences,
                )
            )

        # 4. Group occurrences by video_id
        video_to_step_occs: dict[str, dict[int, list[TemporalOccurrence]]] = {}
        for s_res in step_results:
            for occ in s_res.occurrences:
                v_dict = video_to_step_occs.setdefault(occ.video_id, {})
                v_dict.setdefault(occ.step_index, []).append(occ)

        # 5. Temporal Join Engine
        diag = SequenceDiagnostics(
            videos_considered=len(video_to_step_occs),
            videos_with_multi_step_evidence=0,
            order_violations=0,
            gap_too_small_violations=0,
            gap_too_large_violations=0,
            span_violations=0,
            chains_evaluated=0,
            chains_emitted=0,
        )

        all_grouped_chains: dict[MatchGroup, list[SequenceChain]] = {
            MatchGroup.FULL_MATCH: [],
            MatchGroup.PREFIX_MATCH: [],
            MatchGroup.SUFFIX_MATCH: [],
            MatchGroup.PARTIAL_MATCH: [],
            MatchGroup.STEP_ONLY_MATCH: [],
        }

        chain_counter = 0

        for video_id, step_map in video_to_step_occs.items():
            matched_step_indices = sorted(step_map.keys())
            num_steps_present = len(matched_step_indices)

            if num_steps_present > 1:
                diag.videos_with_multi_step_evidence += 1

            # Deduplicate dense occurrences per step for matching
            clean_step_map: dict[int, list[TemporalOccurrence]] = {
                s_idx: deduplicate_dense_occurrences(occs)
                for s_idx, occs in step_map.items()
            }

            video_chains: list[SequenceChain] = []

            # -------------------------------------------------------------
            # Subsequence Search (from length N down to 1)
            # -------------------------------------------------------------
            # Generate all valid non-empty combinations of step indices
            import itertools

            # Evaluate longer combinations first to avoid redundant subsumption
            all_combos: list[tuple[int, ...]] = []
            for r in range(num_steps_present, 0, -1):
                for combo in itertools.combinations(matched_step_indices, r):
                    all_combos.append(combo)

            video_chains_for_combo: list[SequenceChain] = []

            for combo in all_combos:
                if len(video_chains_for_combo) >= max_chains_per_video:
                    break

                # If this is a 1-step combo and we ALREADY found multi-step chains (len >= 2) for this video, skip 1-step combo
                if len(combo) == 1 and any(c.matched_step_count >= 2 for c in video_chains_for_combo):
                    continue

                combo_steps = list(combo)
                # Find occurrences chains for this combination of steps
                candidate_lists = [clean_step_map[s_idx] for s_idx in combo_steps]

                # Bounded chain search across candidate_lists
                def build_chains(current_chain: list[TemporalOccurrence], depth: int):
                    nonlocal chain_counter
                    if len(video_chains_for_combo) >= max_chains_per_video:
                        return

                    if depth == len(candidate_lists):
                        # Chain completed! Validate span
                        min_start = min(o.start_ms for o in current_chain)
                        max_end = max(o.end_ms for o in current_chain)
                        span = max_end - min_start

                        if max_span_ms is not None and span > max_span_ms:
                            diag.span_violations += 1
                            diag.failure_reasons["MAX_SPAN_VIOLATION"] = diag.failure_reasons.get("MAX_SPAN_VIOLATION", 0) + 1
                            return

                        # Calculate consecutive gaps
                        gaps: list[int] = []
                        for i in range(len(current_chain) - 1):
                            gap = current_chain[i + 1].start_ms - current_chain[i].end_ms
                            gaps.append(gap)

                        group = classify_chain_group(
                            matched_indices=[o.step_index for o in current_chain],
                            total_steps=total_steps,
                        )

                        chain_counter += 1
                        seq_chain = SequenceChain(
                            chain_id=f"seq_{video_id}_{chain_counter}",
                            video_id=video_id,
                            group=group,
                            matched_step_ids=[o.step_id for o in current_chain],
                            matched_step_indices=[o.step_index for o in current_chain],
                            total_steps=total_steps,
                            matched_step_count=len(current_chain),
                            occurrences=list(current_chain),
                            consecutive_gaps_ms=gaps,
                            total_span_ms=span,
                            sum_native_ranks=sum(o.native_rank for o in current_chain),
                            worst_native_rank=max(o.native_rank for o in current_chain),
                            min_start_ms=min_start,
                            max_end_ms=max_end,
                        )
                        video_chains_for_combo.append(seq_chain)
                        return

                    # Branch to next occurrence in candidate_lists[depth]
                    next_occs = candidate_lists[depth]
                    for occ in next_occs:
                        diag.chains_evaluated += 1
                        if not current_chain:
                            build_chains([occ], depth + 1)
                        else:
                            last_occ = current_chain[-1]
                            if strict_order:
                                if occ.start_ms < last_occ.end_ms:
                                    diag.order_violations += 1
                                    diag.failure_reasons["ORDER_VIOLATION"] = diag.failure_reasons.get("ORDER_VIOLATION", 0) + 1
                                    continue
                                gap = occ.start_ms - last_occ.end_ms
                                if gap < min_gap_ms:
                                    diag.gap_too_small_violations += 1
                                    diag.failure_reasons["GAP_TOO_SMALL"] = diag.failure_reasons.get("GAP_TOO_SMALL", 0) + 1
                                    continue
                                if gap > max_gap_ms:
                                    diag.gap_too_large_violations += 1
                                    diag.failure_reasons["GAP_TOO_LARGE"] = diag.failure_reasons.get("GAP_TOO_LARGE", 0) + 1
                                    continue

                            # Check running span
                            cur_min = min(min(o.start_ms for o in current_chain), occ.start_ms)
                            cur_max = max(max(o.end_ms for o in current_chain), occ.end_ms)
                            if max_span_ms is not None and (cur_max - cur_min) > max_span_ms:
                                diag.span_violations += 1
                                continue

                            current_chain.append(occ)
                            build_chains(current_chain, depth + 1)
                            current_chain.pop()

                build_chains([], 0)

            # Keep top chains for this video
            for c in video_chains_for_combo[:max_chains_per_video]:
                all_grouped_chains[c.group].append(c)

        # 6. Rank chains within each group and apply group limits
        total_emitted = 0
        ranked_groups: dict[str, list[SequenceChain]] = {}

        for grp_enum in (
            MatchGroup.FULL_MATCH,
            MatchGroup.PREFIX_MATCH,
            MatchGroup.SUFFIX_MATCH,
            MatchGroup.PARTIAL_MATCH,
            MatchGroup.STEP_ONLY_MATCH,
        ):
            raw_list = all_grouped_chains[grp_enum]
            ranked = rank_chains(raw_list)[:max_chains_per_group]
            ranked_groups[grp_enum.value] = ranked
            total_emitted += len(ranked)

        diag.chains_emitted = total_emitted

        # 7. Compute overall status
        if has_errors and not has_success:
            overall_status = SequenceOverallStatus.ERROR
        elif has_errors or (diag.chains_emitted == 0 and has_success):
            overall_status = SequenceOverallStatus.PARTIAL
        else:
            overall_status = SequenceOverallStatus.OK

        total_elapsed = (time.perf_counter() - total_t0) * 1000

        return SequenceResponse(
            mode="SEQUENCE",
            status=overall_status,
            total_steps=total_steps,
            total_latency_ms=total_elapsed,
            steps=step_results,
            groups=ranked_groups,
            diagnostics=diag,
        )
