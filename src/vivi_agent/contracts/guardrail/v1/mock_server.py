"""Deterministic HTTP mock for Guardrail consumer-contract development only."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .contract import (
    CONTRACT_VERSION,
    ContractValidationError,
    proposal_digest,
    validate_action_proposal,
)

_EXAMPLES_PATH = Path(__file__).with_name("examples.json")


class MockGuardrail:
    """Route protocol requests to named fixtures without implementing policy."""

    def __init__(self) -> None:
        self.examples = json.loads(_EXAMPLES_PATH.read_text(encoding="utf-8"))
        self._confirmation_lock = threading.Lock()
        self._pending_confirmations = {
            "confirm-001": self.examples["confirmation_action_proposal"]
        }

    def handle(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if payload.get("contract_version") != CONTRACT_VERSION:
            return 409, self._error(
                payload.get("request_id", "unknown"),
                "CONTRACT_VERSION_MISMATCH",
                f"Expected {CONTRACT_VERSION}",
            )
        if path == "/v1/evaluate/action":
            try:
                validate_action_proposal(payload)
            except ContractValidationError as exc:
                return 400, self._error(payload.get("proposal_id", "unknown"), exc.code, str(exc))
            fixture = payload.get("arguments", {}).get("mock_outcome")
            if not fixture:
                pid = str(payload.get("proposal_id", "")).lower()
                if "block" in pid:
                    fixture = "BLOCK_UNSAFE"
                elif "confirm" in pid:
                    fixture = "CONFIRM"
                elif "answer" in pid:
                    fixture = "ANSWER"
                else:
                    fixture = "ALLOW"
            result = self.examples["decisions"].get(fixture)
            if result is None:
                return 422, self._error(payload["proposal_id"], "UNKNOWN_MOCK_FIXTURE", fixture)
            response = json.loads(json.dumps(result))
            response["proposal_id"] = payload["proposal_id"]
            if payload.get("tool") in ("open_door", "control_access"):
                response["intent"] = "open_door"
            if "confirmation" in response and isinstance(response["confirmation"], dict):
                response["confirmation"]["proposal_id"] = payload["proposal_id"]
            if fixture == "ALLOW":
                response["permit"]["proposal_digest"] = proposal_digest(payload)
                response["permit"]["intent"] = response["intent"]
            return 200, response
        if path == "/v1/confirmations/confirm":
            if not {"request_id", "confirmation_id", "session_id"} <= set(payload):
                return 400, self._error(payload.get("request_id", "unknown"), "INVALID_CONFIRMATION", "Missing fields")
            with self._confirmation_lock:
                proposal = self._pending_confirmations.pop(payload["confirmation_id"], None)
            if proposal is None:
                return 409, self._error(
                    payload["request_id"],
                    "CONFIRMATION_NOT_ACTIVE",
                    "Confirmation is unknown, expired, or already consumed",
                )
            response = json.loads(json.dumps(self.examples["decisions"]["ALLOW"]))
            response.update(
                {
                    "request_id": payload["request_id"],
                    "proposal_id": proposal["proposal_id"],
                    "intent": "turnon_interiorlight",
                    "rule_id": "R030",
                    "reason_code": "CONFIRMATION_REEVALUATED_ALLOW",
                    "relevant_state": {"speed": 30},
                }
            )
            response["permit"].update(
                {
                    "proposal_digest": proposal_digest(proposal),
                    "intent": response["intent"],
                    "rule_id": response["rule_id"],
                }
            )
            return 200, response
        if path == "/v1/monitor/evaluate":
            if not {"request_id", "active_action_id", "intent"} <= set(payload):
                return 400, self._error(payload.get("request_id", "unknown"), "INVALID_MONITOR_REQUEST", "Missing fields")
            return 200, self.examples["decisions"]["BLOCK_UNSAFE"]
        if path == "/v1/evaluate/query":
            return 200, self.examples["decisions"]["ANSWER"]
        return 404, self._error(payload.get("request_id", "unknown"), "ROUTE_NOT_FOUND", path)

    @staticmethod
    def _error(request_id: str, code: str, message: str) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "kind": "error",
            "request_id": request_id,
            "error": {"code": code, "message": message, "retryable": False},
        }


def make_handler(mock: MockGuardrail) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("JSON request body must be an object")
                status, response = mock.handle(self.path, payload)
            except (ValueError, json.JSONDecodeError):
                status, response = 400, mock._error("unknown", "INVALID_JSON", "Invalid JSON")
            body = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            return

    return Handler


def create_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(MockGuardrail()))
