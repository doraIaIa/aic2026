from __future__ import annotations

import argparse
import json
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from aic2026.core.config import load_config
from aic2026.core.paths import PathResolver
from aic2026.media.api_handler import write_stream_response
from aic2026.media.resolver import MediaResolver
from aic2026.retrieval.capabilities import CapabilityService
from aic2026.retrieval.contract import RetrievalContractError
from aic2026.retrieval.orchestrator import SearchOrchestrator
from aic2026.retrieval.providers import (
    AsrBgeProvider,
    AsrBm25Provider,
    AsrProvider,
    BtcClipProvider,
    MediaBm25Provider,
    ObjectProvider,
    OcrBgeProvider,
    OcrBm25Provider,
    OcrTrigramProvider,
    QwenStructuredProvider,
    QwenBm25Provider,
    QwenBgeProvider,
    SigLIPProvider,
    VisualProvider,
)
from aic2026.retrieval.providers.base import ProviderQuery
from aic2026.search.asr import AsrSearchError, search_asr
from aic2026.workspace import WorkspaceError, WorkspaceStore


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class AsrSearchApi:
    """Thin HTTP adapter around canonical search implementations and lane providers."""

    def __init__(
        self,
        database: str | Path,
        capability_service: CapabilityService | None = None,
        orchestrator: SearchOrchestrator | None = None,
        media_resolver: MediaResolver | None = None,
        siglip_provider: SigLIPProvider | None = None,
        btc_clip_provider: BtcClipProvider | None = None,
        asr_bm25_provider: AsrBm25Provider | None = None,
        asr_bge_provider: AsrBgeProvider | None = None,
        ocr_bm25_provider: OcrBm25Provider | None = None,
        ocr_trigram_provider: OcrTrigramProvider | None = None,
        ocr_bge_provider: OcrBgeProvider | None = None,
        media_bm25_provider: MediaBm25Provider | None = None,
        qwen_structured_provider: QwenStructuredProvider | None = None,
        qwen_bm25_provider: QwenBm25Provider | None = None,
        qwen_bge_provider: QwenBgeProvider | None = None,
    ) -> None:
        self.database = Path(database)
        self.capability_service = capability_service or CapabilityService(
            {"asr": AsrProvider(self.database)}
        )
        self.orchestrator = orchestrator or SearchOrchestrator(self.capability_service.providers)
        self.media_resolver = media_resolver
        self.siglip_provider = siglip_provider
        self.btc_clip_provider = btc_clip_provider
        self.asr_bm25_provider = asr_bm25_provider
        self.asr_bge_provider = asr_bge_provider
        self.ocr_bm25_provider = ocr_bm25_provider
        self.ocr_trigram_provider = ocr_trigram_provider
        self.ocr_bge_provider = ocr_bge_provider
        self.media_bm25_provider = media_bm25_provider
        self.qwen_structured_provider = qwen_structured_provider
        self.qwen_bm25_provider = qwen_bm25_provider
        self.qwen_bge_provider = qwen_bge_provider
        self.workspace = WorkspaceStore(self.database)

    def close(self) -> None:
        """Close provider and workspace database connections."""
        for p in [
            self.asr_bm25_provider,
            self.ocr_bm25_provider,
            self.ocr_trigram_provider,
            self.media_bm25_provider,
            self.qwen_structured_provider,
            self.qwen_bm25_provider,
        ]:
            if p is not None and hasattr(p, "close"):
                try:
                    p.close()
                except Exception:
                    pass
        if hasattr(self.workspace, "close"):
            try:
                self.workspace.close()
            except Exception:
                pass





    def siglip_health(self) -> tuple[int, dict[str, Any]]:
        if self.siglip_provider is None:
            # Try loading default location
            default_index_dir = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\siglip_custom_v1")
            if default_index_dir.exists():
                self.siglip_provider = SigLIPProvider(default_index_dir)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "siglip_custom",
                    "status": "UNAVAILABLE",
                    "error": "SigLIP index directory not found",
                }
        h = self.siglip_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def siglip_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.siglip_provider is None:
            default_index_dir = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\siglip_custom_v1")
            if default_index_dir.exists():
                self.siglip_provider = SigLIPProvider(default_index_dir)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "status": "ERROR",
                    "error": "SigLIP index directory not found",
                }
        query_text = request.get("query") or request.get("query_text") or ""
        if not isinstance(query_text, str) or not query_text.strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query is required"}
        top_k = int(request.get("top_k", 20))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        query = ProviderQuery(query_text=query_text, top_k=top_k, video_ids=video_ids)
        t0 = time.perf_counter()
        hits = self.siglip_provider.search(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "siglip_custom",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def btc_clip_health(self) -> tuple[int, dict[str, Any]]:
        if self.btc_clip_provider is None:
            default_artifact_dir = Path(r"F:\AIC_WORK\artifacts\m1\clip-faiss-btc-v1")
            if default_artifact_dir.exists():
                self.btc_clip_provider = BtcClipProvider(default_artifact_dir)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "btc_clip",
                    "status": "UNAVAILABLE",
                    "error": "BTC CLIP artifact directory not found",
                }
        h = self.btc_clip_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def btc_clip_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.btc_clip_provider is None:
            default_artifact_dir = Path(r"F:\AIC_WORK\artifacts\m1\clip-faiss-btc-v1")
            if default_artifact_dir.exists():
                self.btc_clip_provider = BtcClipProvider(default_artifact_dir)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "status": "ERROR",
                    "error": "BTC CLIP artifact directory not found",
                }
        query_text = request.get("query") or request.get("query_text") or ""
        if not isinstance(query_text, str) or not query_text.strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query is required"}
        top_k = int(request.get("top_k", 20))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        query = ProviderQuery(query_text=query_text, top_k=top_k, video_ids=video_ids)
        t0 = time.perf_counter()
        hits = self.btc_clip_provider.search(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "btc_clip",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def asr_bm25_health(self) -> tuple[int, dict[str, Any]]:
        if self.asr_bm25_provider is None:
            if self.database.exists():
                self.asr_bm25_provider = AsrBm25Provider(self.database)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "asr_bm25",
                    "status": "UNAVAILABLE",
                    "error": f"Database not found at {self.database}",
                }
        h = self.asr_bm25_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def asr_bm25_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.asr_bm25_provider is None:
            if self.database.exists():
                self.asr_bm25_provider = AsrBm25Provider(self.database)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "status": "ERROR",
                    "error": f"Database not found at {self.database}",
                }
        query_text = request.get("query") or request.get("query_text") or ""
        if not isinstance(query_text, str) or not query_text.strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query is required"}
        top_k = int(request.get("top_k", 20))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        query = ProviderQuery(query_text=query_text, top_k=top_k, video_ids=video_ids)
        t0 = time.perf_counter()
        hits = self.asr_bm25_provider.search(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "asr_bm25",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def asr_bge_health(self) -> tuple[int, dict[str, Any]]:
        if self.asr_bge_provider is None:
            default_artifact_dir = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\asr_bge_v1")
            if default_artifact_dir.exists():
                self.asr_bge_provider = AsrBgeProvider(default_artifact_dir)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "asr_bge",
                    "status": "UNAVAILABLE",
                    "error": "ASR BGE artifact directory not found",
                }
        h = self.asr_bge_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def asr_bge_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.asr_bge_provider is None:
            default_artifact_dir = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\asr_bge_v1")
            if default_artifact_dir.exists():
                self.asr_bge_provider = AsrBgeProvider(default_artifact_dir)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "status": "ERROR",
                    "error": "ASR BGE artifact directory not found",
                }
        query_text = request.get("query") or request.get("query_text") or ""
        if not isinstance(query_text, str) or not query_text.strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query is required"}
        top_k = int(request.get("top_k", 20))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        query = ProviderQuery(query_text=query_text, top_k=top_k, video_ids=video_ids)
        t0 = time.perf_counter()
        hits = self.asr_bge_provider.search(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "asr_bge",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def ocr_bm25_health(self) -> tuple[int, dict[str, Any]]:
        if self.ocr_bm25_provider is None:
            default_db = self.database if self.database.exists() else Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
            if default_db.exists():
                self.ocr_bm25_provider = OcrBm25Provider(default_db)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "ocr_bm25",
                    "status": "UNAVAILABLE",
                    "error": "OCR database not found",
                }
        h = self.ocr_bm25_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def ocr_bm25_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.ocr_bm25_provider is None:
            status_code, _ = self.ocr_bm25_health()
            if status_code != HTTPStatus.OK:
                return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "ERROR", "error": "OCR BM25 lane unavailable"}
        assert self.ocr_bm25_provider is not None

        query_text = request.get("query") or request.get("q") or ""
        if not isinstance(query_text, str) or not query_text.strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query is required"}
        top_k = int(request.get("top_k", 20))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        query = ProviderQuery(query_text=query_text, top_k=top_k, video_ids=video_ids)
        t0 = time.perf_counter()
        hits = self.ocr_bm25_provider.search(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "ocr_bm25",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def ocr_trigram_health(self) -> tuple[int, dict[str, Any]]:
        if self.ocr_trigram_provider is None:
            default_dir = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\ocr_trigram_v1")
            default_db = self.database if self.database.exists() else Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
            if default_dir.exists():
                self.ocr_trigram_provider = OcrTrigramProvider(default_dir, canonical_db_path=default_db)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "ocr_trigram",
                    "status": "UNAVAILABLE",
                    "error": "OCR Trigram artifact directory not found",
                }
        h = self.ocr_trigram_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def ocr_trigram_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.ocr_trigram_provider is None:
            status_code, _ = self.ocr_trigram_health()
            if status_code != HTTPStatus.OK:
                return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "ERROR", "error": "OCR Trigram lane unavailable"}
        assert self.ocr_trigram_provider is not None

        query_text = request.get("query") or request.get("q") or ""
        if not isinstance(query_text, str) or not query_text.strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query is required"}
        top_k = int(request.get("top_k", 20))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        query = ProviderQuery(query_text=query_text, top_k=top_k, video_ids=video_ids)
        t0 = time.perf_counter()
        hits = self.ocr_trigram_provider.search(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "ocr_trigram",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def ocr_bge_health(self) -> tuple[int, dict[str, Any]]:
        if self.ocr_bge_provider is None:
            default_dir = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\ocr_bge_v1")
            default_db = self.database if self.database.exists() else Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
            if default_dir.exists():
                self.ocr_bge_provider = OcrBgeProvider(default_dir, canonical_db_path=default_db)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "ocr_bge",
                    "status": "UNAVAILABLE",
                    "error": "OCR BGE artifact directory not found",
                }
        h = self.ocr_bge_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def ocr_bge_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.ocr_bge_provider is None:
            status_code, _ = self.ocr_bge_health()
            if status_code != HTTPStatus.OK:
                return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "ERROR", "error": "OCR BGE lane unavailable"}
        assert self.ocr_bge_provider is not None

        query_text = request.get("query") or request.get("q") or ""
        if not isinstance(query_text, str) or not query_text.strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query is required"}
        top_k = int(request.get("top_k", 20))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        query = ProviderQuery(query_text=query_text, top_k=top_k, video_ids=video_ids)
        t0 = time.perf_counter()
        hits = self.ocr_bge_provider.search(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "ocr_bge",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def media_bm25_health(self) -> tuple[int, dict[str, Any]]:
        if self.media_bm25_provider is None:
            default_db = self.database if self.database.exists() else Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
            if default_db.exists():
                self.media_bm25_provider = MediaBm25Provider(default_db)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "media_bm25",
                    "status": "UNAVAILABLE",
                    "error": "Media database not found",
                }
        h = self.media_bm25_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def media_bm25_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.media_bm25_provider is None:
            status_code, _ = self.media_bm25_health()
            if status_code != HTTPStatus.OK:
                return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "ERROR", "error": "Media BM25 lane unavailable"}
        assert self.media_bm25_provider is not None

        query_text = request.get("query") or request.get("q") or ""
        if not isinstance(query_text, str) or not query_text.strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query is required"}
        top_k = int(request.get("top_k", 20))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        # Optional structured filters
        author_filter = request.get("author") or None
        publish_date_from = request.get("publish_date_from") or None
        publish_date_to = request.get("publish_date_to") or None

        query = ProviderQuery(query_text=query_text, top_k=top_k, video_ids=video_ids)
        t0 = time.perf_counter()
        hits = self.media_bm25_provider.search(
            query,
            author_filter=author_filter,
            publish_date_from=publish_date_from,
            publish_date_to=publish_date_to,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "media_bm25",
            "entity_type": "VIDEO",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def qwen_structured_health(self) -> tuple[int, dict[str, Any]]:
        if self.qwen_structured_provider is None:
            default_db = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\qwen_structured_v1\qwen_facets.sqlite")
            if default_db.exists():
                self.qwen_structured_provider = QwenStructuredProvider(default_db)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "qwen_structured",
                    "status": "UNAVAILABLE",
                    "error": "Qwen structured database not found",
                }
        h = self.qwen_structured_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def qwen_structured_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.qwen_structured_provider is None:
            status_code, _ = self.qwen_structured_health()
            if status_code != HTTPStatus.OK:
                return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "ERROR", "error": "Qwen structured lane unavailable"}
        assert self.qwen_structured_provider is not None

        query_text = request.get("query") or request.get("q") or None
        objects = request.get("objects") or ([request["object"]] if "object" in request else [])
        attributes = request.get("attributes") or ([request["attribute"]] if "attribute" in request else [])
        relations = request.get("relations") or ([request["relation"]] if "relation" in request else [])
        counts = request.get("counts") or ([request["count"]] if "count" in request else [])
        scenes = request.get("scenes") or ([request["scene"]] if "scene" in request else [])
        actions = request.get("actions") or ([request["action"]] if "action" in request else [])
        facets = request.get("facets") or []

        has_explicit = bool(objects or attributes or relations or counts or scenes or actions or facets)
        if not query_text and not has_explicit:
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "At least query or one explicit facet is required"}

        top_k = int(request.get("top_k", 50))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        t0 = time.perf_counter()
        hits = self.qwen_structured_provider.search(
            query=query_text or "",
            top_k=top_k,
            candidate_video_ids=video_ids,
            objects=objects,
            attributes=attributes,
            relations=relations,
            counts=counts,
            scenes=scenes,
            actions=actions,
            facets=facets,
            query_id=request.get("query_id"),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "qwen_structured",
            "entity_type": "FRAME",
            "frame_space": "CUSTOM",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def qwen_bm25_health(self) -> tuple[int, dict[str, Any]]:
        if self.qwen_bm25_provider is None:
            default_db = self.database if (self.database and self.database.exists()) else Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
            if default_db.exists():
                self.qwen_bm25_provider = QwenBm25Provider(default_db)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "qwen_bm25",
                    "status": "UNAVAILABLE",
                    "error": "Runtime mapping database not found",
                }
        h = self.qwen_bm25_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h


    def qwen_bm25_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.qwen_bm25_provider is None:
            status_code, _ = self.qwen_bm25_health()
            if status_code != HTTPStatus.OK:
                return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "ERROR", "error": "Qwen BM25 lane unavailable"}
        assert self.qwen_bm25_provider is not None

        query_text = request.get("query") or request.get("q")
        if not query_text or not str(query_text).strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query parameter is required"}

        top_k = int(request.get("top_k", 50))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        t0 = time.perf_counter()
        hits = self.qwen_bm25_provider.search(
            query=query_text,
            top_k=top_k,
            candidate_video_ids=video_ids if video_ids else None,
            query_id=request.get("query_id"),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "qwen_bm25",
            "entity_type": "FRAME",
            "frame_space": "CUSTOM",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }

    def qwen_bge_health(self) -> tuple[int, dict[str, Any]]:
        if self.qwen_bge_provider is None:
            default_artifact_dir = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\qwen_bge_v1")
            if (default_artifact_dir / "qwen_bge.faiss").exists():
                self.qwen_bge_provider = QwenBgeProvider(default_artifact_dir)
            else:
                return HTTPStatus.SERVICE_UNAVAILABLE, {
                    "lane_id": "qwen_bge",
                    "status": "UNAVAILABLE",
                    "error": "Qwen BGE artifact directory not found",
                }
        h = self.qwen_bge_provider.health()
        status_code = HTTPStatus.OK if h.get("status") == "OK" else HTTPStatus.SERVICE_UNAVAILABLE
        return status_code, h

    def qwen_bge_search(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.qwen_bge_provider is None:
            status_code, _ = self.qwen_bge_health()
            if status_code != HTTPStatus.OK:
                return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "ERROR", "error": "Qwen BGE lane unavailable"}
        assert self.qwen_bge_provider is not None

        query_text = request.get("query") or request.get("q")
        if not query_text or not str(query_text).strip():
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "query parameter is required"}

        top_k = int(request.get("top_k", 50))
        video_ids = tuple(request.get("candidate_video_ids") or request.get("video_ids") or ())

        t0 = time.perf_counter()
        hits = self.qwen_bge_provider.search(
            query=query_text,
            top_k=top_k,
            candidate_video_ids=video_ids if video_ids else None,
            query_id=request.get("query_id"),
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return HTTPStatus.OK, {
            "status": "OK",
            "lane": "qwen_bge",
            "entity_type": "FRAME",
            "frame_space": "CUSTOM",
            "query": query_text,
            "query_id": request.get("query_id"),
            "top_k": top_k,
            "count": len(hits),
            "elapsed_ms": round(elapsed_ms, 2),
            "hits": [h.to_dict() for h in hits],
        }



    def health(self) -> tuple[int, dict[str, Any]]:
        if not self.database.is_file():
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "status": "ERROR",
                "error": "ASR search database is unavailable",
            }
        return HTTPStatus.OK, {"status": "OK", "service": "aic2026-asr-search"}

    def search(self, parameters: dict[str, list[str]]) -> tuple[int, dict[str, Any]]:
        query = _single_parameter(parameters, "q", required=True)
        video_id = _single_parameter(parameters, "video_id", required=False)
        raw_limit = _single_parameter(parameters, "limit", required=False) or "20"
        try:
            limit = int(raw_limit)
        except ValueError:
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": "limit must be an integer"}

        started = time.perf_counter()
        try:
            results = search_asr(self.database, query, limit=limit, video_id=video_id)
        except AsrSearchError as exc:
            return HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": str(exc)}
        elapsed_ms = (time.perf_counter() - started) * 1000
        return HTTPStatus.OK, {
            "status": "OK",
            "query": query,
            "video_id": video_id,
            "limit": limit,
            "count": len(results),
            "elapsed_ms": round(elapsed_ms, 3),
            "results": results,
        }

    def capabilities(self) -> tuple[int, dict[str, Any]]:
        return HTTPStatus.OK, self.capability_service.report()

    def unified_search(self, request: Any) -> tuple[int, dict[str, Any]]:
        return HTTPStatus.OK, self.orchestrator.search(request)


def _single_parameter(
    parameters: dict[str, list[str]], field: str, *, required: bool
) -> str | None:
    values = parameters.get(field, [])
    value = values[0].strip() if len(values) == 1 else ""
    if required and not value:
        raise AsrSearchError(f"Missing required query parameter: {field}")
    return value or None


def make_handler(
    application: AsrSearchApi,
    allowed_origins: set[str],
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            origin = self.headers.get("Origin")
            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            origin = self.headers.get("Origin")
            if origin not in allowed_origins:
                self._write_json(HTTPStatus.FORBIDDEN, {"status": "ERROR", "error": "Origin denied"})
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            # Media endpoints – handled separately; failure-isolated from retrieval
            if parsed.path.startswith("/api/v1/media/"):
                range_hdr = self.headers.get("Range")
                handled = write_stream_response(
                    self, parsed.path, parsed.query, range_hdr,
                    application.media_resolver, allowed_origins
                )
                if not handled:
                    self._write_json(HTTPStatus.NOT_FOUND, {"status": "ERROR", "error": "Media endpoint not found"})
                return
            try:
                if parsed.path == "/api/v1/workspace":
                    status, payload = HTTPStatus.OK, {"items": application.workspace.list(_single_parameter(parse_qs(parsed.query), "q", required=False) or "")}
                elif parsed.path == "/api/v1/workspace/export":
                    fmt = _single_parameter(parse_qs(parsed.query), "format", required=False) or "json"
                    content = application.workspace.export(fmt)
                    self._write_json(HTTPStatus.OK, {"format": fmt, "content": content})
                    return
                elif parsed.path.startswith("/api/v1/workspace/"):
                    status, payload = HTTPStatus.OK, application.workspace.get(parsed.path.rsplit("/", 1)[-1])
                elif parsed.path == "/api/health":
                    status, payload = application.health()
                elif parsed.path == "/api/v1/capabilities":
                    status, payload = application.capabilities()
                elif parsed.path in {"/api/v1/lanes/siglip/health", "/api/v1/lanes/siglip_custom/health"}:
                    status, payload = application.siglip_health()
                elif parsed.path in {"/api/v1/lanes/btc-clip/health", "/api/v1/lanes/btc_clip/health"}:
                    status, payload = application.btc_clip_health()
                elif parsed.path in {"/api/v1/lanes/asr-bm25/health", "/api/v1/lanes/asr_bm25/health"}:
                    status, payload = application.asr_bm25_health()
                elif parsed.path in {"/api/v1/lanes/asr-bge/health", "/api/v1/lanes/asr_bge/health"}:
                    status, payload = application.asr_bge_health()
                elif parsed.path in {"/api/v1/lanes/ocr-bm25/health", "/api/v1/lanes/ocr_bm25/health"}:
                    status, payload = application.ocr_bm25_health()
                elif parsed.path in {"/api/v1/lanes/ocr-trigram/health", "/api/v1/lanes/ocr_trigram/health"}:
                    status, payload = application.ocr_trigram_health()
                elif parsed.path in {"/api/v1/lanes/ocr-bge/health", "/api/v1/lanes/ocr_bge/health"}:
                    status, payload = application.ocr_bge_health()
                elif parsed.path in {"/api/v1/lanes/media-bm25/health", "/api/v1/lanes/media_bm25/health"}:
                    status, payload = application.media_bm25_health()
                elif parsed.path in {"/api/v1/lanes/qwen-structured/health", "/api/v1/lanes/qwen_structured/health"}:
                    status, payload = application.qwen_structured_health()
                elif parsed.path in {"/api/v1/lanes/qwen-bm25/health", "/api/v1/lanes/qwen_bm25/health"}:
                    status, payload = application.qwen_bm25_health()
                elif parsed.path in {"/api/v1/lanes/qwen-bge/health", "/api/v1/lanes/qwen_bge/health"}:
                    status, payload = application.qwen_bge_health()
                elif parsed.path == "/api/asr/search":
                    status, payload = application.search(parse_qs(parsed.query, keep_blank_values=True))
                else:
                    status, payload = HTTPStatus.NOT_FOUND, {
                        "status": "ERROR",
                        "error": "Endpoint not found",
                    }
            except (AsrSearchError, WorkspaceError) as exc:
                status, payload = HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": str(exc)}
            self._write_json(status, payload)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            valid_post_paths = {
                "/api/v1/search",
                "/api/v1/workspace",
                "/api/v1/lanes/siglip/search",
                "/api/v1/lanes/siglip_custom/search",
                "/api/v1/lanes/btc-clip/search",
                "/api/v1/lanes/btc_clip/search",
                "/api/v1/lanes/asr-bm25/search",
                "/api/v1/lanes/asr_bm25/search",
                "/api/v1/lanes/asr-bge/search",
                "/api/v1/lanes/asr_bge/search",
                "/api/v1/lanes/ocr-bm25/search",
                "/api/v1/lanes/ocr_bm25/search",
                "/api/v1/lanes/ocr-trigram/search",
                "/api/v1/lanes/ocr_trigram/search",
                "/api/v1/lanes/ocr-bge/search",
                "/api/v1/lanes/ocr_bge/search",
                "/api/v1/lanes/media-bm25/search",
                "/api/v1/lanes/media_bm25/search",
                "/api/v1/lanes/qwen-structured/search",
                "/api/v1/lanes/qwen_structured/search",
                "/api/v1/lanes/qwen-bm25/search",
                "/api/v1/lanes/qwen_bm25/search",
                "/api/v1/lanes/qwen-bge/search",
                "/api/v1/lanes/qwen_bge/search",
            }
            if (
                parsed.path not in valid_post_paths
                and not parsed.path.startswith("/api/v1/workspace/")
            ):
                self._write_json(HTTPStatus.NOT_FOUND, {"status": "ERROR", "error": "Endpoint not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1024 * 1024:
                    raise RetrievalContractError("Request body phải nằm trong 1 byte..1 MiB")
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                if parsed.path == "/api/v1/search":
                    status, payload = application.unified_search(request)
                elif parsed.path in {"/api/v1/lanes/siglip/search", "/api/v1/lanes/siglip_custom/search"}:
                    status, payload = application.siglip_search(request)
                elif parsed.path in {"/api/v1/lanes/btc-clip/search", "/api/v1/lanes/btc_clip/search"}:
                    status, payload = application.btc_clip_search(request)
                elif parsed.path in {"/api/v1/lanes/asr-bm25/search", "/api/v1/lanes/asr_bm25/search"}:
                    status, payload = application.asr_bm25_search(request)
                elif parsed.path in {"/api/v1/lanes/asr-bge/search", "/api/v1/lanes/asr_bge/search"}:
                    status, payload = application.asr_bge_search(request)
                elif parsed.path in {"/api/v1/lanes/ocr-bm25/search", "/api/v1/lanes/ocr_bm25/search"}:
                    status, payload = application.ocr_bm25_search(request)
                elif parsed.path in {"/api/v1/lanes/ocr-trigram/search", "/api/v1/lanes/ocr_trigram/search"}:
                    status, payload = application.ocr_trigram_search(request)
                elif parsed.path in {"/api/v1/lanes/ocr-bge/search", "/api/v1/lanes/ocr_bge/search"}:
                    status, payload = application.ocr_bge_search(request)
                elif parsed.path in {"/api/v1/lanes/media-bm25/search", "/api/v1/lanes/media_bm25/search"}:
                    status, payload = application.media_bm25_search(request)
                elif parsed.path in {"/api/v1/lanes/qwen-structured/search", "/api/v1/lanes/qwen_structured/search"}:
                    status, payload = application.qwen_structured_search(request)
                elif parsed.path in {"/api/v1/lanes/qwen-bm25/search", "/api/v1/lanes/qwen_bm25/search"}:
                    status, payload = application.qwen_bm25_search(request)
                elif parsed.path in {"/api/v1/lanes/qwen-bge/search", "/api/v1/lanes/qwen_bge/search"}:
                    status, payload = application.qwen_bge_search(request)

                else:
                    entry_id = parsed.path.rsplit("/", 1)[-1] if parsed.path != "/api/v1/workspace" else None
                    status, payload = HTTPStatus.OK, application.workspace.save(request, entry_id=entry_id)
            except (RetrievalContractError, WorkspaceError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                status, payload = HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": str(exc)}
            except Exception as exc:
                status, payload = HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
            self._write_json(status, payload)


        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/v1/workspace/"):
                self._write_json(HTTPStatus.NOT_FOUND, {"status": "ERROR", "error": "Endpoint not found"})
                return
            try:
                application.workspace.delete(parsed.path.rsplit("/", 1)[-1])
                self._write_json(HTTPStatus.OK, {"status": "OK"})
            except WorkspaceError as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            print(f"[asr-api] {self.address_string()} {format % args}")

    return Handler


def create_server(
    database: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    allowed_origins: set[str] | None = None,
    capability_service: CapabilityService | None = None,
    orchestrator: SearchOrchestrator | None = None,
    media_resolver: MediaResolver | None = None,
) -> ThreadingHTTPServer:
    origins = allowed_origins or {"http://localhost:3000", "http://127.0.0.1:3000"}
    return ThreadingHTTPServer(
        (host, port), make_handler(AsrSearchApi(database, capability_service, orchestrator, media_resolver), origins)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m aic2026.search.api",
        description="Serve AIC 2026 provider capabilities, unified retrieval v1, and ASR diagnostics.",
    )
    parser.add_argument("--config", default="configs/local.toml")
    parser.add_argument("--database", help="override SQLite database path")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--cors-origin",
        action="append",
        dest="cors_origins",
        help="allowed browser origin; may be repeated",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    resolver = PathResolver.from_config(load_config(args.config))
    database = Path(args.database) if args.database else resolver.work("db/aic.sqlite")
    if not database.is_file():
        print(f"ASR search database not found: {database}", file=sys.stderr)
        return 2
    capability_service = CapabilityService(
        {
            "asr": AsrProvider(database),
            "visual": VisualProvider(resolver.artifact("m1/clip-faiss-btc-v1")),
            "object": ObjectProvider(database),
        },
        media_root=resolver.data_root,
    )
    orchestrator = SearchOrchestrator(capability_service.providers)
    # Media resolver – failure-isolated: missing media root does not abort startup
    media_manifest = resolver.work("audit/videos.jsonl")
    media_resolver = MediaResolver(
        resolver.data_root,
        manifest_path=media_manifest if media_manifest.exists() else None,
    )
    server = create_server(
        database,
        host=args.host,
        port=args.port,
        allowed_origins=set(args.cors_origins) if args.cors_origins else None,
        capability_service=capability_service,
        orchestrator=orchestrator,
        media_resolver=media_resolver,
    )
    print(f"AIC 2026 retrieval API: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping ASR search API.")
    finally:
        server.server_close()
        orchestrator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
