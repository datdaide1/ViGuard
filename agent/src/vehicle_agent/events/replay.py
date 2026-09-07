"""Event replay module for side-effect-free timeline and state reconstruction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from src.vehicle_agent.contracts.agent_ui.v1.contract import (
    validate_event_stream,
    validate_public_payload,
)


class EventConsumerProtocol(Protocol):
    """Protocol for event stream consumers."""

    def consume(self, event: dict[str, Any]) -> None:
        ...


class EventReplayConsumer:
    """Default side-effect-free event replay consumer."""

    def __init__(self) -> None:
        self.timeline: list[str] = []
        self.reconstructed_state: dict[str, Any] = {}
        self.active_actions: dict[str, str] = {}
        self.proposals: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.executions: list[dict[str, Any]] = []
        self.executed_action_calls_count: int = 0  # Must remain 0 during replay!

    def consume(self, event: dict[str, Any]) -> None:
        """Process one event strictly in passive memory without executing vehicle side-effects."""
        validate_public_payload(event)
        event_type = event["event_type"]
        if event_type == "proposal":
            self.proposals.append(event)
            self.timeline.append(f"proposal:{event['intent']}")
        elif event_type == "decision":
            self.decisions.append(event)
            self.timeline.append(f"decision:{event['outcome']}")
        elif event_type == "execution":
            self.executions.append(event)
            self.timeline.append(f"execution:{event['phase']}")
        elif event_type == "state_changed":
            changes = event.get("changes", {})
            self.reconstructed_state.update(changes)
            self.timeline.append(f"state:{event.get('actor', 'UNKNOWN')}")
        elif event_type == "active_action":
            action_id = str(event.get("active_action_id"))
            phase = str(event.get("phase"))
            self.active_actions[action_id] = phase
            self.timeline.append(f"active:{phase}")


def replay_events(
    events: Sequence[dict[str, Any]],
    consumer: EventConsumerProtocol | None = None,
) -> EventConsumerProtocol:
    """Validate and replay historical events into a consumer without side-effects."""
    validate_event_stream(events)
    target_consumer = consumer if consumer is not None else EventReplayConsumer()
    for event in events:
        target_consumer.consume(event)
    return target_consumer
