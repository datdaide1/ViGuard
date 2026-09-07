"""Polling and streaming adapters conforming to the Agent UI contract."""

from __future__ import annotations

import copy
import logging
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from src.vehicle_agent.contracts.agent_ui.v1.contract import validate_event_stream
from src.vehicle_agent.events.store import AgentEventStore


LOGGER = logging.getLogger(__name__)


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

    MAX_PENDING_EVENTS = 256

    def __init__(self, store: AgentEventStore) -> None:
        self._store = store
        self._session_subscribers: dict[str, _SessionSubscriber] = {}
        self._lock = RLock()

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Reject the unsafe legacy global subscription API."""
        raise RuntimeError("Global subscriptions are disabled; use subscribe_session()")

    def unsubscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Reject the unsafe legacy global subscription API."""
        raise RuntimeError("Global subscriptions are disabled; use unsubscribe_session()")

    def notify(self, event: dict[str, Any]) -> None:
        """Notify subscribers of a new event."""
        ready: list[str] = []
        overflow_errors: list[tuple[Callable[[Exception], None] | None, Exception]] = []
        with self._lock:
            for token, subscriber in list(self._session_subscribers.items()):
                if subscriber.session_id != event.get("session_id"):
                    continue
                sequence = int(event["sequence"])
                if sequence <= subscriber.high_watermark:
                    continue
                if len(subscriber.pending) >= self.MAX_PENDING_EVENTS:
                    error = RuntimeError("STREAM_BACKPRESSURE_LIMIT")
                    self._session_subscribers.pop(token, None)
                    overflow_errors.append((subscriber.on_error, error))
                    continue
                subscriber.pending.append(copy.deepcopy(event))
                subscriber.high_watermark = sequence
                if not subscriber.delivering:
                    subscriber.delivering = True
                    ready.append(token)
        for on_error, error in overflow_errors:
            self._report_error(on_error, error)
        for token in ready:
            self._drain(token)

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
            history = self._store.get_events(session_id, since_sequence=since_sequence)
            if len(history) > self.MAX_PENDING_EVENTS:
                raise ValueError("Replay exceeds bounded subscription window; use polling to catch up")
            subscriber.pending.extend(history)
            if history:
                subscriber.high_watermark = int(history[-1]["sequence"])
            subscriber.delivering = bool(history)
            self._session_subscribers[token] = subscriber
        if history:
            self._drain(token)
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

    def _drain(self, token: str) -> None:
        """Deliver queued events without holding the registry lock."""
        while True:
            with self._lock:
                subscriber = self._session_subscribers.get(token)
                if subscriber is None:
                    return
                if not subscriber.pending:
                    subscriber.delivering = False
                    return
                event = subscriber.pending.popleft()
            try:
                subscriber.callback(event)
            except Exception as exc:
                with self._lock:
                    self._session_subscribers.pop(token, None)
                self._report_error(subscriber.on_error, exc)
                return
            with self._lock:
                current = self._session_subscribers.get(token)
                if current is None:
                    return
                current.last_sequence = int(event["sequence"])

    @staticmethod
    def _report_error(
        on_error: Callable[[Exception], None] | None, error: Exception
    ) -> None:
        """Report subscriber failures without breaking the event producer."""
        if on_error is None:
            return
        try:
            on_error(error)
        except Exception:
            LOGGER.exception("Event subscriber error handler failed")


@dataclass
class _SessionSubscriber:
    session_id: str
    callback: Callable[[dict[str, Any]], None]
    on_error: Callable[[Exception], None] | None
    last_sequence: int
    pending: deque[dict[str, Any]] = field(default_factory=deque)
    delivering: bool = False
    high_watermark: int = field(init=False)

    def __post_init__(self) -> None:
        self.high_watermark = self.last_sequence
