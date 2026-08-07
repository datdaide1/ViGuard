"""HERO-02 — HDA/AAC active driving assist hero behaviors.

Closes the wiring gap left open by ACTV-01 (:class:`ActiveActionRegistry`) and
MON-ADP-01 (:class:`GuardrailMonitorAdapter`): neither module was ever
connected to anything else in the codebase, so a running ``activate_hda`` or
``activate_aac`` action was invisible to the monitor loop, and a Guardrail
monitor stop decision never reached the real :class:`VehicleState` (see
``src/vivi_agent/adapters/monitor/mon-adp-01/DEFERRED_FOLLOWUPS.md``, gap #1).

This module closes that gap **for ``activate_hda``/``activate_aac`` only** —
HERO-03 (:mod:`vivi_agent.behaviors.hero.autopark_campmode`) closes the same
gap for ``activate_autopark``/``activate_campmode``. ``activate_petmode``
remains open.

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

from dataclasses import replace
from typing import Any, Callable, Mapping

from vivi_agent.active_actions.models import ActiveActionRecord
from vivi_agent.active_actions.registry import ActiveActionRegistry
from vivi_agent.behaviors.hero._active_action_common import (
    MonitoredActionHeroBehaviorBase,
    apply_monitor_stop_patch,
    assert_subset_of_monitored_intents,
    bridge_active_action_handler,
    drop_active_action,
    is_restart_supersede,
)
from vivi_agent.vehicle.execution.generic import BehaviorConfig
from vivi_agent.vehicle.state.machine import VehicleStateMachine
from vivi_agent.vehicle.state.model import AccState, VehicleState

# The only two intents this module is responsible for. Kept as a frozen set
# (rather than reusing the broader MONITORED_INTENTS from catalog.manifest)
# so this module fails loudly if ever asked to handle an intent outside its
# HERO-02 scope, instead of silently behaving as if HERO-03 were already done.
HDA_AAC_INTENTS: frozenset[str] = frozenset({"activate_hda", "activate_aac"})
assert_subset_of_monitored_intents(HDA_AAC_INTENTS, label="HDA_AAC_INTENTS")

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
    return bridge_active_action_handler(
        config,
        state_machine,
        registry,
        allowed_intents=HDA_AAC_INTENTS,
        scope_name="make_monitored_active_action_handler",
        actor_id=actor_id,
    )


# ---------------------------------------------------------------------------
# 2. HDA monitor-stop handling — the actual fail-safe state mutation that was
#    completely missing (DEFERRED_FOLLOWUPS.md gap #1).
# ---------------------------------------------------------------------------


def _apply_hda_off(state_machine: VehicleStateMachine, record: ActiveActionRecord) -> None:
    """Turn ``adas.hda_active`` off and drop the matching active_action entry."""
    current = state_machine.snapshot()
    if not current.adas.hda_active and all(a.action_id != record.action_id for a in current.active_actions):
        return  # already off, nothing to clean up — skip a wasted apply()/event

    def patch_fn(state: VehicleState) -> VehicleState:
        remaining = drop_active_action(state, record.action_id)
        new_adas = replace(state.adas, hda_active=False) if state.adas.hda_active else state.adas
        return replace(state, adas=new_adas, active_actions=remaining)

    apply_monitor_stop_patch(state_machine, record, patch_fn)


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
        remaining = drop_active_action(state, record.action_id)
        if cascaded:
            remaining = tuple(a for a in remaining if a.intent != "activate_hda")
        return replace(state, adas=new_adas, active_actions=remaining)

    apply_monitor_stop_patch(state_machine, record, patch_fn)
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

    def _stop_hda(record: ActiveActionRecord, reason: str) -> None:
        if is_restart_supersede(reason):
            # A same-session restart, not a real stop: a fresh activate_hda
            # record already exists and now owns adas.hda_active.
            return
        _apply_hda_off(state_machine, record)

    def _stop_aac(record: ActiveActionRecord, reason: str) -> None:
        if is_restart_supersede(reason):
            return  # same rationale as _stop_hda above
        hda_cascaded = _apply_aac_cancelled(state_machine, record)
        if not hda_cascaded:
            return
        # HDA_REQUIRES_ACTIVE_ACC forced HDA off at the state level above;
        # also transition the registry-level HDA record so UI/audit readers
        # don't see a "started" HDA action that is actually off.
        # _apply_hda_off's own no-op guard makes this safe (no extra
        # state_version bump/event) even though the state mutation already
        # happened above.
        hda_record = registry.get_running_action(record.session_id, "activate_hda")
        if hda_record is None:
            return
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
#    Shared mechanics live in MonitoredActionHeroBehaviorBase — see
#    _active_action_common.py.
# ---------------------------------------------------------------------------


class AdasMonitorHeroBehavior(MonitoredActionHeroBehaviorBase):
    """Reference HDA/AAC interpretation of Guardrail monitor decisions.

    See :class:`MonitoredActionHeroBehaviorBase` for the no-local-policy
    guarantee this class inherits.
    """

    # Named distinctly from catalog.manifest.MONITORED_INTENTS (5 entries) —
    # this is the narrower set *this class* handles, not every intent
    # Guardrail monitors. HDA_AAC_INTENTS's own module-level assertion above
    # keeps it a subset of the catalog's set, so the two can't silently drift.
    HANDLED_INTENTS: frozenset[str] = HDA_AAC_INTENTS
    # Defensive copy: a class attribute bound directly to the module-level
    # dict would let an in-place mutation of DISPLAY_NAMES on this class leak
    # back into _DISPLAY_NAMES (and therefore every other user of it).
    DISPLAY_NAMES: dict[str, str] = dict(_DISPLAY_NAMES)
