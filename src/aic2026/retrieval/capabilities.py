from __future__ import annotations

from pathlib import Path
from typing import Any

from aic2026.retrieval.contract import CONTRACT_VERSION, POLICY_VERSION, DEFAULT_ASR_STRATEGY, ASR_STRATEGIES, media_capability
from aic2026.retrieval.providers.base import ProviderCapability, SearchProvider


class CapabilityService:
    """Báo trạng thái từng lane độc lập; lỗi optional lane không che lane khác."""

    def __init__(self, providers: dict[str, SearchProvider], *, media_root: str | Path | None = None) -> None:
        self.providers = dict(providers)
        self.media_root = media_root

    @staticmethod
    def _unavailable(name: str, reason: str) -> ProviderCapability:
        return ProviderCapability(name, "UNAVAILABLE", reason, None, {}, {}, {})

    def report(self) -> dict[str, Any]:
        states: dict[str, dict[str, Any]] = {}
        for lane in ("asr", "visual"):
            provider = self.providers.get(lane)
            if provider is None:
                state = self._unavailable(lane, f"{lane.upper()}_PROVIDER_NOT_CONFIGURED")
            else:
                try:
                    state = provider.capabilities()
                except Exception as exc:  # provider boundary: không làm process chết
                    state = ProviderCapability(lane, "INTEGRITY_ERROR", f"{type(exc).__name__}: {exc}", None, {}, {}, {})
            states[lane] = state.to_dict()
        states["ocr"] = self._unavailable("ocr", "OCR_ARTIFACT_NOT_AVAILABLE").to_dict()
        states["object"] = self._unavailable("object", "OBJECT_ARTIFACT_NOT_AVAILABLE").to_dict()
        return {
            "contract_version": CONTRACT_VERSION,
            "policy_version": POLICY_VERSION,
            "providers": states,
            "media": media_capability(self.media_root),
            "asr_strategy": {
                "active": getattr(self.providers.get("asr"), "strategy", DEFAULT_ASR_STRATEGY),
                "available": list(ASR_STRATEGIES),
                "default": DEFAULT_ASR_STRATEGY,
            },
        }
