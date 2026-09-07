"""HERO-03 — Autopark/Camp mode hero behaviors.

Closes the same wiring gap HERO-02 closed for ``activate_hda``/``activate_aac``
(see ``src/vehicle_agent/adapters/monitor/mon-adp-01/DEFERRED_FOLLOWUPS.md``, gap
#1), now **for ``activate_autopark``/``activate_campmode`` only** —
``activate_petmode`` remains open, deferred past HERO-03.

Before this module: nothing ever called ``registry.start_action()`` for
autopark/camp mode, so a running instance was invisible to
``GuardrailMonitorAdapter``'s monitor loop; and nothing ever called
``registry.register_stop_handler(...)`` for them, so a Guardrail monitor stop
decision only flipped the in-memory :class:`ActiveActionRecord` phase — the
real :class:`VehicleState` (``adas.autopark_state``, ``modes.camp_mode_active``)
never actually changed.

Design notes
------------
- Shared plumbing (registry bridging, SYSTEM-actor state patch boilerplate,
  the grounded-message/monitor-relay base class) lives in
  ``_active_action_common.py`` — see that module's docstring. This file only
  contains what is genuinely specific to autopark/camp mode.
- Camp mode's ``camp_mode_active`` bool *is* set by ``ActiveActionHandler`` on
  start (``BehaviorConfig`` declares ``target_substate``/``target_field`` for
  it — see ``behaviors/catalog.py``), unlike autopark's ``autopark_state``
  (an :class:`AutoparkState` enum, intentionally left for vehicle/monitor
  telemetry feedback to set — same reasoning as HDA/AAC's enum fields, per
  the catalog's ADAS section comments). Both stop handlers below are
  idempotent no-ops if the field is already off, so they're safe to call
  regardless of whether the "engaged" transition ever actually landed.
- ``AutoparkCampmodeMonitorHeroBehavior`` deliberately contains **no vehicle-
  state inspection** — it only relays Guardrail's monitor outcome (e.g. camp
  mode's real self-cancel condition is ``battery_pct < MODE_BATTERY_ABORT_PCT``,
  a Guardrail policy threshold this class never reads or re-derives).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Mapping

from vehicle_agent.active_actions.models import ActiveActionRecord
from vehicle_agent.active_actions.registry import ActiveActionRegistry
from vehicle_agent.behaviors.hero._active_action_common import (
    MonitoredActionHeroBehaviorBase,
    apply_monitor_stop_patch,
    assert_subset_of_monitored_intents,
    bridge_active_action_handler,
    drop_active_action,
    is_restart_supersede,
)
from vehicle_agent.vehicle.execution.generic import BehaviorConfig
from vehicle_agent.vehicle.state.machine import VehicleStateMachine
from vehicle_agent.vehicle.state.model import AutoparkState, VehicleState

# The only two intents this module is responsible for. Kept as a frozen set
# (rather than reusing the broader MONITORED_INTENTS from catalog.manifest) so
# this module fails loudly if ever asked to handle an intent outside its
# HERO-03 scope (e.g. activate_petmode), instead of silently behaving as if
# that intent's wiring were already done.
AUTOPARK_CAMPMODE_INTENTS: frozenset[str] = frozenset({"activate_autopark", "activate_campmode"})
assert_subset_of_monitored_intents(AUTOPARK_CAMPMODE_INTENTS, label="AUTOPARK_CAMPMODE_INTENTS")

# Display names match src/vehicle_agent/queries/knowledge.py's FeatureKnowledge
# entries for "auto_park"/"camp_mode" so a stop/fail notice and a knowledge
# lookup never disagree on what to call the feature.
_DISPLAY_NAMES: dict[str, str] = {
    "activate_autopark": "Tự động đỗ xe (Autopark)",
    "activate_campmode": "Chế độ cắm trại (Camp Mode)",
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
    ``ActiveActionHandler`` for ``activate_autopark``/``activate_campmode``
    only — the wrapped callable's return value (state_version/facts/message)
    is unchanged, so it is a drop-in replacement for the gateway.

    Raises
    ------
    ValueError
        If ``config.intent_id`` is outside :data:`AUTOPARK_CAMPMODE_INTENTS`.
    """
    return bridge_active_action_handler(
        config,
        state_machine,
        registry,
        allowed_intents=AUTOPARK_CAMPMODE_INTENTS,
        scope_name="make_monitored_active_action_handler",
        actor_id=actor_id,
    )


# ---------------------------------------------------------------------------
# 2. Autopark/camp mode monitor-stop handling — the fail-safe state mutation
#    that was completely missing (DEFERRED_FOLLOWUPS.md gap #1).
# ---------------------------------------------------------------------------


def _apply_autopark_off(state_machine: VehicleStateMachine, record: ActiveActionRecord) -> None:
    """Turn ``adas.autopark_state`` off and drop the matching active_action entry."""
    current = state_machine.snapshot()
    already_off = current.adas.autopark_state is AutoparkState.OFF
    if already_off and all(a.action_id != record.action_id for a in current.active_actions):
        return  # already off, nothing to clean up — skip a wasted apply()/event

    def patch_fn(state: VehicleState) -> VehicleState:
        remaining = drop_active_action(state, record.action_id)
        new_adas = (
            replace(state.adas, autopark_state=AutoparkState.OFF)
            if state.adas.autopark_state is not AutoparkState.OFF
            else state.adas
        )
        return replace(state, adas=new_adas, active_actions=remaining)

    apply_monitor_stop_patch(state_machine, record, patch_fn)


def _apply_campmode_off(state_machine: VehicleStateMachine, record: ActiveActionRecord) -> None:
    """Turn ``modes.camp_mode_active`` off and drop the matching active_action entry."""
    current = state_machine.snapshot()
    if not current.modes.camp_mode_active and all(a.action_id != record.action_id for a in current.active_actions):
        return  # already off, nothing to clean up — skip a wasted apply()/event

    def patch_fn(state: VehicleState) -> VehicleState:
        remaining = drop_active_action(state, record.action_id)
        new_modes = (
            replace(state.modes, camp_mode_active=False) if state.modes.camp_mode_active else state.modes
        )
        return replace(state, modes=new_modes, active_actions=remaining)

    apply_monitor_stop_patch(state_machine, record, patch_fn)


def register_autopark_campmode_stop_handlers(
    registry: ActiveActionRegistry,
    state_machine: VehicleStateMachine,
) -> None:
    """Register the fail-safe stop handlers MON-ADP-01 relies on.

    Before this, ``registry.register_stop_handler(...)`` was never called for
    ``activate_autopark``/``activate_campmode``, so a Guardrail monitor stop
    only flipped the in-memory :class:`ActiveActionRecord` phase — the
    vehicle itself never actually stopped. This wires the real state
    mutation for both.
    """

    def _stop_autopark(record: ActiveActionRecord, reason: str) -> None:
        if is_restart_supersede(reason):
            # A same-session restart, not a real stop: a fresh
            # activate_autopark record already exists and now owns
            # adas.autopark_state.
            return
        _apply_autopark_off(state_machine, record)

    def _stop_campmode(record: ActiveActionRecord, reason: str) -> None:
        if is_restart_supersede(reason):
            return  # same rationale as _stop_autopark above
        _apply_campmode_off(state_machine, record)

    registry.register_stop_handler("activate_autopark", _stop_autopark)
    registry.register_stop_handler("activate_campmode", _stop_campmode)


# ---------------------------------------------------------------------------
# 3. Grounded stop/fail responses + pure (state-free) monitor result reading.
#    Shared mechanics live in MonitoredActionHeroBehaviorBase — see
#    _active_action_common.py.
# ---------------------------------------------------------------------------


class AutoparkCampmodeMonitorHeroBehavior(MonitoredActionHeroBehaviorBase):
    """Reference autopark/camp mode interpretation of Guardrail monitor decisions.

    See :class:`MonitoredActionHeroBehaviorBase` for the no-local-policy
    guarantee this class inherits.
    """

    # Named distinctly from catalog.manifest.MONITORED_INTENTS (5 entries) —
    # this is the narrower set *this class* handles, not every intent
    # Guardrail monitors. AUTOPARK_CAMPMODE_INTENTS's own module-level
    # assertion above keeps it a subset of the catalog's set, so the two
    # can't silently drift.
    HANDLED_INTENTS: frozenset[str] = AUTOPARK_CAMPMODE_INTENTS
    # Defensive copy: a class attribute bound directly to the module-level
    # dict would let an in-place mutation of DISPLAY_NAMES on this class leak
    # back into _DISPLAY_NAMES (and therefore every other user of it).
    DISPLAY_NAMES: dict[str, str] = dict(_DISPLAY_NAMES)
