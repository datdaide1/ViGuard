"""Polling and streaming adapters conforming to the Agent UI contract."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from src.vivi_agent.contracts.agent_ui.v1.contract import validate_event_stream
from src.vivi_agent.events.store import AgentEventStore


class EventPollingAdapter:
    """Polling adapter serving sequence-ordered public events to UI consumers."""

    def __init__(self, store: AgentEventStore) -> None:
        self._store = store

    def poll(self, session_id: str, since_sequence: int = 0) -> list[dict[str, Any]]:
        """Poll events for a session starting after since_sequence.
        
        Guarantees that polled events pass validate_event_stream when appended
        to historical sequence.
        """
        events = self._store.get_events(session_id, since_sequence=since_sequence)
        if events:
            all_events = self._store.get_events(session_id, since_sequence=0)
            validate_event_stream(all_events)
        return events


class EventStreamAdapter:
    """Streaming adapter facilitating real-time subscription or generator streaming."""

    def __init__(self, store: AgentEventStore) -> None:
        self._store = store
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for new emitted events."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Remove a registered callback."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def notify(self, event: dict[str, Any]) -> None:
        """Notify subscribers of a new event."""
        for callback in list(self._subscribers):
            callback(event)

    def stream_session(
        self, session_id: str, since_sequence: int = 0
    ) -> Iterator[dict[str, Any]]:
        """Yield historical events from store starting from since_sequence."""
        events = self._store.get_events(session_id, since_sequence=since_sequence)
        for event in events:
            yield event
