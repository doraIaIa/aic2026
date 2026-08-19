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
from aic2026.retrieval.providers import AsrProvider, ObjectProvider, SigLIPProvider, VisualProvider
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
    ) -> None:
        self.database = Path(database)
        self.capability_service = capability_service or CapabilityService(
            {"asr": AsrProvider(self.database)}
        )
        self.orchestrator = orchestrator or SearchOrchestrator(self.capability_service.providers)
        self.media_resolver = media_resolver
        self.siglip_provider = siglip_provider
        self.workspace = WorkspaceStore(self.database)

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
                elif parsed.path == "/api/v1/lanes/siglip/health":
                    status, payload = application.siglip_health()
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
            if (
                parsed.path not in {"/api/v1/search", "/api/v1/workspace", "/api/v1/lanes/siglip/search"}
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
                elif parsed.path == "/api/v1/lanes/siglip/search":
                    status, payload = application.siglip_search(request)
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
