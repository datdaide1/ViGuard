"""Polling and streaming adapters conforming to the Agent UI contract."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from threading import RLock
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
        self._session_subscribers: dict[str, _SessionSubscriber] = {}
        self._lock = RLock()

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
        with self._lock:
            for token, subscriber in list(self._session_subscribers.items()):
                if subscriber.session_id != event.get("session_id"):
                    continue
                sequence = int(event["sequence"])
                if sequence <= subscriber.last_sequence:
                    continue
                try:
                    subscriber.callback(copy.deepcopy(event))
                except Exception as exc:  # UI callbacks cannot break the append-only pipeline.
                    if subscriber.on_error is not None:
                        subscriber.on_error(exc)
                    self._session_subscribers.pop(token, None)
                    continue
                subscriber.last_sequence = sequence

    def subscribe_session(
        self,
        session_id: str,
        callback: Callable[[dict[str, Any]], None],
        *,
        since_sequence: int = 0,
        on_error: Callable[[Exception], None] | None = None,
    ) -> str:
        """Atomically replay then follow one session without cross-session leakage."""
        if not session_id:
            raise ValueError("session_id must be non-empty")
        if not callable(callback) or (on_error is not None and not callable(on_error)):
            raise TypeError("callback and on_error must be callable")
        if isinstance(since_sequence, bool) or not isinstance(since_sequence, int) or since_sequence < 0:
            raise ValueError("since_sequence must be a non-negative integer")
        token = f"sub-{uuid.uuid4().hex}"
        subscriber = _SessionSubscriber(session_id, callback, on_error, since_sequence)
        with self._lock:
            self._session_subscribers[token] = subscriber
            for event in self._store.get_events(session_id, since_sequence=since_sequence):
                try:
                    callback(event)
                except Exception as exc:
                    if on_error is not None:
                        on_error(exc)
                    self._session_subscribers.pop(token, None)
                    break
                subscriber.last_sequence = int(event["sequence"])
        return token

    def unsubscribe_session(self, token: str) -> None:
        """Stop one session subscription; unknown tokens are idempotent."""
        with self._lock:
            self._session_subscribers.pop(token, None)

    def stream_session(
        self, session_id: str, since_sequence: int = 0
    ) -> Iterator[dict[str, Any]]:
        """Yield historical events from store starting from since_sequence."""
        events = self._store.get_events(session_id, since_sequence=since_sequence)
        for event in events:
            yield event


@dataclass
class _SessionSubscriber:
    session_id: str
    callback: Callable[[dict[str, Any]], None]
    on_error: Callable[[Exception], None] | None
    last_sequence: int
