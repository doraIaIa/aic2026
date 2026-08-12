from __future__ import annotations

from dataclasses import asdict, dataclass, field
import time
from typing import Any, Protocol


PROVIDER_STATUSES = {"OK", "UNAVAILABLE", "INTEGRITY_ERROR", "MEDIA_UNAVAILABLE"}


class ProviderError(RuntimeError):
    """Lỗi provider đã được cô lập ở một lane."""


class ProviderUnavailableError(ProviderError):
    """Provider không thể chạy trong môi trường hiện tại."""


class ProviderIntegrityError(ProviderError):
    """Artifact/provider vi phạm integrity và phải fail closed cho lane."""


@dataclass(frozen=True)
class ProviderQuery:
    query_text: str
    top_k: int = 20
    video_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.query_text, str) or not self.query_text.strip():
            raise ValueError("query_text phải là chuỗi không rỗng")
        if type(self.top_k) is not int or not 1 <= self.top_k <= 100:
            raise ValueError("top_k phải nằm trong 1..100")
        if len(self.video_ids) != len(set(self.video_ids)):
            raise ValueError("video_ids không được trùng")


@dataclass(frozen=True)
class ProviderHit:
    provider: str
    evidence_id: str
    video_id: str
    rank: int
    start_sec: float
    end_sec: float
    anchor_sec: float
    raw_score: float | None
    score_kind: str
    artifact_version: str
    payload: dict[str, Any]
    source_video_relpath: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    status: str
    reason: str | None
    version: str | None
    checksums: dict[str, str]
    provenance: dict[str, Any]
    counts: dict[str, int]

    def __post_init__(self) -> None:
        if self.status not in PROVIDER_STATUSES:
            raise ValueError(f"Provider status không hợp lệ: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderSearchResult:
    provider: str
    hits: list[ProviderHit]
    latency_ms: float


def measure_provider_search(provider: "SearchProvider", query: ProviderQuery) -> ProviderSearchResult:
    started = time.perf_counter()
    hits = provider.search(query)
    return ProviderSearchResult(
        provider=provider.name,
        hits=hits,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


class SearchProvider(Protocol):
    name: str

    def capabilities(self) -> ProviderCapability: ...

    def search(self, query: ProviderQuery) -> list[ProviderHit]: ...
