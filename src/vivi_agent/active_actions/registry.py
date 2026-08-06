"""Active Action Registry (ACTV-01).

Manages the lifecycle of continuous/long-running active actions (HDA, AAC, autopark, camp/pet mode, etc.),
enforces behavior metadata constraints, handles reset/restart cleanup, executes registered stop handlers,
and emits typed ActiveActionEvents.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from vivi_agent.active_actions.models import ActiveActionRecord
from vivi_agent.behaviors.catalog import BEHAVIOR_CATALOG, BehaviorConfig
from vivi_agent.events.models import ActiveActionEvent
from vivi_agent.vehicle.execution.generic import BehaviorHandlerType
from vivi_agent.vehicle.state.model import ActiveActionPhase

logger = logging.getLogger(__name__)

# Type definition for stop handler callbacks: func(record, reason)
StopHandlerCallback = Callable[[ActiveActionRecord, str], None]


class ActiveActionRegistry:
    """Thread-safe registry managing long-running active action lifecycles."""

    def __init__(
        self,
        behavior_catalog: Mapping[str, BehaviorConfig] | None = None,
        event_pipeline: Any | None = None,
    ) -> None:
        """Initialize ActiveActionRegistry.

        Args:
            behavior_catalog: Mapping of intent_id -> BehaviorConfig. Defaults to global BEHAVIOR_CATALOG.
            event_pipeline: Optional event pipeline or store for publishing typed events.
        """
        self._lock = threading.Lock()
        if behavior_catalog is None:
            self._catalog = {cfg.intent_id: cfg for cfg in BEHAVIOR_CATALOG}
        elif isinstance(behavior_catalog, Mapping):
            self._catalog = dict(behavior_catalog)
        else:
            self._catalog = {cfg.intent_id: cfg for cfg in behavior_catalog}
        self._event_pipeline = event_pipeline
        self._records: dict[str, ActiveActionRecord] = {}
        self._stop_handlers: dict[str, StopHandlerCallback] = {}
        # (session_id, intent) -> action_id of the currently running record, if any.
        # Lets start_action supersede a same-session/same-intent run in O(1) instead
        # of scanning the full (ever-growing) history on every call.
        self._running_index: dict[tuple[str, str], str] = {}

    def register_stop_handler(self, intent_or_name: str, handler: StopHandlerCallback) -> None:
        """Register a stop/cleanup handler callback for a specific intent or active action name.

        Args:
            intent_or_name: Intent ID (e.g. 'activate_campmode') or active action name (e.g. 'camp_mode').
            handler: Callable taking (ActiveActionRecord, reason_str).
        """
        with self._lock:
            self._stop_handlers[intent_or_name] = handler
        logger.info("Registered stop handler for active action target '%s'", intent_or_name)

    def is_monitored_behavior(self, intent: str) -> bool:
        """Check whether the given intent is configured as a monitored active action behavior."""
        cfg = self._catalog.get(intent)
        if cfg is None:
            return False
        return cfg.handler_type == BehaviorHandlerType.ACTIVE_ACTION

    def start_action(
        self,
        intent: str,
        proposal_id: str = "",
        execution_id: str = "",
        decision_id: str = "",
        state_version: int = 0,
        session_id: str = "",
        request_id: str = "",
        turn_id: str = "",
        metadata: dict[str, Any] | None = None,
        active_action_name: str | None = None,
        action_id: str | None = None,
    ) -> ActiveActionRecord:
        """Start a new monitored active action.

        Args:
            intent: Intent ID (must be a monitored active action in BehaviorCatalog).
            proposal_id: ID of origin proposal.
            execution_id: ID of execution event.
            decision_id: ID of Guardrail decision.
            state_version: Vehicle state version.
            session_id: Session identifier.
            request_id: Request identifier.
            turn_id: Conversational turn identifier that triggered this start.
            metadata: Additional contextual metadata.
            active_action_name: Explicit name override, if any.
            action_id: Optional fixed action ID. If omitted, auto-generated.

        Returns:
            Created ActiveActionRecord.

        Raises:
            ValueError: If intent is not a monitored active action in BehaviorCatalog.
        """
        if not self.is_monitored_behavior(intent):
            raise ValueError(
                f"INTENT_NOT_MONITORED: Intent '{intent}' is not a monitored active action behavior"
            )

        cfg = self._catalog.get(intent)
        resolved_name = active_action_name or (cfg.active_action_name if cfg else "") or intent
        final_action_id = action_id or f"act-{uuid.uuid4().hex[:8]}"

        now_iso = datetime.now(timezone.utc).isoformat()
        record = ActiveActionRecord(
            action_id=final_action_id,
            intent=intent,
            active_action_name=resolved_name,
            phase=ActiveActionPhase.STARTED,
            progress=0.0,
            proposal_id=proposal_id,
            decision_id=decision_id,
            execution_id=execution_id,
            state_version=state_version,
            session_id=session_id,
            request_id=request_id,
            turn_id=turn_id,
            created_at=now_iso,
            updated_at=now_iso,
            metadata=dict(metadata or {}),
        )

        superseded: list[ActiveActionRecord] = []
        with self._lock:
            # Stop any previously running action for the same session+intent to prevent
            # duplicates. Scoped by session_id (not just intent) so concurrent starts from
            # different sessions/callers don't stomp on each other's running action.
            index_key = (session_id, intent)
            existing_id = self._running_index.get(index_key)
            if existing_id is not None:
                existing = self._records.get(existing_id)
                if existing is not None and existing.phase in (
                    ActiveActionPhase.STARTED,
                    ActiveActionPhase.PROGRESS,
                ):
                    superseded.append(
                        self._internal_stop(
                            existing_id, reason="superseded_by_new_start", turn_id=turn_id
                        )
                    )

            self._records[final_action_id] = record
            self._running_index[index_key] = final_action_id

        # Invoke stop handlers and emit typed events outside the lock (self._lock is
        # non-reentrant; a handler calling back into the registry would otherwise deadlock).
        for stopped_record in superseded:
            self._invoke_stop_handler(stopped_record, reason="superseded_by_new_start")
            self._emit_event(stopped_record)

        self._emit_event(record)
        logger.info(
            "Started active action %s (intent=%s, name=%s)",
            final_action_id,
            intent,
            resolved_name,
        )
        return record

    def update_progress(
        self,
        action_id: str,
        progress: float,
        state_version: int = 0,
        execution_id: str | None = None,
        turn_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActiveActionRecord:
        """Update progress of an active action.

        Args:
            action_id: ID of active action.
            progress: Progress float in range [0.0, 1.0].
            state_version: Updated vehicle state version.
            execution_id: Optional new execution ID.
            turn_id: Conversational turn identifier that triggered this update.
            metadata: Optional metadata to merge.

        Returns:
            Updated ActiveActionRecord.
        """
        with self._lock:
            record = self._records.get(action_id)
            if record is None:
                raise KeyError(f"Active action '{action_id}' not found in registry")

            if record.phase in (ActiveActionPhase.STOPPED, ActiveActionPhase.FAILED, ActiveActionPhase.COMPLETED):
                raise ValueError(f"Cannot update progress for terminal active action '{action_id}' in phase {record.phase}")

            merged_meta = dict(record.metadata)
            if metadata:
                merged_meta.update(metadata)

            now_iso = datetime.now(timezone.utc).isoformat()
            updated = replace(
                record,
                phase=ActiveActionPhase.PROGRESS,
                progress=float(progress),
                state_version=state_version or record.state_version,
                execution_id=execution_id or record.execution_id,
                turn_id=turn_id or record.turn_id,
                updated_at=now_iso,
                metadata=merged_meta,
            )
            self._records[action_id] = updated

        self._emit_event(updated)
        return updated

    def stop_action(
        self,
        action_id: str,
        reason: str = "manual_stop",
        execution_id: str | None = None,
        turn_id: str = "",
    ) -> ActiveActionRecord:
        """Stop an active action gracefully.

        Args:
            action_id: ID of active action.
            reason: Reason string.
            execution_id: Optional execution ID.
            turn_id: Conversational turn identifier that triggered this stop.

        Returns:
            Stopped ActiveActionRecord.

        Raises:
            KeyError: If action_id is not found in the registry.
            ValueError: If the action is already in a terminal phase.
        """
        with self._lock:
            record = self._records.get(action_id)
            if record is None:
                raise KeyError(f"Active action '{action_id}' not found in registry")
            if record.phase in (ActiveActionPhase.STOPPED, ActiveActionPhase.FAILED, ActiveActionPhase.COMPLETED):
                raise ValueError(f"Cannot stop terminal active action '{action_id}' in phase {record.phase}")
            stopped_record = self._internal_stop(
                action_id, reason=reason, execution_id=execution_id, turn_id=turn_id
            )

        # Invoke stop handler and emit typed event outside the lock (self._lock is
        # non-reentrant; a handler calling back into the registry would otherwise deadlock).
        self._invoke_stop_handler(stopped_record, reason=reason)
        self._emit_event(stopped_record)
        return stopped_record

    def fail_action(
        self,
        action_id: str,
        error: str = "execution_failed",
        execution_id: str | None = None,
        turn_id: str = "",
    ) -> ActiveActionRecord:
        """Mark an active action as failed.

        Args:
            action_id: ID of active action.
            error: Error description.
            execution_id: Optional execution ID.
            turn_id: Conversational turn identifier that triggered this failure.

        Returns:
            Failed ActiveActionRecord.

        Raises:
            KeyError: If action_id is not found in the registry.
            ValueError: If the action is already in a terminal phase.
        """
        with self._lock:
            record = self._records.get(action_id)
            if record is None:
                raise KeyError(f"Active action '{action_id}' not found in registry")
            if record.phase in (ActiveActionPhase.STOPPED, ActiveActionPhase.FAILED, ActiveActionPhase.COMPLETED):
                raise ValueError(f"Cannot fail terminal active action '{action_id}' in phase {record.phase}")

            now_iso = datetime.now(timezone.utc).isoformat()
            failed_record = replace(
                record,
                phase=ActiveActionPhase.FAILED,
                execution_id=execution_id or record.execution_id,
                turn_id=turn_id or record.turn_id,
                failure_reason=error,
                updated_at=now_iso,
            )
            self._records[action_id] = failed_record
            self._clear_running_index(failed_record)

        # Invoke stop handler and emit typed event outside the lock (self._lock is
        # non-reentrant; a handler calling back into the registry would otherwise deadlock).
        self._invoke_stop_handler(failed_record, reason=f"failed: {error}")
        self._emit_event(failed_record)
        logger.warning("Active action %s failed: %s", action_id, error)
        return failed_record

    def complete_action(
        self,
        action_id: str,
        execution_id: str | None = None,
        turn_id: str = "",
    ) -> ActiveActionRecord:
        """Mark an active action as successfully completed.

        Args:
            action_id: ID of active action.
            execution_id: Optional execution ID.
            turn_id: Conversational turn identifier that triggered this completion.

        Returns:
            Completed ActiveActionRecord.
        """
        with self._lock:
            record = self._records.get(action_id)
            if record is None:
                raise KeyError(f"Active action '{action_id}' not found in registry")
            if record.phase in (ActiveActionPhase.STOPPED, ActiveActionPhase.FAILED, ActiveActionPhase.COMPLETED):
                raise ValueError(f"Cannot complete terminal active action '{action_id}' in phase {record.phase}")

            now_iso = datetime.now(timezone.utc).isoformat()
            completed_record = replace(
                record,
                phase=ActiveActionPhase.COMPLETED,
                progress=1.0,
                execution_id=execution_id or record.execution_id,
                turn_id=turn_id or record.turn_id,
                updated_at=now_iso,
            )
            self._records[action_id] = completed_record
            self._clear_running_index(completed_record)

        self._emit_event(completed_record)
        logger.info("Active action %s completed", action_id)
        return completed_record

    def reset_and_cleanup(
        self, reason: str = "system_reset", turn_id: str = ""
    ) -> list[ActiveActionRecord]:
        """Reset and clean up active actions on agent restart or vehicle state reset.

        Ensures no running active actions are restored as active/running after reset/restart.
        Calls registered stop handlers and emits typed ActiveActionEvents for all stopped actions.

        Args:
            reason: Reason for reset/cleanup.
            turn_id: Conversational turn identifier that triggered this reset, if any.

        Returns:
            List of stopped/cleaned up ActiveActionRecords.
        """
        cleaned_up: list[ActiveActionRecord] = []
        with self._lock:
            running_ids = [
                rec.action_id
                for rec in self._records.values()
                if rec.phase in (ActiveActionPhase.STARTED, ActiveActionPhase.PROGRESS)
            ]
            for action_id in running_ids:
                stopped_rec = self._internal_stop(action_id, reason=reason, turn_id=turn_id)
                cleaned_up.append(stopped_rec)

        # Invoke stop handlers and emit typed stop events outside the lock (self._lock is
        # non-reentrant; a handler calling back into the registry would otherwise deadlock).
        for record in cleaned_up:
            self._invoke_stop_handler(record, reason=reason)
            self._emit_event(record)

        logger.info("Reset & cleanup performed (%s): stopped %d running actions", reason, len(cleaned_up))
        return cleaned_up

    def get_action(self, action_id: str) -> ActiveActionRecord | None:
        """Retrieve a specific active action record by ID."""
        with self._lock:
            return self._records.get(action_id)

    def get_running_action(self, session_id: str, intent: str) -> ActiveActionRecord | None:
        """O(1) lookup of the currently running record for (session_id, intent).

        Backed directly by ``_running_index`` instead of the O(total records
        ever created) scan ``get_active_actions``/``query_actions`` perform —
        use this when the caller only needs "is there a running record for
        this exact session+intent", not a filtered list.
        """
        with self._lock:
            action_id = self._running_index.get((session_id, intent))
            if action_id is None:
                return None
            return self._records.get(action_id)

    def get_active_actions(self, session_id: str | None = None) -> list[ActiveActionRecord]:
        """Get currently active (running) actions.

        Args:
            session_id: Optional session filter.

        Returns:
            List of active ActiveActionRecords.
        """
        return self.query_actions(session_id=session_id, active_only=True)

    def query_actions(
        self,
        session_id: str | None = None,
        intent: str | None = None,
        phase: ActiveActionPhase | str | None = None,
        active_only: bool = False,
    ) -> list[ActiveActionRecord]:
        """Query active action records for UI endpoints or monitoring.

        Args:
            session_id: Filter by session ID.
            intent: Filter by intent ID.
            phase: Filter by ActiveActionPhase enum or phase string.
            active_only: If True, filter only running phases (STARTED, PROGRESS).

        Returns:
            List of matching ActiveActionRecords.
        """
        with self._lock:
            records = list(self._records.values())

        filtered: list[ActiveActionRecord] = []
        if phase is None:
            target_phase_val = None
        elif isinstance(phase, ActiveActionPhase):
            target_phase_val = phase.value
        else:
            target_phase_val = str(phase)

        for rec in records:
            if session_id is not None and rec.session_id != session_id:
                continue
            if intent is not None and rec.intent != intent:
                continue
            if target_phase_val is not None and rec.phase.value != target_phase_val:
                continue
            if active_only and rec.phase not in (ActiveActionPhase.STARTED, ActiveActionPhase.PROGRESS):
                continue
            filtered.append(rec)

        return filtered

    def list_all(self) -> list[ActiveActionRecord]:
        """List all active action records in history."""
        with self._lock:
            return list(self._records.values())

    def set_event_pipeline(self, pipeline: Any) -> None:
        """Set or update the event pipeline for publishing events."""
        with self._lock:
            self._event_pipeline = pipeline

    # ---------------------------------------------------------------------------
    # Private Helpers
    # ---------------------------------------------------------------------------

    def _internal_stop(
        self,
        action_id: str,
        reason: str,
        execution_id: str | None = None,
        turn_id: str = "",
    ) -> ActiveActionRecord:
        """Internal helper to transition an action to STOPPED state under lock.

        Callers are responsible for invoking the stop handler and emitting the
        resulting event AFTER releasing self._lock (a plain, non-reentrant lock) —
        a handler that calls back into the registry would otherwise deadlock.
        """
        record = self._records[action_id]
        now_iso = datetime.now(timezone.utc).isoformat()

        stopped_record = replace(
            record,
            phase=ActiveActionPhase.STOPPED,
            execution_id=execution_id or record.execution_id,
            turn_id=turn_id or record.turn_id,
            stop_reason=reason,
            updated_at=now_iso,
        )
        self._records[action_id] = stopped_record
        self._clear_running_index(stopped_record)
        return stopped_record

    def _clear_running_index(self, record: ActiveActionRecord) -> None:
        """Remove the (session_id, intent) -> action_id index entry if it still points here.

        Must be called while holding self._lock, immediately after a record transitions
        out of the running phases (STOPPED/FAILED/COMPLETED).
        """
        index_key = (record.session_id, record.intent)
        if self._running_index.get(index_key) == record.action_id:
            del self._running_index[index_key]

    def _invoke_stop_handler(self, record: ActiveActionRecord, reason: str) -> None:
        """Invoke registered stop handler if available."""
        handler = self._stop_handlers.get(record.intent) or self._stop_handlers.get(record.active_action_name)
        if handler is not None:
            try:
                handler(record, reason)
            except Exception as err:
                logger.exception("Error executing stop handler for action %s: %s", record.action_id, err)

    def _emit_event(self, record: ActiveActionRecord) -> None:
        """Publish a typed ActiveActionEvent for the given action record."""
        pipeline = self._event_pipeline
        if pipeline is None:
            return

        session_id = record.session_id or "unknown_session"
        turn_id = record.turn_id or "unknown_turn"
        request_id = record.request_id or "unknown_request"
        phase_value = record.phase.value if isinstance(record.phase, ActiveActionPhase) else str(record.phase)
        progress = record.progress if record.phase in (ActiveActionPhase.PROGRESS, ActiveActionPhase.COMPLETED) else None

        try:
            if hasattr(pipeline, "emit_active_action"):
                # Real AgentEventPipeline: builds, redacts, and stores its own typed event.
                pipeline.emit_active_action(
                    session_id=session_id,
                    turn_id=turn_id,
                    request_id=request_id,
                    proposal_id=record.proposal_id,
                    execution_id=record.execution_id,
                    active_action_id=record.action_id,
                    intent=record.intent,
                    phase=phase_value,
                    progress=progress,
                )
                return

            event = ActiveActionEvent(
                session_id=session_id,
                turn_id=turn_id,
                request_id=request_id,
                proposal_id=record.proposal_id,
                execution_id=record.execution_id,
                active_action_id=record.action_id,
                intent=record.intent,
                phase=phase_value,
                progress=progress,
            )
            if hasattr(pipeline, "publish"):
                pipeline.publish(event)
            elif hasattr(pipeline, "append"):
                # Dict-based sinks (e.g. AgentEventStore.append) expect a plain dict,
                # not a raw dataclass instance.
                pipeline.append(event.to_dict())
            elif callable(pipeline):
                pipeline(event)
        except Exception as err:
            logger.exception("Failed to publish ActiveActionEvent: %s", err)
