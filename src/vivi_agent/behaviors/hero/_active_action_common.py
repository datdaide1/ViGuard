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
from vivi_agent.active_actions.registry import ActiveActionRegistry
from vivi_agent.vehicle.execution.generic import ActiveActionHandler, BehaviorConfig
from vivi_agent.vehicle.state.events import ActorKind
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import ActiveActionPhase, VehicleState


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
        remaining = tuple(a for a in state.active_actions if a.action_id != action_id)
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
        display_name = cls.DISPLAY_NAMES.get(record.intent, record.active_action_name)
        return f"{display_name} đã dừng do lỗi giám sát an toàn: {error}."
