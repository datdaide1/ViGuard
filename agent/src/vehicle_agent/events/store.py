"""Append-only Agent Event Store for storing and querying typed events."""

from __future__ import annotations

import copy
from collections import defaultdict
from threading import Lock
from typing import Any, Sequence

from src.vehicle_agent.contracts.agent_ui.v1.contract import (
    EventStreamState,
    validate_next_event,
)
from src.vehicle_agent.events.redaction import redact_event


class AgentEventStore:
    """Thread-safe append-only event store managing contiguous session event streams."""

    MAX_EVENTS_PER_SESSION = 4096

    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._validation_states: dict[str, EventStreamState] = {}
        self._lock = Lock()

    def append(self, event_payload: dict[str, Any]) -> dict[str, Any]:
        """Redact, assign contiguous sequence number, validate, and store event.
        
        Returns the finalized stored event dictionary.
        """
        redacted = redact_event(event_payload)
        session_id = redacted.get("session_id")
        if not session_id or not isinstance(session_id, str):
            raise ValueError("Event must contain a valid string 'session_id'")

        with self._lock:
            session_stream = self._events[session_id]
            if len(session_stream) >= self.MAX_EVENTS_PER_SESSION:
                raise ValueError("EVENT_STORE_SESSION_LIMIT")
            next_seq = len(session_stream) + 1
            
            # Enforce or assign contiguous 1-based sequence
            redacted["sequence"] = next_seq
            
            state = self._validation_states.setdefault(session_id, EventStreamState())
            validate_next_event(redacted, state)
            
            # Commit to store
            session_stream.append(redacted)
            return copy.deepcopy(redacted)

    def get_events(
        self, session_id: str, since_sequence: int = 0
    ) -> list[dict[str, Any]]:
        """Retrieve stored events for a session, optionally filtered by since_sequence."""
        with self._lock:
            stream = self._events.get(session_id, [])
            filtered = [
                copy.deepcopy(e) for e in stream if e["sequence"] > since_sequence
            ]
            return filtered

    def get_turn_events(
        self, session_id: str, turn_id: str
    ) -> list[dict[str, Any]]:
        """Retrieve events for a specific turn in a session."""
        with self._lock:
            stream = self._events.get(session_id, [])
            return [copy.deepcopy(e) for e in stream if e.get("turn_id") == turn_id]

    def get_proposal_events(
        self, session_id: str, proposal_id: str
    ) -> list[dict[str, Any]]:
        """Retrieve events correlated with a specific proposal_id."""
        with self._lock:
            stream = self._events.get(session_id, [])
            return [
                copy.deepcopy(e)
                for e in stream
                if e.get("proposal_id") == proposal_id
            ]

    def get_no_execution_evidence(
        self, session_id: str, proposal_id: str
    ) -> dict[str, Any] | None:
        """Provide explicit evidence that a blocked proposal resulted in zero execution events.
        
        Returns a summary dictionary with decision outcome and execution_count=0 if blocked.
        """
        events = self.get_proposal_events(session_id, proposal_id)
        decision_event = next(
            (e for e in events if e.get("event_type") == "decision"), None
        )
        execution_events = [
            e for e in events if e.get("event_type") == "execution"
        ]
        
        if decision_event and len(execution_events) == 0:
            outcome = str(decision_event.get("outcome", ""))
            if outcome.startswith("BLOCK") or outcome in {"NOT_VOICE_ACTIONABLE", "CONFIRM"}:
                return {
                    "session_id": session_id,
                    "proposal_id": proposal_id,
                    "decision_event": decision_event,
                    "outcome": outcome,
                    "reason_code": decision_event.get("reason_code"),
                    "execution_count": 0,
                    "has_no_execution_evidence": True,
                }
        return None

    def clear(self, session_id: str | None = None) -> None:
        """Clear stored events for a specific session or all sessions."""
        with self._lock:
            if session_id:
                self._events.pop(session_id, None)
                self._validation_states.pop(session_id, None)
            else:
                self._events.clear()
                self._validation_states.clear()
