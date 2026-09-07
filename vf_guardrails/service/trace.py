"""Guardrail-side request trace (PRD FR-14 / §16).

A trace is the demo's evidence: for one request it records which stage resolved
the intent, which state version was read, which rule matched, which outcome went
back, and the latency -- every event carries ``stage_ms`` (time since the
previous event) and ``since_start_ms``, and the terminal event carries
``end_to_end_ms``. It is a replay/audit aid, not a production log store -- kept
in memory (last ``capacity`` requests) and, optionally, appended to a JSONL file.

Decision D1 keeps this separate from the Agent's ``AgentEventPipeline``; the demo
(``run_both.py``) merges the two streams by ``request_id``.

Never records secrets or prompts -- there are none on this path (tool + typed
arguments only), and ``relevant_state`` is already the minimal projection the
engine used.
"""
from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# guardrail-relevant subset of PRD §16.1 event types
EVENT_TYPES = frozenset(
    {
        "guardrail_started",
        "tool_mapped",
        "mapping_failed",
        "constraint_evaluated",
        "confirmation_requested",
        "confirmation_resolved",
        "monitor_evaluated",
        "guardrail_completed",
        "guardrail_error",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _RequestTrace:
    __slots__ = ("request_id", "session_id", "route", "started_at", "_t0", "_last", "events")

    def __init__(self, request_id: str, session_id: str, route: str) -> None:
        self.request_id = request_id
        self.session_id = session_id
        self.route = route
        self.started_at = _now_iso()
        self._t0 = time.perf_counter()
        self._last = self._t0
        self.events: list[dict[str, Any]] = []

    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000.0, 3)

    def split_ms(self) -> tuple[float, float]:
        """(time since previous event, time since request start), in ms."""
        now = time.perf_counter()
        stage_ms = round((now - self._last) * 1000.0, 3)
        self._last = now
        return stage_ms, round((now - self._t0) * 1000.0, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "route": self.route,
            "started_at": self.started_at,
            "elapsed_ms": self.elapsed_ms(),
            "events": list(self.events),
        }


class TraceRecorder:
    def __init__(
        self, *, capacity: int = 256, policy_checksum: str = "", sink_path: str | Path | None = None
    ) -> None:
        self._lock = threading.Lock()
        self._traces: "OrderedDict[str, _RequestTrace]" = OrderedDict()
        self._capacity = capacity
        self._policy_checksum = policy_checksum
        self._sink = Path(sink_path) if sink_path else None

    def begin(self, request_id: str, session_id: str, route: str) -> None:
        with self._lock:
            self._traces[request_id] = _RequestTrace(request_id, session_id, route)
            self._traces.move_to_end(request_id)
            while len(self._traces) > self._capacity:
                self._traces.popitem(last=False)
        self.record(request_id, "guardrail_started", stage="ingress", route=route)

    def record(self, request_id: str, event_type: str, *, stage: str, **detail: Any) -> None:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown trace event_type: {event_type!r}")
        with self._lock:
            trace = self._traces.get(request_id)
            stage_ms, since_start_ms = trace.split_ms() if trace is not None else (0.0, 0.0)
            event = {
                "event_type": event_type,
                "request_id": request_id,
                "session_id": trace.session_id if trace else "unknown",
                "timestamp": _now_iso(),
                "stage": stage,
                "stage_ms": stage_ms,
                "since_start_ms": since_start_ms,
                "policy_checksum": self._policy_checksum,
                **detail,
            }
            if trace is not None:
                trace.events.append(event)
        self._emit(event)

    def end(self, request_id: str, *, status: int, outcome: str | None, error_code: str | None) -> None:
        with self._lock:
            trace = self._traces.get(request_id)
            elapsed = trace.elapsed_ms() if trace else 0.0
        event_type = "guardrail_error" if error_code else "guardrail_completed"
        self.record(
            request_id,
            event_type,
            stage="egress",
            http_status=status,
            outcome=outcome,
            error_code=error_code,
            end_to_end_ms=elapsed,
        )

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            trace = self._traces.get(request_id)
            return trace.to_dict() if trace else None

    def _emit(self, event: dict[str, Any]) -> None:
        if self._sink is None:
            return
        try:
            with self._sink.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass  # a trace sink failure must never break a guardrail decision
