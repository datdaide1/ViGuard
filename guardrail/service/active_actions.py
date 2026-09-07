"""Guardrail-side registry of currently-running monitored actions .

The Agent owns action execution and is the source of truth for what is live;
this registry is the Guardrail's own view, populated when the action path issues
an ``ALLOW`` for one of the five monitored intents and cleared when a monitor
evaluation says stop. It exists for tracing and for answering "was this
``active_action_id`` one we authorized?" -- it never gates a monitor evaluation
(an unknown id is still evaluated, fail-safe).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

# The five monitored intents (mirror of vehicle_agent.catalog.manifest.MONITORED_INTENTS
# and the five check_mode="monitor" rows in the workbook). Kept as data, asserted
# against the workbook in tests.
MONITORED_INTENTS: frozenset[str] = frozenset(
    {"activate_aac", "activate_autopark", "activate_campmode", "activate_hda", "activate_petmode"}
)


@dataclass
class ActiveAction:
    active_action_id: str
    intent: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ActiveActionRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._actions: dict[str, ActiveAction] = {}

    def register(self, active_action_id: str, intent: str) -> None:
        if intent not in MONITORED_INTENTS:
            return
        with self._lock:
            self._actions[active_action_id] = ActiveAction(active_action_id, intent)

    def deregister(self, active_action_id: str) -> None:
        with self._lock:
            self._actions.pop(active_action_id, None)

    def is_active(self, active_action_id: str) -> bool:
        with self._lock:
            return active_action_id in self._actions

    def snapshot(self) -> tuple[ActiveAction, ...]:
        with self._lock:
            return tuple(self._actions.values())
