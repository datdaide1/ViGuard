"""Guardrail Monitor Integration Adapter (MON-ADP-01).

Subscribes to state changes and manual ticks, queries Guardrail monitor evaluation
for continuous active actions, and routes allow/stop/error decisions to a fail-safe
stop via ActiveActionRegistry.

NOTE: stop/fail transitions currently go through ActiveActionRegistry only — the
`vehicle_gateway` constructor parameter is accepted but not yet wired into the stop
path, and no registry stop handler is registered anywhere in the codebase, so a
monitor-triggered stop only updates the in-memory ActiveActionRecord today. Routing
stop execution through VehicleToolGateway's fail-closed permit boundary (matching
every other vehicle tool call) is a follow-up integration decision, not done here.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any

from vivi_agent.active_actions.models import ActiveActionRecord
from vivi_agent.active_actions.registry import ActiveActionRegistry
from vivi_agent.adapters.guardrail.client import (
    GuardrailAdapterError,
    GuardrailClientAdapter,
)
from vivi_agent.catalog.manifest import MONITORED_INTENTS
from vivi_agent.contracts.guardrail.v1.contract import (
    CONTRACT_VERSION,
    ContractValidationError,
)
from vivi_agent.events.models import (
    DecisionEvent,
    ExecutionEvent,
)
from vivi_agent.vehicle.execution.gateway import VehicleToolGateway

logger = logging.getLogger(__name__)

# MONITORED_INTENTS is imported (not redefined) from catalog.manifest so this
# adapter's monitor coverage can never silently drift from the catalog's own
# MONITOR_COVERAGE_MISMATCH readiness check.


class GuardrailMonitorAdapter:
    """Monitor Integration Adapter connecting Agent active actions with Guardrail monitor."""

    def __init__(
        self,
        guardrail_client: GuardrailClientAdapter,
        active_action_registry: ActiveActionRegistry | None = None,
        vehicle_gateway: VehicleToolGateway | None = None,
        event_pipeline: Any | None = None,
    ) -> None:
        self.guardrail_client = guardrail_client
        self.registry = active_action_registry or ActiveActionRegistry()
        self.gateway = vehicle_gateway
        self.event_pipeline = event_pipeline

        # Metrics
        self._evaluations_count = 0
        self._allow_count = 0
        self._stop_count = 0
        self._error_count = 0
        self._failsafe_stop_count = 0

    @property
    def metrics(self) -> dict[str, int]:
        return {
            "evaluations_count": self._evaluations_count,
            "allow_count": self._allow_count,
            "stop_count": self._stop_count,
            "error_count": self._error_count,
            "failsafe_stop_count": self._failsafe_stop_count,
        }

    def get_metrics(self) -> dict[str, int]:
        return dict(self.metrics)

    def is_monitored_intent(self, intent: str) -> bool:
        """Check if intent is one of the 5 monitored intents."""
        return intent in MONITORED_INTENTS

    def evaluate_active_actions(
        self, current_state: Any | None = None, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Evaluate all running monitored active actions against Guardrail monitor endpoint.

        Returns a list of evaluation summary dictionaries.
        """
        active_records = self.registry.get_active_actions(session_id=session_id)
        results: list[dict[str, Any]] = []

        for record in active_records:
            if not self.is_monitored_intent(record.intent):
                continue

            results.append(self._evaluate_single_action(record, current_state=current_state))

        return results

    def on_state_changed(
        self, new_state: Any, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        """State-change subscription callback: triggers monitor evaluation upon state update."""
        return self.evaluate_active_actions(current_state=new_state, session_id=session_id)

    def tick(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """Manual tick trigger: evaluates all running monitored active actions."""
        return self.evaluate_active_actions(session_id=session_id)

    def _evaluate_single_action(
        self, record: ActiveActionRecord, current_state: Any | None = None
    ) -> dict[str, Any]:
        request_id = f"req-mon-{uuid.uuid4().hex[:8]}"
        payload: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "request_id": request_id,
            "active_action_id": record.action_id,
            "intent": record.intent,
        }
        if current_state is not None:
            if hasattr(current_state, "to_guardrail_snapshot"):
                payload["vehicle_state"] = current_state.to_guardrail_snapshot()
            elif isinstance(current_state, Mapping):
                payload["vehicle_state"] = dict(current_state)

        self._evaluations_count += 1

        try:
            decision = self.guardrail_client.evaluate_monitor(payload)
        except (GuardrailAdapterError, ContractValidationError) as exc:
            return self._handle_monitor_error(record, request_id, str(exc))

        if decision.get("kind") == "error":
            # Typed Guardrail error envelope returned as a normal (non-raising)
            # result by the client (see GuardrailClientAdapter._post) — treat it
            # as a monitor error, not an ordinary stop decision, so the real
            # error code isn't discarded and error metrics stay accurate.
            error_detail = decision.get("error")
            error_detail = error_detail if isinstance(error_detail, Mapping) else {}
            error_msg = str(
                error_detail.get("message")
                or error_detail.get("code")
                or "Guardrail returned a typed error envelope"
            )
            return self._handle_monitor_error(record, request_id, error_msg)

        outcome = decision.get("outcome") or "UNKNOWN"

        if outcome == "ALLOW":
            self._allow_count += 1
            return {
                "action_id": record.action_id,
                "intent": record.intent,
                "outcome": "ALLOW",
                "stopped": False,
                "request_id": request_id,
            }

        # Non-ALLOW outcome (e.g. BLOCK_UNSAFE, BLOCK_UNAVAILABLE, STOP): route stop
        self._stop_count += 1
        reason_code = str(decision.get("reason_code", "MONITOR_STOP"))
        rule_id = str(decision.get("rule_id", "MONITOR_RULE"))

        # Perform stop through the registered registry handler (idempotent: a
        # concurrent stop racing this evaluation is a no-op, not a crash).
        stopped_record = self._execute_stop(
            record,
            reason=f"monitor_stop:{reason_code}",
            failure=False,
        )

        self._emit_decision_event(stopped_record, decision)
        self._emit_execution_event(stopped_record, phase="stopped", reason=reason_code)

        return {
            "action_id": record.action_id,
            "intent": record.intent,
            "outcome": outcome,
            "stopped": True,
            "reason_code": reason_code,
            "rule_id": rule_id,
            "request_id": request_id,
        }

    def _handle_monitor_error(
        self, record: ActiveActionRecord, request_id: str, error_msg: str
    ) -> dict[str, Any]:
        """Fail-safe stop: Monitor error/timeout MUST NOT let action continue silently!"""
        self._error_count += 1
        self._failsafe_stop_count += 1
        self._stop_count += 1

        logger.error(
            "Guardrail monitor evaluation failed for action %s (intent=%s): %s. Executing fail-safe stop.",
            record.action_id,
            record.intent,
            error_msg,
        )

        # Perform fail-safe stop (idempotent: an already-terminal record is a no-op).
        stopped_record = self._execute_stop(
            record,
            reason=f"failsafe_monitor_error:{error_msg}",
            failure=True,
            error=error_msg,
        )

        self._emit_execution_event(
            stopped_record, phase="failed", reason=f"failsafe_monitor_error:{error_msg}"
        )

        return {
            "action_id": record.action_id,
            "intent": record.intent,
            "outcome": "ERROR",
            "stopped": True,
            "error": error_msg,
            "request_id": request_id,
        }

    def _execute_stop(
        self,
        record: ActiveActionRecord,
        reason: str,
        failure: bool = False,
        error: str = "",
    ) -> ActiveActionRecord:
        """Route stop execution through the registered registry handler.

        Idempotent: if the record is already terminal or missing (e.g. raced by
        a concurrent evaluation or a manual stop between the registry snapshot
        and this call), returns the current record instead of raising, so one
        action's already-terminal state can never abort evaluation of the rest
        of the batch (see evaluate_active_actions).
        """
        try:
            if failure:
                return self.registry.fail_action(
                    record.action_id, error=reason, turn_id=record.turn_id
                )
            return self.registry.stop_action(
                record.action_id, reason=reason, turn_id=record.turn_id
            )
        except (ValueError, KeyError) as exc:
            logger.warning(
                "Active action %s already terminal or missing when attempting stop (reason=%s): %s",
                record.action_id,
                reason,
                exc,
            )
            current = self.registry.get_action(record.action_id)
            return current if current is not None else record

    def _emit_decision_event(
        self, record: ActiveActionRecord, decision: Mapping[str, Any]
    ) -> None:
        if self.event_pipeline is None:
            return
        if not record.proposal_id:
            # The Agent-UI event contract requires every decision to correlate
            # with a prior proposal event; a monitor re-evaluation of an active
            # action started without a proposal_id has no proposal to reference,
            # so emitting here would fail downstream stream validation. Skip.
            logger.debug(
                "Skipping DecisionEvent for action %s: no proposal_id to correlate against",
                record.action_id,
            )
            return
        raw_state_version = decision.get("state_version")
        state_version = (
            raw_state_version
            if isinstance(raw_state_version, int)
            else (record.state_version or 0)
        )
        event = DecisionEvent(
            session_id=record.session_id or "default",
            turn_id=record.turn_id or "default",
            request_id=str(decision.get("request_id", record.request_id or "req-mon")),
            proposal_id=record.proposal_id,
            outcome=str(decision.get("outcome", "BLOCK_UNSAFE")),
            reason_code=str(decision.get("reason_code", "MONITOR_STOP")),
            rule_id=str(decision.get("rule_id", "MONITOR_RULE")),
            state_version=state_version,
        )
        try:
            if hasattr(self.event_pipeline, "emit_decision"):
                # Real AgentEventPipeline: builds, redacts, and stores its own typed event.
                self.event_pipeline.emit_decision(
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    request_id=event.request_id,
                    proposal_id=event.proposal_id,
                    outcome=event.outcome,
                    reason_code=event.reason_code,
                    rule_id=event.rule_id,
                    state_version=event.state_version,
                )
            elif hasattr(self.event_pipeline, "publish"):
                self.event_pipeline.publish(event)
            elif hasattr(self.event_pipeline, "emit"):
                self.event_pipeline.emit(event)
        except Exception as exc:
            logger.warning("Failed to publish DecisionEvent: %s", exc)

    def _emit_execution_event(
        self, record: ActiveActionRecord, phase: str, reason: str
    ) -> None:
        if self.event_pipeline is None:
            return
        if not record.proposal_id:
            logger.debug(
                "Skipping ExecutionEvent for action %s: no proposal_id to correlate against",
                record.action_id,
            )
            return
        event = ExecutionEvent(
            session_id=record.session_id or "default",
            turn_id=record.turn_id or "default",
            request_id=record.request_id or "req-mon",
            proposal_id=record.proposal_id,
            execution_id=record.execution_id or f"exec-{record.action_id}",
            intent=record.intent,
            phase=phase,
            detail={"reason": reason},
        )
        try:
            if hasattr(self.event_pipeline, "emit_execution"):
                # Real AgentEventPipeline: builds, redacts, and stores its own typed event.
                self.event_pipeline.emit_execution(
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    request_id=event.request_id,
                    proposal_id=event.proposal_id,
                    execution_id=event.execution_id,
                    intent=event.intent,
                    phase=event.phase,
                    detail=event.detail,
                )
            elif hasattr(self.event_pipeline, "publish"):
                self.event_pipeline.publish(event)
            elif hasattr(self.event_pipeline, "emit"):
                self.event_pipeline.emit(event)
        except Exception as exc:
            logger.warning("Failed to publish ExecutionEvent: %s", exc)
