"""Stdlib ``http.server`` shell over :class:`GuardrailService` (P2-D4: zero deps).

One process, ``127.0.0.1:<port>``. No framework. The request core lives in
``app.py``; this file only moves bytes.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .app import GuardrailService
from .envelope import error_envelope


def make_handler(service: GuardrailService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length)) if length else {}
                status, body = service.handle(self.path, payload)
            except (ValueError, json.JSONDecodeError):
                status, body = 400, error_envelope("unknown", "INVALID_JSON", "Invalid JSON body")
            self._send(status, body)

        def do_GET(self) -> None:  # noqa: N802 - lightweight liveness probe
            if self.path == "/healthz":
                self._send(200, {"status": "ok", "policy_checksum": service.engine.policy_checksum})
                return
            self._send(404, error_envelope("unknown", "ROUTE_NOT_FOUND", self.path))

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, _format: str, *args: object) -> None:
            return

    return Handler


def create_server(
    host: str = "127.0.0.1", port: int = 0, *, service: GuardrailService | None = None
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(service or GuardrailService()))
