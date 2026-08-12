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
from aic2026.retrieval.capabilities import CapabilityService
from aic2026.retrieval.providers import AsrProvider, VisualProvider
from aic2026.search.asr import AsrSearchError, search_asr


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class AsrSearchApi:
    """Thin HTTP adapter around the canonical ASR search implementation."""

    def __init__(self, database: str | Path, capability_service: CapabilityService | None = None) -> None:
        self.database = Path(database)
        self.capability_service = capability_service or CapabilityService(
            {"asr": AsrProvider(self.database)}
        )

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
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/health":
                    status, payload = application.health()
                elif parsed.path == "/api/v1/capabilities":
                    status, payload = application.capabilities()
                elif parsed.path == "/api/asr/search":
                    status, payload = application.search(parse_qs(parsed.query, keep_blank_values=True))
                else:
                    status, payload = HTTPStatus.NOT_FOUND, {
                        "status": "ERROR",
                        "error": "Endpoint not found",
                    }
            except AsrSearchError as exc:
                status, payload = HTTPStatus.BAD_REQUEST, {"status": "ERROR", "error": str(exc)}
            self._write_json(status, payload)

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
) -> ThreadingHTTPServer:
    origins = allowed_origins or {"http://localhost:3000", "http://127.0.0.1:3000"}
    return ThreadingHTTPServer(
        (host, port), make_handler(AsrSearchApi(database, capability_service), origins)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m aic2026.search.api",
        description="Serve the read-only AIC 2026 ASR search API for a local UI.",
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
        },
        media_root=resolver.data_root,
    )
    server = create_server(
        database,
        host=args.host,
        port=args.port,
        allowed_origins=set(args.cors_origins) if args.cors_origins else None,
        capability_service=capability_service,
    )
    print(f"ASR search API: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping ASR search API.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
