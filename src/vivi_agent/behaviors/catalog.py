"""Behavior Catalog — 47 action/UI intent declarations.

Every action/UI intent from the ViVi intent manifest v1 has exactly one
``BehaviorConfig`` entry here.  Query intents (kind=query) do NOT appear —
they are handled by the Query Responder (QRY-01).  The explicit refusal
(``deactivate_esc``) is registered in ``refusal.py``, not here.

Catalog contents:
    - 46 executable action behaviors
    -  1 explicit refusal  (deactivate_esc) — declared in refusal.py
    ─────────────────────────────────────────
    = 47 total behavior entries (acceptance criteria: 47/47)
"""

from __future__ import annotations

from vivi_agent.vehicle.execution.generic import BehaviorConfig, BehaviorHandlerType
from vivi_agent.vehicle.state.model import (
    AccState,
    AutoparkState,
    DriveMode,
    Gear,
    LightMode,
)

# ---------------------------------------------------------------------------
# Helper aliases for readability
# ---------------------------------------------------------------------------
_T = BehaviorHandlerType.TOGGLE
_EN = BehaviorHandlerType.ENUM_SETTER
_ACC = BehaviorHandlerType.ACCESS
_POS = BehaviorHandlerType.POSITION
_TIM = BehaviorHandlerType.TIMED
_ONE = BehaviorHandlerType.ONE_SHOT
_ACT = BehaviorHandlerType.ACTIVE_ACTION
_COMP = BehaviorHandlerType.COMPOUND


# ===========================================================================
# 1. LIGHTS — 9 toggle + 2 compound hazard + 1 toggle cornering + 1 interior
# ===========================================================================

_LIGHTS: tuple[BehaviorConfig, ...] = (
    # High-beam
    BehaviorConfig(
        intent_id="turnon_highbeam",
        handler_type=_EN,
        target_substate="lighting",
        target_field="highbeam",
        enum_cls=LightMode,
        default_value=LightMode.ON,
    ),
    BehaviorConfig(
        intent_id="turnoff_highbeam",
        handler_type=_EN,
        target_substate="lighting",
        target_field="highbeam",
        enum_cls=LightMode,
        default_value=LightMode.OFF,
    ),
    # Low-beam
    BehaviorConfig(
        intent_id="turnon_lowbeam",
        handler_type=_EN,
        target_substate="lighting",
        target_field="lowbeam",
        enum_cls=LightMode,
        default_value=LightMode.ON,
    ),
    BehaviorConfig(
        intent_id="turnoff_lowbeam",
        handler_type=_EN,
        target_substate="lighting",
        target_field="lowbeam",
        enum_cls=LightMode,
        default_value=LightMode.OFF,
    ),
    # Auto high-beam (AHB)
    BehaviorConfig(
        intent_id="activate_ahb",
        handler_type=_T,
        target_substate="adas",
        target_field="auto_highbeam_active",
        param_name="state",
    ),
    # Turn signals
    BehaviorConfig(
        intent_id="turnon_turnsignal_right",
        handler_type=_T,
        target_substate="lighting",
        target_field="right_turn_signal",
        default_value=True,
    ),
    BehaviorConfig(
        intent_id="turnoff_turnsignal_right",
        handler_type=_T,
        target_substate="lighting",
        target_field="right_turn_signal",
        default_value=False,
    ),
    BehaviorConfig(
        intent_id="turnon_turnsignal_left",
        handler_type=_T,
        target_substate="lighting",
        target_field="left_turn_signal",
        default_value=True,
    ),
    BehaviorConfig(
        intent_id="turnoff_turnsignal_left",
        handler_type=_T,
        target_substate="lighting",
        target_field="left_turn_signal",
        default_value=False,
    ),
    # Hazard lights — compound: both left AND right turn signals simultaneously
    BehaviorConfig(
        intent_id="turnon_hazardlight",
        handler_type=_COMP,
        sub_configs=(
            BehaviorConfig(
                intent_id="turnon_hazardlight__left",
                handler_type=_T,
                target_substate="lighting",
                target_field="left_turn_signal",
                default_value=True,
            ),
            BehaviorConfig(
                intent_id="turnon_hazardlight__right",
                handler_type=_T,
                target_substate="lighting",
                target_field="right_turn_signal",
                default_value=True,
            ),
            BehaviorConfig(
                intent_id="turnon_hazardlight__flag",
                handler_type=_T,
                target_substate="lighting",
                target_field="hazard_light",
                default_value=True,
            ),
        ),
    ),
    BehaviorConfig(
        intent_id="turnoff_hazardlight",
        handler_type=_COMP,
        sub_configs=(
            BehaviorConfig(
                intent_id="turnoff_hazardlight__left",
                handler_type=_T,
                target_substate="lighting",
                target_field="left_turn_signal",
                default_value=False,
            ),
            BehaviorConfig(
                intent_id="turnoff_hazardlight__right",
                handler_type=_T,
                target_substate="lighting",
                target_field="right_turn_signal",
                default_value=False,
            ),
            BehaviorConfig(
                intent_id="turnoff_hazardlight__flag",
                handler_type=_T,
                target_substate="lighting",
                target_field="hazard_light",
                default_value=False,
            ),
        ),
    ),
    # Cornering light
    BehaviorConfig(
        intent_id="turnon_corneringlight",
        handler_type=_T,
        target_substate="lighting",
        target_field="cornering_light",
        default_value=True,
    ),
    # Interior light
    BehaviorConfig(
        intent_id="turnon_interiorlight",
        handler_type=_T,
        target_substate="lighting",
        target_field="interior_light",
        default_value=True,
    ),
)

# ===========================================================================
# 2. ACCESS — doors, trunk, bonnet, charge port, bulk lock/unlock
# ===========================================================================

_ACCESS: tuple[BehaviorConfig, ...] = (
    # Per-door open (requires `door` param)
    BehaviorConfig(
        intent_id="open_door",
        handler_type=_ACC,
        event_name="door_opened",
    ),
    # Trunk
    BehaviorConfig(
        intent_id="open_trunk",
        handler_type=_T,
        target_substate="access",
        target_field="trunk_open",
        default_value=True,
    ),
    # Charge port
    BehaviorConfig(
        intent_id="open_chargeport",
        handler_type=_T,
        target_substate="access",
        target_field="charge_port_open",
        default_value=True,
    ),
    # Bonnet / frunk
    BehaviorConfig(
        intent_id="OPEN_BONNET",
        handler_type=_T,
        target_substate="access",
        target_field="bonnet_open",
        default_value=True,
    ),
    # Bulk lock all doors — ONE_SHOT event commanding vehicle to lock all doors.
    # Note: individual DoorState.lock mutation requires per-door AccessActuatorHandler
    # which needs an explicit door target param. Bulk lock is a vehicle-level command;
    # actual DoorState.lock is updated via telemetry feedback (outside agent scope).
    BehaviorConfig(
        intent_id="lock_doors",
        handler_type=_ONE,
        event_name="bulk_lock_all_doors_commanded",
    ),
    # Bulk unlock all doors — symmetric ONE_SHOT event
    BehaviorConfig(
        intent_id="unlock_doors",
        handler_type=_ONE,
        event_name="bulk_unlock_all_doors_commanded",
    ),
)

# ===========================================================================
# 3. CABIN — wiper, seat, window, sunroof, mirrors, HUD
# ===========================================================================

_CABIN: tuple[BehaviorConfig, ...] = (
    # Wiper max — no wiper field in VehicleState v1; fire one-shot event
    BehaviorConfig(
        intent_id="AD_WIPER_MAX",
        handler_type=_ONE,
        event_name="cabin_wiper_max_event",
    ),
    # Steering wheel adjust (up/down via delta param on a virtual position field)
    # CabinState has no steering field; fire one-shot event preserving intent semantics
    BehaviorConfig(
        intent_id="ad_steeringwheel",
        handler_type=_ONE,
        event_name="cabin_steeringwheel_adjust_event",
    ),
    # Driver seat — forward/backward (position on 0–1 axis)
    BehaviorConfig(
        intent_id="ad_driverseat_pos",
        handler_type=_POS,
        target_substate="cabin",
        target_field="driver_seat_position",
        param_name="position",
        value_range=(0.0, 1.0),
    ),
    # Driver seat angle (recline)
    BehaviorConfig(
        intent_id="ad_driverseat_angle",
        handler_type=_POS,
        target_substate="cabin",
        target_field="driver_seat_angle",
        param_name="angle",
        value_range=(0.0, 1.0),
    ),
    # Restore driver seat to defaults — compound: reset both position + angle
    BehaviorConfig(
        intent_id="restore_driverseat_pos",
        handler_type=_COMP,
        sub_configs=(
            BehaviorConfig(
                intent_id="restore_driverseat_pos__position",
                handler_type=_POS,
                target_substate="cabin",
                target_field="driver_seat_position",
                default_value=0.5,
                value_range=(0.0, 1.0),
            ),
            BehaviorConfig(
                intent_id="restore_driverseat_pos__angle",
                handler_type=_POS,
                target_substate="cabin",
                target_field="driver_seat_angle",
                default_value=0.5,
                value_range=(0.0, 1.0),
            ),
        ),
    ),
    # Rear seat fold (timed operation)
    BehaviorConfig(
        intent_id="fold_backseat",
        handler_type=_TIM,
        target_substate="cabin",
        target_field="rear_seat_folded",
        duration_seconds=5.0,
    ),
    # Window open/close — aggregate bool on CabinState
    BehaviorConfig(
        intent_id="open_window",
        handler_type=_T,
        target_substate="cabin",
        target_field="windows_open",
        default_value=True,
    ),
    # Sunroof open/close — toggle bool field on CabinState (True=open, False=closed)
    BehaviorConfig(
        intent_id="open_sunroof",
        handler_type=_T,
        target_substate="cabin",
        target_field="sunroof_open",
        default_value=True,
    ),
    # Mirrors fold (timed)
    BehaviorConfig(
        intent_id="fold_mirrors",
        handler_type=_TIM,
        target_substate="cabin",
        target_field="mirrors_folded",
        duration_seconds=3.0,
    ),
    # HUD deactivate
    BehaviorConfig(
        intent_id="deactivate_hud",
        handler_type=_T,
        target_substate="cabin",
        target_field="hud_active",
        default_value=False,
    ),
)

# ===========================================================================
# 4. DRIVE MODES — enum_setter on modes.drive_mode
# ===========================================================================

_DRIVE_MODES: tuple[BehaviorConfig, ...] = (
    BehaviorConfig(
        intent_id="switch_drivemode_sport",
        handler_type=_EN,
        target_substate="modes",
        target_field="drive_mode",
        enum_cls=DriveMode,
        default_value=DriveMode.SPORT,
    ),
    BehaviorConfig(
        intent_id="switch_drivemode_eco",
        handler_type=_EN,
        target_substate="modes",
        target_field="drive_mode",
        enum_cls=DriveMode,
        default_value=DriveMode.ECO,
    ),
    BehaviorConfig(
        intent_id="switch_drivemode_normal",
        handler_type=_EN,
        target_substate="modes",
        target_field="drive_mode",
        enum_cls=DriveMode,
        default_value=DriveMode.NORMAL,
    ),
)

# ===========================================================================
# 5. SPECIAL MODES — active_action (monitored by Guardrail)
# ===========================================================================

_SPECIAL_MODES: tuple[BehaviorConfig, ...] = (
    BehaviorConfig(
        intent_id="activate_campmode",
        handler_type=_ACT,
        target_substate="modes",
        target_field="camp_mode_active",
        active_action_name="camp_mode",
    ),
    BehaviorConfig(
        intent_id="activate_petmode",
        handler_type=_ACT,
        target_substate="modes",
        target_field="pet_mode_active",
        active_action_name="pet_mode",
    ),
    BehaviorConfig(
        intent_id="activate_valetmode",
        handler_type=_ACT,
        target_substate="modes",
        target_field="valet_mode_active",
        active_action_name="valet_mode",
    ),
    # Creep mode — simple toggle (not monitored)
    BehaviorConfig(
        intent_id="activate_creepmode",
        handler_type=_T,
        target_substate="modes",
        target_field="creep_mode_active",
        param_name="state",
    ),
)

# ===========================================================================
# 6. TRANSMISSION — gear shifts, EPB
# ===========================================================================

_TRANSMISSION: tuple[BehaviorConfig, ...] = (
    BehaviorConfig(
        intent_id="SHIFT_GEAR_REVERSE",
        handler_type=_EN,
        target_substate="transmission",
        target_field="gear",
        enum_cls=Gear,
        default_value=Gear.REVERSE,
    ),
    BehaviorConfig(
        intent_id="shift_gear_park",
        handler_type=_EN,
        target_substate="transmission",
        target_field="gear",
        enum_cls=Gear,
        default_value=Gear.PARK,
    ),
    # Electric parking brake
    BehaviorConfig(
        intent_id="activate_epb",
        handler_type=_T,
        target_substate="transmission",
        target_field="epb_engaged",
        param_name="state",
    ),
)

# ===========================================================================
# 7. ADAS — active_action (monitored) + toggles
# ===========================================================================

_ADAS: tuple[BehaviorConfig, ...] = (
    # Autopark — active action monitored by Guardrail (R048).
    # target_substate/target_field intentionally omitted: autopark_state is AutoparkState
    # (Enum), and ActiveActionHandler only sets bool. Actual autopark_state transition is
    # managed by the Guardrail monitor (MON-ADP-01) via vehicle telemetry feedback.
    BehaviorConfig(
        intent_id="activate_autopark",
        handler_type=_ACT,
        active_action_name="autopark",
    ),
    # AAC (Adaptive Cruise Control) — active action (R070).
    # acc_state is AccState (Enum) — omit target fields; monitor handles state transition.
    BehaviorConfig(
        intent_id="activate_aac",
        handler_type=_ACT,
        active_action_name="aac",
    ),
    # HDA (Highway Driving Assist) — active action (R073).
    # target_substate/target_field intentionally omitted: setting hda_active=True directly
    # violates the AdasState invariant (HDA_REQUIRES_ACTIVE_ACC) unless acc_state is already
    # ACTIVE. The actual hda_active transition is managed by the vehicle and monitor.
    BehaviorConfig(
        intent_id="activate_hda",
        handler_type=_ACT,
        active_action_name="hda",
    ),
    # LKA turn off
    BehaviorConfig(
        intent_id="turnoff_LKA",
        handler_type=_T,
        target_substate="adas",
        target_field="lane_keep_assist_active",
        default_value=False,
    ),
    # TCS
    BehaviorConfig(
        intent_id="activate_tcs",
        handler_type=_T,
        target_substate="adas",
        target_field="tcs_active",
        default_value=True,
    ),
    # AVH (Auto Vehicle Hold)
    BehaviorConfig(
        intent_id="activate_avh",
        handler_type=_T,
        target_substate="adas",
        target_field="avh_active",
        default_value=True,
    ),
)

# ===========================================================================
# 8. UI — one-shot events
# ===========================================================================

_UI: tuple[BehaviorConfig, ...] = (
    BehaviorConfig(
        intent_id="open_noti_center",
        handler_type=_ONE,
        target_substate="ui",
        target_field="notification_center_open",
        event_name="ui_notification_center_opened",
    ),
)

# ===========================================================================
# Full catalog (executable behaviors only — no query, no refusal)
# ===========================================================================

ACTION_BEHAVIOR_CONFIGS: tuple[BehaviorConfig, ...] = (
    *_LIGHTS,
    *_ACCESS,
    *_CABIN,
    *_DRIVE_MODES,
    *_SPECIAL_MODES,
    *_TRANSMISSION,
    *_ADAS,
    *_UI,
)

# The intent IDs of all explicit refusals (re-exported from refusal.py for single source of truth)
from vivi_agent.behaviors.refusal import REFUSAL_INTENT_IDS

# Behavior catalog containing all executable action behavior configs.
# Refusals (e.g. deactivate_esc) are defined separately in refusal.py,
# and query intents are intentionally excluded.
BEHAVIOR_CATALOG: tuple[BehaviorConfig, ...] = ACTION_BEHAVIOR_CONFIGS


def get_behavior_config(intent_id: str) -> BehaviorConfig | None:
    """Return the ``BehaviorConfig`` for *intent_id*, or ``None`` if not found."""
    for cfg in ACTION_BEHAVIOR_CONFIGS:
        if cfg.intent_id == intent_id:
            return cfg
    return None
