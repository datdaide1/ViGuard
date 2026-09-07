"""Agent-owned ports for external action authorization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ActionAuthorizer(Protocol):
    """Authorize one Agent proposal through an external implementation."""

    def evaluate(self, proposal: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ConfirmationAuthorizer(Protocol):
    """Resolve a confirmation through the configured authorization service."""

    def confirm(
        self, *, confirmation_id: str, session_id: str, request_id: str | None = None
    ) -> Mapping[str, Any]: ...


class MonitorAuthorizer(Protocol):
    """Evaluate a long-running action observation externally."""

    def evaluate_monitor(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...
