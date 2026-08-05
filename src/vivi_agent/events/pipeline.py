"""Agent Event Pipeline coordinating typed event emission, redaction, and distribution."""

from __future__ import annotations

from typing import Any, Mapping

from src.vivi_agent.events.adapters import EventPollingAdapter, EventStreamAdapter
from src.vivi_agent.events.models import (
    ActiveActionEvent,
    DecisionEvent,
    ExecutionEvent,
    ProposalEvent,
    StateChangedEvent,
    generate_id,
)
from src.vivi_agent.events.store import AgentEventStore


class AgentEventPipeline:
    """Central event pipeline for generating, storing, and broadcasting typed public events."""

    def __init__(
        self,
        store: AgentEventStore | None = None,
    ) -> None:
        self.store = store if store is not None else AgentEventStore()
        self.stream_adapter = EventStreamAdapter(self.store)
        self.polling_adapter = EventPollingAdapter(self.store)

    def emit_raw(self, event_dict: dict[str, Any]) -> dict[str, Any]:
        """Emit a raw dictionary event through redaction, storage, and streaming."""
        stored = self.store.append(event_dict)
        self.stream_adapter.notify(stored)
        return stored

    def emit_proposal(
        self,
        session_id: str,
        turn_id: str,
        request_id: str,
        intent: str,
        summary: str,
        proposal_id: str | None = None,
        actor: str = "AGENT",
    ) -> dict[str, Any]:
        """Emit a typed proposal event."""
        p_id = proposal_id or generate_id("prop")
        event = ProposalEvent(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=p_id,
            intent=intent,
            summary=summary,
            actor=actor,
        )
        return self.emit_raw(event.to_dict())

    def emit_decision(
        self,
        session_id: str,
        turn_id: str,
        request_id: str,
        proposal_id: str,
        outcome: str = "ALLOW",
        reason_code: str = "PERMITTED",
        rule_id: str = "RULE_ALLOW_ALL",
        state_version: int = 0,
        actor: str = "AGENT",
    ) -> dict[str, Any]:
        """Emit a typed decision event."""
        event = DecisionEvent(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_id,
            outcome=outcome,
            reason_code=reason_code,
            rule_id=rule_id,
            state_version=state_version,
            actor=actor,
        )
        return self.emit_raw(event.to_dict())

    def emit_execution(
        self,
        session_id: str,
        turn_id: str,
        request_id: str,
        proposal_id: str,
        execution_id: str,
        intent: str,
        phase: str,
        detail: dict[str, Any] | None = None,
        actor: str = "AGENT",
    ) -> dict[str, Any]:
        """Emit a typed execution lifecycle event (started, succeeded, failed, stopped)."""
        event = ExecutionEvent(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_id,
            execution_id=execution_id,
            intent=intent,
            phase=phase,
            detail=detail,
            actor=actor,
        )
        return self.emit_raw(event.to_dict())

    def emit_state_changed(
        self,
        session_id: str,
        turn_id: str,
        request_id: str,
        state_version: int,
        changes: dict[str, Any],
        source_execution_id: str | None = None,
        actor: str = "AGENT",
    ) -> dict[str, Any]:
        """Emit a state_changed event."""
        event = StateChangedEvent(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            state_version=state_version,
            changes=changes,
            source_execution_id=source_execution_id,
            actor=actor,
        )
        return self.emit_raw(event.to_dict())

    def emit_active_action(
        self,
        session_id: str,
        turn_id: str,
        request_id: str,
        proposal_id: str,
        execution_id: str,
        active_action_id: str,
        intent: str,
        phase: str,
        progress: float | None = None,
        actor: str = "AGENT",
    ) -> dict[str, Any]:
        """Emit an active_action event."""
        event = ActiveActionEvent(
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            proposal_id=proposal_id,
            execution_id=execution_id,
            active_action_id=active_action_id,
            intent=intent,
            phase=phase,
            progress=progress,
            actor=actor,
        )
        return self.emit_raw(event.to_dict())
