"""Single, fail-closed HTTP adapter for real and mock Guardrail providers."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ...contracts.guardrail.v1.contract import (
    CONTRACT_VERSION,
    ContractValidationError,
    proposal_digest,
    validate_action_proposal,
    validate_guardrail_result,
)


class GuardrailProvider(str, Enum):
    MOCK = "MOCK"
    REAL = "REAL"


class GuardrailAdapterError(RuntimeError):
    """Typed fail-closed adapter error which can never authorize execution."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.execution_allowed = False


@dataclass(frozen=True)
class GuardrailClientConfig:
    base_url: str
    provider: GuardrailProvider
    timeout_seconds: float = 2.0
    read_only_retries: int = 1
    retry_backoff_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.read_only_retries < 0:
            raise ValueError("read_only_retries cannot be negative")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")


class GuardrailClientAdapter:
    """HTTP Guardrail client; provider choice changes configuration, not interface."""

    def __init__(
        self,
        config: GuardrailClientConfig,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._sleep = sleep

    @property
    def event_metadata(self) -> dict[str, str]:
        return {
            "guardrail_provider": self.config.provider.value,
            "guardrail_contract_version": CONTRACT_VERSION,
        }

    @property
    def uses_mock(self) -> bool:
        return self.config.provider is GuardrailProvider.MOCK

    def evaluate(self, proposal: Mapping[str, Any]) -> Mapping[str, Any]:
        """Authorize a state-changing proposal once, without ambiguous retries."""

        try:
            validate_action_proposal(proposal)
        except ContractValidationError as exc:
            raise GuardrailAdapterError(exc.code, str(exc)) from exc
        result = self._post("/v1/evaluate/action", proposal, read_only=False)
        self._validate_result(result)
        if result.get("kind") == "decision":
            if result.get("proposal_id") != proposal["proposal_id"]:
                raise GuardrailAdapterError(
                    "PROPOSAL_MISMATCH", "Guardrail decision does not match submitted proposal"
                )
            permit = result.get("permit")
            if result.get("outcome") == "ALLOW" and (
                not isinstance(permit, Mapping)
                or permit.get("proposal_digest") != proposal_digest(proposal)
            ):
                raise GuardrailAdapterError(
                    "PROPOSAL_MISMATCH", "Guardrail permit is not bound to submitted proposal"
                )
        return result

    def evaluate_query(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Evaluate a non-executable query with bounded retries."""

        result = self._post(
            "/v1/evaluate/query", self._with_contract_version(payload), read_only=True
        )
        self._validate_result(result)
        return result

    def confirm(
        self,
        confirmation_id: str,
        session_id: str,
        request_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Submit a confirmation request to Guardrail to obtain a fresh evaluation decision."""

        req_id = request_id or f"req-{confirmation_id}"
        payload = {
            "contract_version": CONTRACT_VERSION,
            "request_id": req_id,
            "confirmation_id": confirmation_id,
            "session_id": session_id,
        }
        result = self._post("/v1/confirmations/confirm", payload, read_only=False)
        self._validate_result(result)
        return result

    def evaluate_monitor(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Submit a monitor evaluation request to Guardrail for an active action."""

        result = self._post(
            "/v1/monitor/evaluate", self._with_contract_version(payload), read_only=False
        )
        self._validate_result(result)
        return result

    @staticmethod
    def _with_contract_version(payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return a copy of *payload* with ``contract_version`` defaulted if absent."""
        req_payload = dict(payload)
        if "contract_version" not in req_payload:
            req_payload["contract_version"] = CONTRACT_VERSION
        return req_payload

    def _validate_result(self, result: Mapping[str, Any]) -> None:
        try:
            validate_guardrail_result(result)
        except ContractValidationError as exc:
            raise GuardrailAdapterError(exc.code, str(exc)) from exc

    def _post(
        self, path: str, payload: Mapping[str, Any], *, read_only: bool
    ) -> Mapping[str, Any]:
        attempts = 1 + (self.config.read_only_retries if read_only else 0)
        for attempt in range(attempts):
            try:
                request = urllib.request.Request(
                    self.config.base_url.rstrip("/") + "/" + path.lstrip("/"),
                    data=json.dumps(dict(payload), ensure_ascii=False).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "X-Guardrail-Contract-Version": CONTRACT_VERSION,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(
                    request, timeout=self.config.timeout_seconds
                ) as response:
                    body = response.read()
                decoded = json.loads(body)
                if not isinstance(decoded, Mapping):
                    raise ValueError("response JSON must be an object")
                return decoded
            except urllib.error.HTTPError as exc:
                try:
                    decoded = json.loads(exc.read())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    decoded = None
                if isinstance(decoded, Mapping) and decoded.get("kind") == "error":
                    return decoded
                raise GuardrailAdapterError(
                    "MALFORMED_GUARDRAIL_RESPONSE",
                    f"Guardrail returned HTTP {exc.code} without a typed error envelope",
                ) from exc
            except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
                if attempt + 1 < attempts:
                    self._sleep(self.config.retry_backoff_seconds * (attempt + 1))
                    continue
                raise GuardrailAdapterError(
                    "GUARDRAIL_UNAVAILABLE", "Guardrail request failed", retryable=read_only
                ) from exc
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                raise GuardrailAdapterError(
                    "MALFORMED_GUARDRAIL_RESPONSE", "Guardrail response is not valid JSON"
                ) from exc
