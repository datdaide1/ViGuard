"""OPS-01 reset, readiness, and UI reconnect coordination."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


class EventStore(Protocol):
    def clear(self, session_id: str | None = None) -> None: ...
    def get_events(self, session_id: str, since_sequence: int = 0) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class DependencyHealth:
    name: str
    available: bool
    reason: str | None = None


class HealthRegistry:
    """Expose liveness separately from dependency-backed readiness."""

    def __init__(self, required: tuple[str, ...] = ("model", "guardrail", "ui")) -> None:
        self._required = frozenset(required)
        self._statuses = {name: DependencyHealth(name, False, "not_checked") for name in required}
        self._lock = threading.Lock()

    def report(self, name: str, available: bool, reason: str | None = None) -> None:
        if not name:
            raise ValueError("dependency name must be non-empty")
        with self._lock:
            self._statuses[name] = DependencyHealth(name, available, reason)

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            statuses = dict(self._statuses)
        unavailable = tuple(sorted(name for name in self._required if not statuses[name].available))
        return {"live": True, "ready": not unavailable,
            "unavailable_dependencies": unavailable,
            "dependencies": {
                name: {"available": status.available, "reason": status.reason}
                for name, status in statuses.items()
            }}


@dataclass(frozen=True)
class ReconnectResult:
    session_id: str
    connection_id: str
    events: tuple[Mapping[str, Any], ...]
    next_sequence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "connection_id": self.connection_id,
            "events": [dict(event) for event in self.events],
            "next_sequence": self.next_sequence,
        }


class RuntimeResetError(RuntimeError):
    """Typed failure returned when a reset dependency cannot reset safely."""

    code = "VEHICLE_RESET_FAILED"

    def __init__(self, scope: str, reason: str | None) -> None:
        self.scope = scope
        self.reason = reason or "unknown vehicle reset failure"
        super().__init__(f"{self.code}: {self.reason}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "scope": self.scope, "reason": self.reason}


class UIConnectionRegistry:
    """Resume event delivery after the last ACK without invoking side effects."""

    def __init__(self, event_store: EventStore) -> None:
        self._event_store = event_store
        self._acked: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def acknowledge(self, session_id: str, connection_id: str, sequence: int) -> None:
        if sequence < 0:
            raise ValueError("sequence must be >= 0")
        key = (session_id, connection_id)
        with self._lock:
            self._acked[key] = max(sequence, self._acked.get(key, 0))

    def reconnect(self, session_id: str, connection_id: str) -> ReconnectResult:
        with self._lock:
            cursor = self._acked.get((session_id, connection_id), 0)
        events = self._event_store.get_events(session_id, since_sequence=cursor)
        next_sequence = max((int(event["sequence"]) for event in events), default=cursor)
        return ReconnectResult(session_id, connection_id, tuple(events), next_sequence)

    def reset(self, session_id: str | None = None) -> None:
        with self._lock:
            if session_id is None:
                self._acked.clear()
            else:
                self._acked = {key: value for key, value in self._acked.items() if key[0] != session_id}


@dataclass(frozen=True)
class ResetResult:
    scope: str
    session_id: str | None
    stopped_actions: int
    cancelled_confirmations: int
    vehicle_reset: bool
    reset_at: datetime


class RuntimeOperations:
    """Coordinate cleanup under one lifecycle lock."""

    def __init__(self, *, active_actions: Any, confirmations: Any, permit_store: Any,
                 agent_events: EventStore, ui_connections: UIConnectionRegistry,
                 simulation: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._active_actions = active_actions
        self._confirmations = confirmations
        self._permit_store = permit_store
        self._agent_events = agent_events
        self._ui_connections = ui_connections
        self._simulation = simulation
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()

    def reset(self, scope: str, *, session_id: str | None = None) -> ResetResult:
        if scope not in {"session", "simulator", "all"}:
            raise ValueError("scope must be session, simulator, or all")
        if scope == "session" and not session_id:
            raise ValueError("session reset requires session_id")
        with self._lock, self._permit_store.lifecycle_boundary():
            # Take the cutoff only after acquiring the shared lifecycle
            # boundary so every permit from the pre-reset snapshot is covered.
            reset_at = self._clock()
            if reset_at.tzinfo is None:
                raise ValueError("reset clock must return a timezone-aware datetime")
            # Simulator state is process-global, so resetting it invalidates
            # every action/confirmation/permit that was derived from the old
            # snapshot. Session reset remains isolated to its caller.
            target = session_id if scope == "session" else None
            stopped = len(self._active_actions.reset_and_cleanup(session_id=target))
            cancelled = self._confirmations.cancel_pending_for_reset(target)
            self._permit_store.revoke_before(reset_at, target)
            self._agent_events.clear(target)
            self._ui_connections.reset(target)

            vehicle_reset = False
            if scope in {"simulator", "all"}:
                result = self._simulation.reset(correlation_id="ops-01-reset")
                vehicle_reset = bool(result.success)
                if not vehicle_reset:
                    raise RuntimeResetError(scope, result.error)
            return ResetResult(scope, session_id, stopped, cancelled, vehicle_reset, reset_at)
