"""Shared plumbing for wiring monitored active-action handlers (HERO-02, HERO-03).

Extracted from ``active_driving_assist.py`` (HERO-02) when HERO-03 needed the
identical "wrap :class:`ActiveActionHandler`, register a real
:class:`~vivi_agent.active_actions.models.ActiveActionRecord`, roll back on
registry failure" bridging logic for ``activate_autopark``/``activate_campmode``.
Each hero module keeps its own narrow allowed-intents ``frozenset`` and its own
public ``make_monitored_*_handler`` wrapper — a scope violation still fails
loudly, naming that module's actual scope — only the mechanics below are
shared, not the scoping policy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from vivi_agent.active_actions.models import ActiveActionRecord
from vivi_agent.active_actions.registry import (
    SUPERSEDED_BY_NEW_START_REASON,
    ActiveActionRegistry,
)
from vivi_agent.catalog.manifest import MONITORED_INTENTS as _CATALOG_MONITORED_INTENTS
from vivi_agent.vehicle.execution.generic import ActiveActionHandler, BehaviorConfig
from vivi_agent.vehicle.state.events import ActorKind
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import ActiveAction, ActiveActionPhase, VehicleState


def assert_subset_of_monitored_intents(intents: frozenset[str], *, label: str) -> None:
    """Fail loudly at import time if ``intents`` isn't a subset of
    ``catalog.manifest.MONITORED_INTENTS``.

    Each hero module calls this for its own narrow allowed-intents set right
    after defining it, matching ``catalog/manifest.py``'s own
    ``MONITOR_COVERAGE_MISMATCH`` check — a hero module's declared scope must
    never silently drift out of sync with the catalog's declared
    monitored-intent set.
    """
    if not intents <= _CATALOG_MONITORED_INTENTS:
        raise RuntimeError(
            f"{label} {sorted(intents)} is not a subset of "
            f"catalog.manifest.MONITORED_INTENTS {sorted(_CATALOG_MONITORED_INTENTS)}"
        )


def is_restart_supersede(reason: str) -> bool:
    """True when ``reason`` is :data:`SUPERSEDED_BY_NEW_START_REASON` — a
    same-session restart, not a real stop.

    A stop handler must treat this as a no-op on real vehicle state: a fresh
    record for the same intent already exists and now owns the field, and
    telemetry is unaffected by the agent restarting its own bookkeeping, so
    forcing the field off would disengage the *new* run instead of doing
    nothing.
    """
    return reason == SUPERSEDED_BY_NEW_START_REASON


def drop_active_action(state: VehicleState, action_id: Any) -> tuple[ActiveAction, ...]:
    """Return ``state.active_actions`` with the entry matching ``action_id`` removed.

    A no-op (returns the same tuple) if no entry matches — callers that want
    to skip a wasted ``apply()`` when nothing changed can compare the result
    against ``state.active_actions`` themselves.
    """
    return tuple(a for a in state.active_actions if a.action_id != action_id)


def bridge_active_action_handler(
    config: BehaviorConfig,
    state_machine: VehicleStateMachine,
    registry: ActiveActionRegistry,
    *,
    allowed_intents: frozenset[str],
    scope_name: str,
    actor_id: str | None = None,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Wrap :class:`ActiveActionHandler` so successful execution registers/
    unregisters an :class:`ActiveActionRecord`.

    Intended to be registered in ``HandlerRegistry`` in place of the raw
    ``ActiveActionHandler`` for a monitored active-action intent — the wrapped
    callable's return value (state_version/facts/message) is unchanged, so it
    is a drop-in replacement for the gateway.

    Raises
    ------
    ValueError
        If ``config.intent_id`` is outside ``allowed_intents``.
    """
    if config.intent_id not in allowed_intents:
        raise ValueError(
            f"{scope_name} only supports {sorted(allowed_intents)}, got {config.intent_id!r}"
        )

    base_handler = ActiveActionHandler(config, state_machine, actor_id=actor_id)

    def _handler(proposal: Mapping[str, Any]) -> dict[str, Any]:
        result = base_handler(proposal)
        facts = result.get("facts", {})
        # No catalog intent in scope currently sends action="stop"/"cancel" for
        # these intents (only "activate" mapping rules exist) — ActiveActionHandler
        # can only ever compute phase=STARTED here, so a STOPPED branch would be
        # untestable dead code. Removed rather than kept "for completeness"; re-add
        # once a real stop/cancel intent exists.
        if facts.get("phase") != ActiveActionPhase.STARTED.value:
            return result

        action_id = facts.get("action_id")
        session_id = str(proposal.get("session_id") or "")
        try:
            registry.start_action(
                intent=config.intent_id,
                proposal_id=str(proposal.get("proposal_id") or ""),
                state_version=result.get("state_version")
                if isinstance(result.get("state_version"), int)
                else 0,
                session_id=session_id,
                turn_id=str(proposal.get("source_turn_id") or proposal.get("turn_id") or ""),
                active_action_name=facts.get("action_name"),
                action_id=action_id,
            )
        except Exception:
            # Compensate: the base handler already committed a STARTED
            # active_action entry to VehicleState above. If the registry never
            # learns about it, that entry would be permanently invisible to
            # GuardrailMonitorAdapter.tick() while the caller is told this
            # execution failed — remove the orphaned entry before re-raising.
            remove_orphaned_active_action(
                state_machine, action_id, intent=config.intent_id, session_id=session_id
            )
            raise

        return result

    return _handler


def remove_orphaned_active_action(
    state_machine: VehicleStateMachine, action_id: Any, *, intent: str, session_id: str
) -> None:
    """Best-effort cleanup of an ``active_actions`` entry the registry never learned about."""
    if not action_id:
        return

    def patch_fn(state: VehicleState) -> VehicleState:
        remaining = drop_active_action(state, action_id)
        return state if remaining == state.active_actions else replace(state, active_actions=remaining)

    state_machine.apply(
        patch_fn,
        actor_kind=ActorKind.SYSTEM,
        actor_id="registry_start_rollback",
        # Includes intent/session (not just action_id) so a rollback transition
        # is traceable in logs/audit without cross-referencing the registry.
        correlation_id=f"rollback_{intent}_{session_id or 'unknown_session'}_{action_id}",
    )


def apply_system_patch(
    state_machine: VehicleStateMachine,
    *,
    intent: str,
    session_id: str,
    action_id: str,
    actor_id: str,
    correlation_prefix: str,
    patch_fn: Callable[[VehicleState], VehicleState],
) -> None:
    """Shared SYSTEM-actor transition boilerplate for fail-safe monitor-stop handlers."""
    state_machine.apply(
        patch_fn,
        actor_kind=ActorKind.SYSTEM,
        actor_id=actor_id,
        # Includes intent/session (not just action_id) so a monitor-driven
        # transition is traceable in logs/audit without cross-referencing the
        # registry for context.
        correlation_id=f"{correlation_prefix}_{intent}_{session_id or 'unknown_session'}_{action_id}",
    )


def apply_monitor_stop_patch(
    state_machine: VehicleStateMachine,
    record: ActiveActionRecord,
    patch_fn: Callable[[VehicleState], VehicleState],
) -> None:
    """:func:`apply_system_patch` specialised for a Guardrail monitor-triggered
    fail-safe stop — actor_id/correlation_prefix are fixed, since every hero
    module's monitor-stop handler uses the same two literals.
    """
    apply_system_patch(
        state_machine,
        intent=record.intent,
        session_id=record.session_id,
        action_id=record.action_id,
        actor_id="guardrail_monitor_stop",
        correlation_prefix="monitor_stop",
        patch_fn=patch_fn,
    )


# ---------------------------------------------------------------------------
# Grounded stop/fail responses + pure (state-free) monitor result reading.
# Shared by AdasMonitorHeroBehavior (HERO-02) and
# AutoparkCampmodeMonitorHeroBehavior (HERO-03) — both must relay Guardrail's
# monitor outcome verbatim, never re-derive it from vehicle telemetry.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonitorOutcome:
    """Typed view of a `GuardrailMonitorAdapter` evaluation result dict."""

    stopped: bool
    outcome: str
    reason_code: str
    rule_id: str
    action_id: str
    intent: str


class MonitoredActionHeroBehaviorBase:
    """Reference interpretation of Guardrail monitor decisions for one hero module's intents.

    Every method here reads only the Guardrail-produced monitor result (or the
    registry record) — never vehicle telemetry (speed, hands-on-wheel,
    battery, ...). That is a deliberate, structural guarantee: the Agent must
    not reason about *why* a monitored action should stop, only relay
    Guardrail's *outcome*.

    Subclasses must set ``HANDLED_INTENTS`` (and may override
    ``DISPLAY_NAMES``) — this base class holds no intents of its own.
    """

    HANDLED_INTENTS: frozenset[str] = frozenset()
    DISPLAY_NAMES: Mapping[str, str] = {}

    @classmethod
    def evaluate_monitor_result(cls, monitor_result: Mapping[str, Any]) -> MonitorOutcome:
        """Interpret one result dict from ``GuardrailMonitorAdapter.tick()``/
        ``evaluate_active_actions()`` — pure dict-in, dict-out, no state.
        """
        intent = str(monitor_result.get("intent", ""))
        if intent not in cls.HANDLED_INTENTS:
            raise ValueError(
                f"{cls.__name__} only handles {sorted(cls.HANDLED_INTENTS)}, got {intent!r}"
            )
        return MonitorOutcome(
            stopped=bool(monitor_result.get("stopped", False)),
            outcome=str(monitor_result.get("outcome", "UNKNOWN")),
            reason_code=str(monitor_result.get("reason_code", "")),
            rule_id=str(monitor_result.get("rule_id", "")),
            action_id=str(monitor_result.get("action_id", "")),
            intent=intent,
        )

    @classmethod
    def build_stop_message(cls, record: ActiveActionRecord, monitor_result: Mapping[str, Any]) -> str:
        """Grounded Vietnamese stop notice — cites only real reason_code/rule_id.

        A ``GuardrailMonitorAdapter`` fail-safe (``outcome="ERROR"``) carries no
        reason_code/rule_id — only an ``error`` string — so it is routed to
        :meth:`build_fail_message` instead of being formatted as a normal
        policy-triggered stop here.
        """
        if str(monitor_result.get("outcome", "")) == "ERROR":
            return cls.build_fail_message(record, str(monitor_result.get("error") or "lỗi không xác định"))

        outcome = cls.evaluate_monitor_result(monitor_result)
        # Defends against a caller pairing the wrong record with the wrong
        # monitor_result — e.g. iterating multiple running records (possibly
        # two sessions running the *same* intent) and zipping them
        # incorrectly. evaluate_monitor_result above only checked that
        # monitor_result's intent is *in scope*, not that it actually belongs
        # to this record; without this check a mismatch would silently
        # produce a message with the right display name but the wrong
        # rule_id/reason_code. action_id is only checked when monitor_result
        # actually carries one (every real GuardrailMonitorAdapter result
        # does) so callers that never populate it are unaffected.
        mismatched_intent = outcome.intent != record.intent
        mismatched_action = bool(outcome.action_id) and outcome.action_id != record.action_id
        if mismatched_intent or mismatched_action:
            raise ValueError(
                f"monitor_result (intent={outcome.intent!r}, action_id={outcome.action_id!r}) does not "
                f"match record (intent={record.intent!r}, action_id={record.action_id!r})"
            )
        display_name = cls.DISPLAY_NAMES.get(record.intent, record.active_action_name)
        reason = outcome.reason_code or "yêu cầu an toàn từ Guardrail"
        rule = outcome.rule_id or "không xác định"
        return (
            f"{display_name} đã dừng theo yêu cầu của Guardrail "
            f"(rule_id={rule}, reason_code={reason})."
        )

    @classmethod
    def build_fail_message(cls, record: ActiveActionRecord, error: str) -> str:
        """Grounded Vietnamese failure notice for a fail-safe monitor-error stop."""
        if record.intent not in cls.HANDLED_INTENTS:
            # Same "fail loudly on scope violation" guarantee as
            # evaluate_monitor_result — a GuardrailMonitorAdapter ERROR outcome
            # carries no reason_code/rule_id to validate, so record.intent is
            # the only scope signal available on this path.
            raise ValueError(
                f"{cls.__name__} only handles {sorted(cls.HANDLED_INTENTS)}, got record.intent={record.intent!r}"
            )
        display_name = cls.DISPLAY_NAMES.get(record.intent, record.active_action_name)
        return f"{display_name} đã dừng do lỗi giám sát an toàn: {error}."
