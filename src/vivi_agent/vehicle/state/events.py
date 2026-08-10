"""Vehicle state-change events and in-memory event store.

Every successful transition emitted by :class:`VehicleStateMachine` produces
exactly one :class:`StateChangedEvent`.  The store retains all events for the
lifetime of the machine (no truncation in VEH-02 scope; truncation/replay is
a SIM-01 concern).

Design notes
------------
* Events are immutable frozen dataclasses -- safe to hand to any consumer.
* ``sequence`` is the 1-based position of the event in the store; it is
  distinct from ``next_version``.  They are equal only when the machine
  starts from ``state_version=0`` and no out-of-band events exist.
  Keeping them separate preserves extensibility (e.g. a future out-of-band
  system event could advance sequence without touching state).
* The store uses a dedicated ``threading.Lock`` so reads and writes are
  serialised independently of the machine lock.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .model import VehicleState


class ActorKind(str, Enum):
    """Who initiated a state transition."""

    AGENT = "AGENT"          # ViVi Agent (LLM-driven)
    OPERATOR = "OPERATOR"    # Human operator via simulation UI
    SIMULATOR = "SIMULATOR"  # Automated simulation harness
    SYSTEM = "SYSTEM"        # Internal lifecycle (reset, preset, boot)


@dataclass(frozen=True)
class StateChangedEvent:
    """Immutable record of a single successful Vehicle State transition.

    Attributes
    ----------
    event_id:
        UUID4 string, globally unique.
    correlation_id:
        Caller-supplied opaque string linking this event to a higher-level
        request (e.g. an agent action ID or a UI request ID).
    sequence:
        1-based monotonic position in the :class:`VehicleEventStore`.
    previous_version:
        ``state_version`` of the snapshot **before** the transition.
    next_version:
        ``state_version`` of the snapshot **after** the transition.
        Always ``previous_version + 1``.
    actor_kind:
        Category of the actor that triggered the transition.
    actor_id:
        Opaque identifier for the specific actor (e.g. action UUID, operator
        username, or system component name).
    occurred_at:
        Timezone-aware UTC timestamp recorded by the machine at the moment the
        new state was committed.
    snapshot:
        The **new** :class:`VehicleState` after the transition.  Consumers
        can reconstruct any historical state by replaying events in sequence.
    """

    event_id: str
    correlation_id: str
    sequence: int
    previous_version: int
    next_version: int
    actor_kind: ActorKind
    actor_id: str
    occurred_at: datetime
    snapshot: VehicleState

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if not self.correlation_id:
            raise ValueError("correlation_id must be non-empty")
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")
        if self.previous_version < 0:
            raise ValueError("previous_version must be >= 0")
        if self.next_version != self.previous_version + 1:
            raise ValueError("next_version must be previous_version + 1")
        if not isinstance(self.actor_kind, ActorKind):
            raise ValueError("actor_kind must be ActorKind")
        if not self.actor_id:
            raise ValueError("actor_id must be non-empty")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be a timezone-aware datetime")
        if self.occurred_at.utcoffset() and self.occurred_at.utcoffset().total_seconds() != 0:
            raise ValueError("occurred_at must be in UTC (utcoffset must be zero)")
        if not isinstance(self.snapshot, VehicleState):
            raise ValueError("snapshot must be a VehicleState")

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict projection of this event.

        Suitable for transport to Guardrail or UI consumers.
        """
        return {
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "sequence": self.sequence,
            "previous_version": self.previous_version,
            "next_version": self.next_version,
            "actor_kind": self.actor_kind.value,
            "actor_id": self.actor_id,
            "occurred_at": self.occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "snapshot": self.snapshot.to_authorization_snapshot(),
        }


def _new_event_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class VehicleEventStore:
    """Thread-safe, in-memory, append-only store of :class:`StateChangedEvent`.

    All sequences are 1-based.  The store never truncates events; the full
    history is available for the lifetime of the process.

    Parameters
    ----------
    _new_event_id_fn:
        Injectable factory for ``event_id`` strings (used in tests).
    _clock:
        Injectable clock returning UTC datetime (used in tests).
    """

    def __init__(
        self,
        *,
        _new_event_id_fn=_new_event_id,
        _clock=_utcnow,
    ) -> None:
        self._events: list[StateChangedEvent] = []
        self._lock = threading.Lock()
        self._new_event_id_fn = _new_event_id_fn
        self._clock = _clock

    # ------------------------------------------------------------------
    # Write (internal)
    # ------------------------------------------------------------------

    def _build_and_append(
        self,
        *,
        correlation_id: str,
        previous_version: int,
        next_version: int,
        actor_kind: ActorKind,
        actor_id: str,
        snapshot: VehicleState,
        occurred_at: datetime | None = None,
    ) -> StateChangedEvent:
        """Atomically assign sequence, build event, and append to store."""
        with self._lock:
            sequence = len(self._events) + 1
            event = StateChangedEvent(
                event_id=self._new_event_id_fn(),
                correlation_id=correlation_id,
                sequence=sequence,
                previous_version=previous_version,
                next_version=next_version,
                actor_kind=actor_kind,
                actor_id=actor_id,
                occurred_at=occurred_at if occurred_at is not None else self._clock(),
                snapshot=snapshot,
            )
            self._events.append(event)
        return event

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def latest(self) -> StateChangedEvent | None:
        """Return the most recent event, or ``None`` if the store is empty."""
        with self._lock:
            return self._events[-1] if self._events else None

    def get_event(self, sequence: int) -> StateChangedEvent | None:
        """Return the event at the given 1-based sequence, or ``None``."""
        with self._lock:
            idx = sequence - 1
            if idx < 0 or idx >= len(self._events):
                return None
            return self._events[idx]

    def list_since(self, sequence: int) -> list[StateChangedEvent]:
        """Return all events with ``sequence >= sequence``, in order.

        Passing ``sequence=1`` returns the full history.
        """
        with self._lock:
            idx = max(0, sequence - 1)
            return list(self._events[idx:])

    def list_all(self) -> list[StateChangedEvent]:
        """Return a snapshot copy of all events in chronological order."""
        with self._lock:
            return list(self._events)

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
