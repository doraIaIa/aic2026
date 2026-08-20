"""M6 — Compare Mode & Lane Diagnostics Orchestrator.

Executes multiple independent retrieval lanes for the same search query,
preserves native ranks and raw scores, provides partial-failure isolation,
and computes video-level diagnostic overlap metrics without fusion or normalization.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from aic2026.retrieval.providers import (
    AsrBgeProvider,
    AsrBm25Provider,
    BtcClipProvider,
    BtcObjectsProvider,
    BtcObjectsQuery,
    MediaBm25Provider,
    OcrBgeProvider,
    OcrBm25Provider,
    OcrTrigramProvider,
    QwenBgeProvider,
    QwenBm25Provider,
    QwenStructuredProvider,
    SigLIPProvider,
)
from aic2026.retrieval.providers.base import ProviderHit, ProviderQuery


class LaneStatus(str, Enum):
    OK = "OK"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
    SKIPPED_INVALID_CONFIG = "SKIPPED_INVALID_CONFIG"


class OverallStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


ACCEPTED_FREE_TEXT_LANES = {
    "siglip_custom",
    "siglip",
    "btc_clip",
    "asr_bm25",
    "asr_bge",
    "ocr_bm25",
    "ocr_trigram",
    "ocr_bge",
    "media_bm25",
    "qwen_bm25",
    "qwen_bge",
}

ACCEPTED_STRUCTURED_LANES = {
    "qwen_structured",
    "btc_objects",
}

ALL_ACCEPTED_LANES = ACCEPTED_FREE_TEXT_LANES | ACCEPTED_STRUCTURED_LANES


@dataclass(frozen=True)
class CompareLaneConfig:
    lane: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompareLaneResult:
    lane: str
    status: LaneStatus
    latency_ms: float
    requested_top_k: int
    result_count: int
    results: list[dict[str, Any]]
    score_type: str = "raw"
    score_direction: str = "HIGHER_IS_BETTER"
    error: str | None = None
    warning: str | None = None
    effective_query: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "requested_top_k": self.requested_top_k,
            "result_count": self.result_count,
            "score_type": self.score_type,
            "score_direction": self.score_direction,
            "error": self.error,
            "warning": self.warning,
            "effective_query": self.effective_query,
            "options": self.options,
            "results": self.results,
        }


@dataclass
class CompareDiagnostics:
    video_union_count: int
    video_intersection_count: int
    per_lane_unique_videos: dict[str, int]
    unique_to_lane_videos: dict[str, int]
    pairwise_video_overlap: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_union_count": self.video_union_count,
            "video_intersection_count": self.video_intersection_count,
            "per_lane_unique_videos": self.per_lane_unique_videos,
            "unique_to_lane_videos": self.unique_to_lane_videos,
            "pairwise_video_overlap": self.pairwise_video_overlap,
        }


def compute_video_diagnostics(lane_results: Sequence[CompareLaneResult]) -> CompareDiagnostics:
    """Compute video-level overlap and set algebra diagnostics across executed lanes."""
    executed = [r for r in lane_results if r.status in {LaneStatus.OK, LaneStatus.EMPTY}]
    
    lane_video_sets: dict[str, set[str]] = {}
    for r in executed:
        video_ids = {hit.get("video_id") for hit in r.results if hit.get("video_id")}
        lane_video_sets[r.lane] = video_ids

    per_lane_unique = {lane: len(vids) for lane, vids in lane_video_sets.items()}

    all_vids_union: set[str] = set().union(*lane_video_sets.values()) if lane_video_sets else set()
    
    if lane_video_sets and all(len(vids) > 0 for vids in lane_video_sets.values()):
        all_vids_inter: set[str] = set.intersection(*lane_video_sets.values())
    else:
        all_vids_inter = set()

    # Unique to single lane count
    unique_to_lane: dict[str, int] = {}
    for lane, vids in lane_video_sets.items():
        other_vids = set().union(*(other_v for other_l, other_v in lane_video_sets.items() if other_l != lane)) if len(lane_video_sets) > 1 else set()
        unique_to_lane[lane] = len(vids - other_vids)

    # Pairwise overlap and Jaccard
    pairwise: list[dict[str, Any]] = []
    lanes_list = list(lane_video_sets.keys())
    for i in range(len(lanes_list)):
        for j in range(i + 1, len(lanes_list)):
            l1, l2 = lanes_list[i], lanes_list[j]
            v1, v2 = lane_video_sets[l1], lane_video_sets[l2]
            intersection = v1 & v2
            union = v1 | v2
            jaccard = round(len(intersection) / len(union), 4) if union else 0.0
            pairwise.append({
                "lane_a": l1,
                "lane_b": l2,
                "overlap_count": len(intersection),
                "jaccard": jaccard,
                "union_count": len(union),
            })

    return CompareDiagnostics(
        video_union_count=len(all_vids_union),
        video_intersection_count=len(all_vids_inter),
        per_lane_unique_videos=per_lane_unique,
        unique_to_lane_videos=unique_to_lane,
        pairwise_video_overlap=pairwise,
    )


class CompareOrchestrator:
    """Orchestrates deterministic sequential execution of multiple standalone retrieval lanes."""

    def __init__(self, api_adapter: Any) -> None:
        """Initialize with an AsrSearchApi adapter holding the initialized providers."""
        self.api = api_adapter

    def execute_compare(
        self,
        query: str,
        lanes: list[CompareLaneConfig],
        *,
        top_k: int = 20,
        candidate_video_ids: tuple[str, ...] | None = None,
        query_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute all enabled selected lanes sequentially and gather independent diagnostic results."""
        t_start = time.perf_counter()

        if not lanes:
            return {
                "status": "ERROR",
                "mode": "COMPARE",
                "error": "No retrieval lanes selected for comparison",
            }

        # Filter enabled lanes and deduplicate deterministically
        seen_lanes: set[str] = set()
        enabled_configs: list[CompareLaneConfig] = []
        for l_cfg in lanes:
            if not l_cfg.enabled:
                continue
            normalized_lane = "siglip_custom" if l_cfg.lane == "siglip" else l_cfg.lane
            if normalized_lane in seen_lanes:
                continue
            seen_lanes.add(normalized_lane)
            enabled_configs.append(CompareLaneConfig(lane=normalized_lane, enabled=True, options=l_cfg.options))

        if not enabled_configs:
            return {
                "status": "ERROR",
                "mode": "COMPARE",
                "error": "All selected lanes are disabled",
            }

        lane_results: list[CompareLaneResult] = []

        for cfg in enabled_configs:
            lane_id = cfg.lane
            options = cfg.options or {}

            if lane_id not in ALL_ACCEPTED_LANES:
                lane_results.append(
                    CompareLaneResult(
                        lane=lane_id,
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=f"Unknown or unsupported retrieval lane: {lane_id}",
                    )
                )
                continue

            # Execute single lane with isolation
            result = self._execute_single_lane(
                lane_id=lane_id,
                query_text=query,
                top_k=top_k,
                candidate_video_ids=candidate_video_ids,
                options=options,
                query_id=query_id,
            )
            lane_results.append(result)

        t_end = time.perf_counter()
        total_latency_ms = (t_end - t_start) * 1000

        # Determine overall status
        has_ok = any(r.status in {LaneStatus.OK, LaneStatus.EMPTY} for r in lane_results)
        all_ok = all(r.status in {LaneStatus.OK, LaneStatus.EMPTY} for r in lane_results)

        if all_ok:
            overall_status = OverallStatus.OK
        elif has_ok:
            overall_status = OverallStatus.PARTIAL
        else:
            overall_status = OverallStatus.ERROR

        diagnostics = compute_video_diagnostics(lane_results)

        return {
            "status": overall_status.value,
            "mode": "COMPARE",
            "query": query,
            "query_id": query_id,
            "total_latency_ms": round(total_latency_ms, 2),
            "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
            "lanes": [r.to_dict() for r in lane_results],
            "diagnostics": diagnostics.to_dict(),
        }

    def _execute_single_lane(
        self,
        lane_id: str,
        query_text: str,
        top_k: int,
        candidate_video_ids: tuple[str, ...] | None,
        options: dict[str, Any],
        query_id: str | None,
    ) -> CompareLaneResult:
        """Invoke existing provider pathway without altering rankings, scores, or algorithms."""
        t0 = time.perf_counter()

        try:
            # 1. SigLIP (CUSTOM)
            if lane_id in {"siglip_custom", "siglip"}:
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="siglip_custom",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for SigLIP",
                    )
                status_code, resp = self.api.siglip_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="siglip_custom",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "SigLIP lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="siglip_custom",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="cosine_similarity",
                    score_direction="HIGHER_IS_BETTER",
                    effective_query=query_text,
                )

            # 2. BTC CLIP (BTC)
            if lane_id == "btc_clip":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="btc_clip",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for BTC CLIP",
                    )
                status_code, resp = self.api.btc_clip_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="btc_clip",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "BTC CLIP lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="btc_clip",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="cosine_similarity",
                    score_direction="HIGHER_IS_BETTER",
                    effective_query=query_text,
                )

            # 3. ASR BM25
            if lane_id == "asr_bm25":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="asr_bm25",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for ASR BM25",
                    )
                status_code, resp = self.api.asr_bm25_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="asr_bm25",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "ASR BM25 lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="asr_bm25",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="sqlite_fts5_bm25",
                    score_direction="LOWER_IS_BETTER",
                    effective_query=query_text,
                )

            # 4. ASR BGE
            if lane_id == "asr_bge":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="asr_bge",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for ASR BGE",
                    )
                status_code, resp = self.api.asr_bge_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="asr_bge",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "ASR BGE lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="asr_bge",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="dense_cosine_similarity",
                    score_direction="HIGHER_IS_BETTER",
                    effective_query=query_text,
                )

            # 5. OCR BM25
            if lane_id == "ocr_bm25":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="ocr_bm25",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for OCR BM25",
                    )
                status_code, resp = self.api.ocr_bm25_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="ocr_bm25",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "OCR BM25 lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="ocr_bm25",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="sqlite_fts5_bm25",
                    score_direction="LOWER_IS_BETTER",
                    effective_query=query_text,
                )

            # 6. OCR Trigram
            if lane_id == "ocr_trigram":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="ocr_trigram",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for OCR Trigram",
                    )
                status_code, resp = self.api.ocr_trigram_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="ocr_trigram",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "OCR Trigram lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="ocr_trigram",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="sqlite_fts5_trigram",
                    score_direction="LOWER_IS_BETTER",
                    effective_query=query_text,
                )

            # 7. OCR BGE
            if lane_id == "ocr_bge":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="ocr_bge",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for OCR BGE",
                    )
                status_code, resp = self.api.ocr_bge_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="ocr_bge",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "OCR BGE lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="ocr_bge",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="dense_cosine_similarity",
                    score_direction="HIGHER_IS_BETTER",
                    effective_query=query_text,
                )

            # 8. Media BM25
            if lane_id == "media_bm25":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="media_bm25",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for Media BM25",
                    )
                status_code, resp = self.api.media_bm25_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "author": options.get("author"),
                    "publish_date_from": options.get("publish_date_from"),
                    "publish_date_to": options.get("publish_date_to"),
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="media_bm25",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "Media BM25 lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="media_bm25",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="sqlite_fts5_bm25",
                    score_direction="LOWER_IS_BETTER",
                    effective_query=query_text,
                )

            # 9. Qwen BM25
            if lane_id == "qwen_bm25":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="qwen_bm25",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for Qwen BM25",
                    )
                status_code, resp = self.api.qwen_bm25_search({
                    "query": query_text,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="qwen_bm25",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "Qwen BM25 lane failure"),
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="qwen_bm25",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="sqlite_fts5_bm25",
                    score_direction="LOWER_IS_BETTER",
                    effective_query=query_text,
                )

            # 10. Qwen BGE (with optional field & embedding_query override)
            if lane_id == "qwen_bge":
                if not query_text.strip():
                    return CompareLaneResult(
                        lane="qwen_bge",
                        status=LaneStatus.ERROR,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error="query is required for Qwen BGE",
                    )
                field = options.get("field", "full_text")
                embedding_query = options.get("embedding_query")
                status_code, resp = self.api.qwen_bge_search({
                    "query": query_text,
                    "field": field,
                    "embedding_query": embedding_query,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="qwen_bge",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "Qwen BGE lane failure"),
                        options={"field": field, "embedding_query": embedding_query},
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="qwen_bge",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="dense_cosine_similarity",
                    score_direction="HIGHER_IS_BETTER",
                    effective_query=embedding_query or query_text,
                    options={"field": field, "embedding_query": embedding_query},
                )

            # 11. Qwen Structured (MUST NOT parse natural query; requires explicit facet options)
            if lane_id == "qwen_structured":
                has_facets = any(
                    bool(options.get(k))
                    for k in ["objects", "attributes", "relations", "counts", "scenes", "actions", "query"]
                )
                if not has_facets:
                    return CompareLaneResult(
                        lane="qwen_structured",
                        status=LaneStatus.SKIPPED_INVALID_CONFIG,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        warning="qwen_structured skipped: no structured facets configured in options",
                    )

                status_code, resp = self.api.qwen_structured_search({
                    "objects": options.get("objects"),
                    "attributes": options.get("attributes"),
                    "relations": options.get("relations"),
                    "counts": options.get("counts"),
                    "scenes": options.get("scenes"),
                    "actions": options.get("actions"),
                    "query": options.get("query"),
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                    "query_id": query_id,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="qwen_structured",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "Qwen Structured lane failure"),
                        options=options,
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="qwen_structured",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="structured_facet_match",
                    score_direction="HIGHER_IS_BETTER",
                    options=options,
                )

            # 12. BTC Objects (MUST NOT parse natural query; requires explicit classes list)
            if lane_id == "btc_objects":
                classes = options.get("classes") or []
                if not isinstance(classes, list) or len(classes) == 0:
                    return CompareLaneResult(
                        lane="btc_objects",
                        status=LaneStatus.SKIPPED_INVALID_CONFIG,
                        latency_ms=0.0,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        warning="btc_objects skipped: no detector classes configured in options",
                    )

                match_mode = options.get("match_mode", "ALL")
                min_detector_score = float(options.get("min_detector_score", 0.10))

                status_code, resp = self.api.btc_objects_search({
                    "classes": classes,
                    "match_mode": match_mode,
                    "min_detector_score": min_detector_score,
                    "top_k": top_k,
                    "candidate_video_ids": list(candidate_video_ids) if candidate_video_ids else None,
                })
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if status_code != 200 or resp.get("status") != "OK":
                    return CompareLaneResult(
                        lane="btc_objects",
                        status=LaneStatus.UNAVAILABLE if status_code == 503 else LaneStatus.ERROR,
                        latency_ms=elapsed_ms,
                        requested_top_k=top_k,
                        result_count=0,
                        results=[],
                        error=resp.get("error", "BTC Objects lane failure"),
                        options=options,
                    )
                hits = resp.get("hits", [])
                return CompareLaneResult(
                    lane="btc_objects",
                    status=LaneStatus.OK if hits else LaneStatus.EMPTY,
                    latency_ms=elapsed_ms,
                    requested_top_k=top_k,
                    result_count=len(hits),
                    results=hits,
                    score_type="btc_object_support",
                    score_direction="HIGHER_IS_BETTER",
                    options=options,
                )

            return CompareLaneResult(
                lane=lane_id,
                status=LaneStatus.ERROR,
                latency_ms=0.0,
                requested_top_k=top_k,
                result_count=0,
                results=[],
                error=f"Unhandled lane ID: {lane_id}",
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return CompareLaneResult(
                lane=lane_id,
                status=LaneStatus.ERROR,
                latency_ms=elapsed_ms,
                requested_top_k=top_k,
                result_count=0,
                results=[],
                error=f"{type(exc).__name__}: {exc}",
            )
