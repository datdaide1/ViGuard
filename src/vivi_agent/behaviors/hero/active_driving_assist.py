"""HERO-02 — HDA/AAC active driving assist hero behaviors.

Closes the wiring gap left open by ACTV-01 (:class:`ActiveActionRegistry`) and
MON-ADP-01 (:class:`GuardrailMonitorAdapter`): neither module was ever
connected to anything else in the codebase, so a running ``activate_hda`` or
``activate_aac`` action was invisible to the monitor loop, and a Guardrail
monitor stop decision never reached the real :class:`VehicleState` (see
``src/vivi_agent/adapters/monitor/mon-adp-01/DEFERRED_FOLLOWUPS.md``, gap #1).

This module closes that gap **for ``activate_hda``/``activate_aac`` only** —
``activate_autopark``/``activate_campmode``/``activate_petmode`` remain open,
deferred to HERO-03.

Design notes
------------
- The monitor-triggered stop is a **fail-safe system mutation**, not a new
  Guardrail-authorized proposal. Routing it through
  :class:`~vivi_agent.vehicle.execution.gateway.VehicleToolGateway`'s normal
  permit boundary would make an emergency stop depend on a second network
  round-trip to Guardrail — exactly the failure mode
  ``DEFERRED_FOLLOWUPS.md`` warns against. Instead the stop handlers patch
  :class:`VehicleState` directly via ``VehicleStateMachine.apply(...,
  actor_kind=ActorKind.SYSTEM)``, the same pattern
  :func:`~vivi_agent.behaviors.hero.open_door.reset_open_door_state` uses for
  HERO-01's deterministic reset.
- :class:`AdasMonitorHeroBehavior` deliberately contains **no vehicle-state
  inspection** (no speed/hands-off/threshold branches). HERO-02's acceptance
  criteria requires the Agent to never infer or duplicate Guardrail's monitor
  policy — e.g. AAC's Stop&Go Hold (``acc_state=ACTIVE`` while ``speed=0``) is
  explicitly *not* a violation, and only Guardrail's monitor decision governs
  whether an action keeps running.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from vivi_agent.active_actions.models import ActiveActionRecord
from vivi_agent.active_actions.registry import ActiveActionRegistry
from vivi_agent.vehicle.execution.generic import ActiveActionHandler, BehaviorConfig
from vivi_agent.vehicle.state.events import ActorKind
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import AccState, ActiveActionPhase, VehicleState

# The only two intents this module is responsible for. Kept as a frozen set
# (rather than reusing the broader MONITORED_INTENTS from catalog.manifest)
# so this module fails loudly if ever asked to handle an intent outside its
# HERO-02 scope, instead of silently behaving as if HERO-03 were already done.
HDA_AAC_INTENTS: frozenset[str] = frozenset({"activate_hda", "activate_aac"})

_DISPLAY_NAMES: dict[str, str] = {
    "activate_hda": "Hỗ trợ lái trên cao tốc (HDA)",
    "activate_aac": "Điều khiển hành trình thích ứng (AAC)",
}


# ---------------------------------------------------------------------------
# 1. ActiveAction creation — bridge ActiveActionHandler execution to the
#    ActiveActionRegistry so MON-ADP-01's monitor loop has real records to
#    evaluate.
# ---------------------------------------------------------------------------


def make_monitored_active_action_handler(
    config: BehaviorConfig,
    state_machine: VehicleStateMachine,
    registry: ActiveActionRegistry,
    *,
    actor_id: str | None = None,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Wrap :class:`ActiveActionHandler` so successful execution registers/
    unregisters an :class:`ActiveActionRecord`.

    Intended to be registered in :class:`HandlerRegistry` in place of the raw
    ``ActiveActionHandler`` for ``activate_hda``/``activate_aac`` only — the
    wrapped callable's return value (state_version/facts/message) is
    unchanged, so it is a drop-in replacement for the gateway.

    Raises
    ------
    ValueError
        If ``config.intent_id`` is outside :data:`HDA_AAC_INTENTS`.
    """
    if config.intent_id not in HDA_AAC_INTENTS:
        raise ValueError(
            f"make_monitored_active_action_handler only supports {sorted(HDA_AAC_INTENTS)}, "
            f"got {config.intent_id!r}"
        )

    base_handler = ActiveActionHandler(config, state_machine, actor_id=actor_id)

    def _handler(proposal: Mapping[str, Any]) -> dict[str, Any]:
        result = base_handler(proposal)
        facts = result.get("facts", {})
        phase_value = facts.get("phase")
        session_id = str(proposal.get("session_id") or "")
        turn_id = str(proposal.get("source_turn_id") or proposal.get("turn_id") or "")
        proposal_id = str(proposal.get("proposal_id") or "")
        state_version = result.get("state_version")
        state_version = state_version if isinstance(state_version, int) else 0

        if phase_value == ActiveActionPhase.STARTED.value:
            registry.start_action(
                intent=config.intent_id,
                proposal_id=proposal_id,
                state_version=state_version,
                session_id=session_id,
                turn_id=turn_id,
                active_action_name=facts.get("action_name"),
                action_id=facts.get("action_id"),
            )
        elif phase_value == ActiveActionPhase.STOPPED.value:
            # Defensive: no catalog intent currently sends action="stop" for
            # activate_hda/activate_aac (see DEFERRED_FOLLOWUPS.md), but keep
            # the lifecycle complete rather than silently drop it if one ever
            # does.
            running = [
                rec
                for rec in registry.get_active_actions(session_id=session_id)
                if rec.intent == config.intent_id
            ]
            for rec in running:
                try:
                    registry.stop_action(rec.action_id, reason="user_requested_stop", turn_id=turn_id)
                except (ValueError, KeyError):
                    pass  # already terminal/missing — idempotent, not an error

        return result

    return _handler


# ---------------------------------------------------------------------------
# 2. HDA monitor-stop handling — the actual fail-safe state mutation that was
#    completely missing (DEFERRED_FOLLOWUPS.md gap #1).
# ---------------------------------------------------------------------------


def _apply_hda_off(state_machine: VehicleStateMachine, record: ActiveActionRecord) -> None:
    """Turn ``adas.hda_active`` off and drop the matching active_action entry."""

    def patch_fn(state: VehicleState) -> VehicleState:
        remaining = tuple(a for a in state.active_actions if a.action_id != record.action_id)
        if not state.adas.hda_active and remaining == state.active_actions:
            return state  # already off, nothing to clean up
        new_adas = replace(state.adas, hda_active=False) if state.adas.hda_active else state.adas
        return replace(state, adas=new_adas, active_actions=remaining)

    state_machine.apply(
        patch_fn,
        actor_kind=ActorKind.SYSTEM,
        actor_id="guardrail_monitor_stop",
        correlation_id=f"monitor_stop_{record.action_id}",
    )


def _apply_aac_cancelled(state_machine: VehicleStateMachine, record: ActiveActionRecord) -> bool:
    """Cancel ``adas.acc_state``.

    Cascades ``hda_active`` off in the *same* transition when it was active —
    required by the ``HDA_REQUIRES_ACTIVE_ACC`` invariant on ``AdasState``,
    which would otherwise reject an intermediate state where ACC is no longer
    ACTIVE but HDA is still on.

    Returns
    -------
    bool
        ``True`` if HDA was cascaded off as part of this transition (the
        caller uses this to also stop the corresponding registry record).
    """
    cascaded = False

    def patch_fn(state: VehicleState) -> VehicleState:
        nonlocal cascaded
        cascaded = state.adas.hda_active
        new_adas = replace(state.adas, acc_state=AccState.CANCELLED, hda_active=False)
        remaining = tuple(a for a in state.active_actions if a.action_id != record.action_id)
        if cascaded:
            remaining = tuple(a for a in remaining if a.intent != "activate_hda")
        return replace(state, adas=new_adas, active_actions=remaining)

    state_machine.apply(
        patch_fn,
        actor_kind=ActorKind.SYSTEM,
        actor_id="guardrail_monitor_stop",
        correlation_id=f"monitor_stop_{record.action_id}",
    )
    return cascaded


def register_hda_aac_stop_handlers(
    registry: ActiveActionRegistry,
    state_machine: VehicleStateMachine,
) -> None:
    """Register the fail-safe stop handlers MON-ADP-01 relies on.

    Before this, ``registry.register_stop_handler(...)`` was never called for
    any intent, so a Guardrail monitor stop only flipped the in-memory
    :class:`ActiveActionRecord` phase — the vehicle itself never actually
    stopped. This wires the real state mutation for HDA/AAC.
    """

    def _stop_hda(record: ActiveActionRecord, _reason: str) -> None:
        _apply_hda_off(state_machine, record)

    def _stop_aac(record: ActiveActionRecord, reason: str) -> None:
        hda_cascaded = _apply_aac_cancelled(state_machine, record)
        if not hda_cascaded:
            return
        # HDA_REQUIRES_ACTIVE_ACC forced HDA off at the state level above;
        # also transition the registry-level HDA record so UI/audit readers
        # of the registry don't see a "started" HDA action that is actually
        # off. This re-invokes _stop_hda (idempotent — hda_active is already
        # False) purely for its ActiveActionEvent bookkeeping side effect.
        for hda_record in registry.get_active_actions(session_id=record.session_id):
            if hda_record.intent != "activate_hda":
                continue
            try:
                registry.stop_action(
                    hda_record.action_id,
                    reason=f"cascaded_from_aac_stop:{reason}",
                    turn_id=record.turn_id,
                )
            except (ValueError, KeyError):
                pass  # already terminal/missing — idempotent, not an error

    registry.register_stop_handler("activate_hda", _stop_hda)
    registry.register_stop_handler("activate_aac", _stop_aac)


# ---------------------------------------------------------------------------
# 3. Grounded stop/fail responses + pure (state-free) monitor result reading.
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


class AdasMonitorHeroBehavior:
    """Reference HDA/AAC interpretation of Guardrail monitor decisions.

    Every method here reads only the Guardrail-produced monitor result (or
    the registry record) — never vehicle telemetry (speed, hands-on-wheel,
    battery, ...). That is a deliberate, structural guarantee: the Agent must
    not reason about *why* a monitored action should stop, only relay
    Guardrail's *outcome*. See module docstring.
    """

    MONITORED_INTENTS: frozenset[str] = HDA_AAC_INTENTS

    @classmethod
    def evaluate_monitor_result(cls, monitor_result: Mapping[str, Any]) -> MonitorOutcome:
        """Interpret one result dict from ``GuardrailMonitorAdapter.tick()``/
        ``evaluate_active_actions()`` — pure dict-in, dict-out, no state.
        """
        intent = str(monitor_result.get("intent", ""))
        if intent not in cls.MONITORED_INTENTS:
            raise ValueError(
                f"AdasMonitorHeroBehavior only handles {sorted(cls.MONITORED_INTENTS)}, got {intent!r}"
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
        """Grounded Vietnamese stop notice — cites only real reason_code/rule_id."""
        outcome = cls.evaluate_monitor_result(monitor_result)
        display_name = _DISPLAY_NAMES.get(record.intent, record.active_action_name)
        reason = outcome.reason_code or "yêu cầu an toàn từ Guardrail"
        rule = outcome.rule_id or "không xác định"
        return (
            f"{display_name} đã dừng theo yêu cầu của Guardrail "
            f"(rule_id={rule}, reason_code={reason})."
        )

    @classmethod
    def build_fail_message(cls, record: ActiveActionRecord, error: str) -> str:
        """Grounded Vietnamese failure notice for a fail-safe monitor-error stop."""
        display_name = _DISPLAY_NAMES.get(record.intent, record.active_action_name)
        return f"{display_name} đã dừng do lỗi giám sát an toàn: {error}."
