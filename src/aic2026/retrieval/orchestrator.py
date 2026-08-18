from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any

from aic2026.retrieval.contract import CONTRACT_VERSION, POLICY_VERSION, validate_search_request, validate_search_response
from aic2026.retrieval.planner import RulePlanner
from aic2026.retrieval.providers.base import ProviderCapability, ProviderHit, ProviderQuery, SearchProvider
from aic2026.retrieval.windowing import WindowPolicy, build_evidence_windows, rank_windows


@dataclass(frozen=True)
class OrchestratorConfig:
    version: str = "orchestrator-v1"
    per_lane_top_k: int = 100
    provider_timeout_sec: float = 60.0
    max_workers: int = 2

    def __post_init__(self) -> None:
        if not 1 <= self.per_lane_top_k <= 300:
            raise ValueError("per_lane_top_k phải nằm trong 1..300")
        if self.provider_timeout_sec <= 0 or not 1 <= self.max_workers <= 4:
            raise ValueError("timeout/max_workers không hợp lệ")


class SearchOrchestrator:
    """Điều phối provider theo retrieval.v1; chưa chứa mode-specific submission logic."""

    def __init__(self, providers: dict[str, SearchProvider], *, config: OrchestratorConfig | None = None) -> None:
        self.providers = dict(providers)
        self.config = config or OrchestratorConfig()
        self.window_policy = WindowPolicy.authority()
        self.planner = RulePlanner()
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers, thread_name_prefix="retrieval-provider")

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _get_capabilities(self, lanes: set[str]) -> tuple[dict[str, ProviderCapability], list[str], dict[str, float]]:
        futures = {
            self._executor.submit(provider.capabilities): (lane, time.perf_counter())
            for lane, provider in self.providers.items()
            if lane in lanes
        }
        done, pending = wait(futures, timeout=self.config.provider_timeout_sec)
        states: dict[str, ProviderCapability] = {}
        warnings: list[str] = []
        latency_ms: dict[str, float] = {}
        for future in done:
            lane, lane_started = futures[future]
            latency_ms[lane] = (time.perf_counter() - lane_started) * 1000
            try:
                states[lane] = future.result()
            except Exception as exc:
                states[lane] = ProviderCapability(lane, "INTEGRITY_ERROR", f"{type(exc).__name__}: {exc}", None, {}, {}, {})
                warnings.append(f"{lane.upper()}_CAPABILITY_ERROR")
        for future in pending:
            lane, lane_started = futures[future]
            latency_ms[lane] = (time.perf_counter() - lane_started) * 1000
            future.cancel()
            states[lane] = ProviderCapability(lane, "UNAVAILABLE", "CAPABILITY_TIMEOUT", None, {}, {}, {})
            warnings.append(f"{lane.upper()}_CAPABILITY_TIMEOUT")
        return states, warnings, latency_ms

    @staticmethod
    def _provider_state(capability: ProviderCapability, status: str, *, count: int = 0, latency_ms: float | None = None, reason: str | None = None) -> dict[str, Any]:
        return {
            "status": status,
            "reason": reason if reason is not None else capability.reason,
            "artifact_version": capability.version,
            "checksums": capability.checksums,
            "provenance": capability.provenance,
            "count": count,
            "latency_ms": latency_ms,
        }

    def search(self, raw_request: Any) -> dict[str, Any]:
        started = time.perf_counter()
        request = validate_search_request(raw_request)
        strategy = request["routing"]["strategy"]
        capability_lanes = set(self.providers) if strategy == "auto" else set(request["routing"]["enabled_lanes"])
        capabilities, warnings, capability_latency = self._get_capabilities(capability_lanes)
        for lane in ("asr", "visual", "ocr", "object"):
            if lane not in capabilities:
                capabilities[lane] = ProviderCapability(lane, "UNAVAILABLE", f"{lane.upper()}_ARTIFACT_NOT_AVAILABLE", None, {}, {}, {})

        if strategy == "auto":
            selected = [lane for lane in ("visual", "asr", "ocr", "object") if capabilities[lane].status == "OK"]
            plan = self.planner.plan(request["query_text"], tuple(selected))
            route_reason = plan.version
            warnings.extend(f"PLANNER_{code}" for code in plan.reason_codes if code != "BASELINE_ALL_AVAILABLE")
        else:
            selected = list(request["routing"]["enabled_lanes"])
            route_reason = "manual_override_v1"
        active = [lane for lane in selected if lane in self.providers and capabilities[lane].status == "OK"]

        provider_states: dict[str, dict[str, Any]] = {}
        for lane in ("asr", "visual", "ocr", "object"):
            capability = capabilities[lane]
            if strategy == "manual" and lane not in selected:
                provider_states[lane] = self._provider_state(capability, "SKIPPED")
            elif capability.status == "OK" and lane in self.providers:
                provider_states[lane] = self._provider_state(capability, "AVAILABLE")
            elif capability.status == "INTEGRITY_ERROR":
                provider_states[lane] = self._provider_state(capability, "ERROR")
                warnings.append(f"{lane.upper()}_INTEGRITY_ERROR")
            else:
                provider_states[lane] = self._provider_state(capability, "UNAVAILABLE")
                warnings.append(f"{lane.upper()}_UNAVAILABLE")

        query = ProviderQuery(
            request["query_text"],
            top_k=self.config.per_lane_top_k,
            video_ids=tuple(request["filters"]["video_ids"]),
        )
        futures: dict[Future[list[ProviderHit]], tuple[str, float]] = {}
        for lane in active:
            futures[self._executor.submit(self.providers[lane].search, query)] = (lane, time.perf_counter())
        done, pending = wait(futures, timeout=self.config.provider_timeout_sec)
        all_hits: list[ProviderHit] = []
        successful: set[str] = set()
        provider_latency: dict[str, float] = {}
        for future in done:
            lane, lane_started = futures[future]
            latency = (time.perf_counter() - lane_started) * 1000
            provider_latency[lane] = latency
            try:
                hits = future.result()[: self.config.per_lane_top_k]
                all_hits.extend(hits)
                successful.add(lane)
                provider_states[lane] = self._provider_state(capabilities[lane], "AVAILABLE", count=len(hits), latency_ms=latency)
            except Exception as exc:
                provider_states[lane] = self._provider_state(capabilities[lane], "ERROR", latency_ms=latency, reason=f"{type(exc).__name__}: {exc}")
                warnings.append(f"{lane.upper()}_SEARCH_ERROR")
        for future in pending:
            lane, lane_started = futures[future]
            future.cancel()
            latency = (time.perf_counter() - lane_started) * 1000
            provider_latency[lane] = latency
            provider_states[lane] = self._provider_state(capabilities[lane], "ERROR", latency_ms=latency, reason="PROVIDER_TIMEOUT")
            warnings.append(f"{lane.upper()}_TIMEOUT")

        start_filter = request["filters"]["start_sec"]
        end_filter = request["filters"]["end_sec"]
        if start_filter is not None:
            all_hits = [hit for hit in all_hits if hit.anchor_sec >= start_filter]
        if end_filter is not None:
            all_hits = [hit for hit in all_hits if hit.anchor_sec <= end_filter]
        windows = rank_windows(build_evidence_windows(all_hits, self.window_policy), request["result_limit"])

        unsuccessful_selected = [lane for lane in selected if lane not in successful]
        auto_capability_failure = strategy == "auto" and any(
            lane in self.providers
            and (
                capabilities[lane].status == "INTEGRITY_ERROR"
                or capabilities[lane].reason == "CAPABILITY_TIMEOUT"
            )
            for lane in self.providers
        )
        if not successful:
            status = "ERROR"
        elif unsuccessful_selected or auto_capability_failure:
            status = "PARTIAL"
        else:
            status = "OK"
        response = {
            "contract_version": CONTRACT_VERSION,
            "request_id": request["request_id"],
            "status": status,
            "route": {
                "strategy": strategy,
                "reason": route_reason,
                "selected_lanes": selected,
                "executed_lanes": sorted(successful),
                "mode": request["mode"],
                "orchestrator_version": self.config.version,
                "policy_version": POLICY_VERSION,
                "per_lane_top_k": self.config.per_lane_top_k,
            },
            "providers": provider_states,
            "results": windows,
            "latency_ms": {
                "total": (time.perf_counter() - started) * 1000,
                "capabilities": capability_latency,
                "providers": provider_latency,
            },
            "warnings": sorted(set(warnings)),
        }
        return validate_search_response(response)
