"""Deterministic ``(tool, action, target, value) -> intent`` mapping.

On the Agent authorization path the ``ActionProposal`` carries only ``tool`` +
``arguments`` -- no intent. The Guardrail must recover the intent *independently*,
using the exact same table the Agent used, so that the Agent's
``_validate_decision_correlation`` check (``decision.intent == agent_mapped_intent``)
holds. Decision D1 forbids importing Agent code in production, so the table is
**copied** here and a conformance test (``tests/test_tool_map.py``) compares it
row-by-row against ``vehicle_agent.tools.mapping.mapper.DEFAULT_MAPPING_RULES``;
any drift turns that test red.

Scope: the 79 explicit rows of the Agent table (every row whose ``tool`` is not
``control_vehicle_capability``). Those cover all 53 workbook intents plus
``turnon_LKA`` (which has a mapping but no workbook rule -> the engine
fail-closes on it, which the service surfaces as a typed error, never ALLOW).
The 69 ``control_vehicle_capability`` "candidate" rows are Agent-only future
capabilities with no workbook policy and are deliberately out of scope.

Lookup is exact. A tool call that does not match a reviewed row fails closed
with ``UNSUPPORTED_TOOL_MAPPING`` -- never a guessed intent, never an outcome.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

MappingKey = tuple[str, str, str, str | None]


class ToolMappingError(ValueError):
    """A valid-looking tool call has no exact reviewed mapping. Fail closed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.execution_allowed = False


class ToolMapReadinessError(RuntimeError):
    """The copied table itself is duplicated/ambiguous. Fail closed at import."""


@dataclass(frozen=True)
class MappingRule:
    """Mirror of ``vehicle_agent.tools.mapping.mapper.MappingRule`` (field order incl.)."""

    tool_name: str
    action: str
    target: str
    intent: str
    value: str | None = None

    @property
    def key(self) -> MappingKey:
        return (self.tool_name, self.action, self.target, self.value)


def _M(  # noqa: N802 - deliberately terse, one call per table row
    tool_name: str, action: str, target: str, intent: str, value: str | None = None
) -> MappingRule:
    return MappingRule(tool_name, action, target, intent, value)


# --- verbatim copy of the Agent's explicit rows (see module docstring) --------
DEFAULT_MAPPING_RULES: tuple[MappingRule, ...] = (
    # control_access
    _M("control_access", "open", "driver_door", "open_door"),
    _M("control_access", "open", "trunk", "open_trunk"),
    _M("control_access", "open", "charge_port", "open_chargeport"),
    _M("control_access", "open", "bonnet", "OPEN_BONNET"),
    _M("control_access", "lock", "all_doors", "lock_doors"),
    _M("control_access", "unlock", "all_doors", "unlock_doors"),
    # control_light
    _M("control_light", "turn_on", "high_beam", "turnon_highbeam"),
    _M("control_light", "turn_on", "low_beam", "turnon_lowbeam"),
    _M("control_light", "turn_on", "left_turn_signal", "turnon_turnsignal_left"),
    _M("control_light", "turn_on", "right_turn_signal", "turnon_turnsignal_right"),
    _M("control_light", "turn_on", "hazard_light", "turnon_hazardlight"),
    _M("control_light", "turn_on", "cornering_light", "turnon_corneringlight"),
    _M("control_light", "turn_on", "interior_light", "turnon_interiorlight"),
    _M("control_light", "turn_off", "high_beam", "turnoff_highbeam"),
    _M("control_light", "turn_off", "low_beam", "turnoff_lowbeam"),
    _M("control_light", "turn_off", "left_turn_signal", "turnoff_turnsignal_left"),
    _M("control_light", "turn_off", "right_turn_signal", "turnoff_turnsignal_right"),
    _M("control_light", "turn_off", "hazard_light", "turnoff_hazardlight"),
    _M("control_light", "activate", "automatic_high_beam", "activate_ahb"),
    # control_cabin
    _M("control_cabin", "set", "wiper", "AD_WIPER_MAX", "max"),
    _M("control_cabin", "adjust", "steering_wheel", "ad_steeringwheel", "forward"),
    _M("control_cabin", "adjust", "steering_wheel", "ad_steeringwheel", "backward"),
    _M("control_cabin", "adjust", "steering_wheel", "ad_steeringwheel", "up"),
    _M("control_cabin", "adjust", "steering_wheel", "ad_steeringwheel", "down"),
    _M("control_cabin", "adjust", "driver_seat_angle", "ad_driverseat_angle", "forward"),
    _M("control_cabin", "adjust", "driver_seat_angle", "ad_driverseat_angle", "backward"),
    _M("control_cabin", "adjust", "driver_seat_angle", "ad_driverseat_angle", "up"),
    _M("control_cabin", "adjust", "driver_seat_angle", "ad_driverseat_angle", "down"),
    _M("control_cabin", "adjust", "driver_seat_position", "ad_driverseat_pos", "forward"),
    _M("control_cabin", "adjust", "driver_seat_position", "ad_driverseat_pos", "backward"),
    _M("control_cabin", "adjust", "driver_seat_position", "ad_driverseat_pos", "up"),
    _M("control_cabin", "adjust", "driver_seat_position", "ad_driverseat_pos", "down"),
    _M("control_cabin", "fold", "back_seat", "fold_backseat"),
    _M("control_cabin", "fold", "mirrors", "fold_mirrors"),
    _M("control_cabin", "open", "sunroof", "open_sunroof"),
    _M("control_cabin", "open", "driver_window", "open_window"),
    _M("control_cabin", "open", "front_passenger_window", "open_window"),
    _M("control_cabin", "open", "rear_left_window", "open_window"),
    _M("control_cabin", "open", "rear_right_window", "open_window"),
    _M("control_cabin", "restore", "driver_seat_position", "restore_driverseat_pos"),
    # set_drive_mode
    _M("set_drive_mode", "set", "drive_mode", "switch_drivemode_eco", "eco"),
    _M("set_drive_mode", "set", "drive_mode", "switch_drivemode_normal", "normal"),
    _M("set_drive_mode", "set", "drive_mode", "switch_drivemode_sport", "sport"),
    # control_transmission
    _M("control_transmission", "shift", "gear", "shift_gear_park", "park"),
    _M("control_transmission", "shift", "gear", "SHIFT_GEAR_REVERSE", "reverse"),
    _M("control_transmission", "activate", "electronic_parking_brake", "activate_epb"),
    # control_driver_assistance
    _M("control_driver_assistance", "activate", "auto_park", "activate_autopark"),
    _M("control_driver_assistance", "activate", "adaptive_cruise_control", "activate_aac"),
    _M("control_driver_assistance", "activate", "highway_drive_assist", "activate_hda"),
    _M("control_driver_assistance", "activate", "traction_control", "activate_tcs"),
    _M("control_driver_assistance", "activate", "auto_vehicle_hold", "activate_avh"),
    _M("control_driver_assistance", "deactivate", "lane_keeping_assist", "turnoff_LKA"),
    _M("control_driver_assistance", "activate", "lane_keeping_assist", "turnon_LKA"),
    _M("control_driver_assistance", "deactivate", "electronic_stability_control", "deactivate_esc"),
    # control_special_mode
    _M("control_special_mode", "activate", "creep_mode", "activate_creepmode"),
    _M("control_special_mode", "activate", "camp_mode", "activate_campmode"),
    _M("control_special_mode", "activate", "pet_mode", "activate_petmode"),
    _M("control_special_mode", "activate", "valet_mode", "activate_valetmode"),
    # control_ui
    _M("control_ui", "open", "notification_center", "open_noti_center"),
    _M("control_ui", "deactivate", "head_up_display", "deactivate_hud"),
    # query_vehicle_state
    _M("query_vehicle_state", "get", "current_speed", "get_current_speed"),
    _M("query_vehicle_state", "get", "battery_percentage", "get_battery_pct"),
    _M("query_vehicle_state", "get", "gear", "get_gear"),
    _M("query_vehicle_state", "get", "door_lock_status", "get_door_lock_status"),
    _M("query_vehicle_state", "get", "auto_vehicle_hold_status", "get_avh_status"),
    # explain_vehicle_feature (target is the normalized `feature` parameter)
    _M("explain_vehicle_feature", "explain", "adaptive_cruise_control", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "auto_park", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "auto_vehicle_hold", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "automatic_high_beam", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "camp_mode", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "creep_mode", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "electronic_parking_brake", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "electronic_stability_control", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "head_up_display", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "highway_drive_assist", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "lane_keeping_assist", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "pet_mode", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "traction_control", "explain_feature"),
    _M("explain_vehicle_feature", "explain", "valet_mode", "explain_feature"),
)

# Query intents resolve to ANSWER/UNKNOWN via the query path, not an action permit.
QUERY_INTENTS: frozenset[str] = frozenset(
    r.intent for r in DEFAULT_MAPPING_RULES if r.tool_name == "query_vehicle_state"
)
EXPLAIN_INTENTS: frozenset[str] = frozenset(
    r.intent for r in DEFAULT_MAPPING_RULES if r.tool_name == "explain_vehicle_feature"
)
# The 14 feature ids the workbook's explain_feature rules (R108/R109) treat as
# "in the knowledge base". The Guardrail owns this list because R108/R109 gate on
# ``kb_has_feature`` -- the Agent still supplies the actual explanation text.
EXPLAIN_FEATURE_TARGETS: frozenset[str] = frozenset(
    r.target for r in DEFAULT_MAPPING_RULES if r.tool_name == "explain_vehicle_feature"
)


def _index(rules: tuple[MappingRule, ...]) -> Mapping[MappingKey, str]:
    table: dict[MappingKey, str] = {}
    for rule in rules:
        if rule.key in table:
            existing = table[rule.key]
            raise ToolMapReadinessError(
                f"{'DUPLICATE' if existing == rule.intent else 'AMBIGUOUS'}_MAPPING: "
                f"key {rule.key!r} -> {existing!r} and {rule.intent!r}"
            )
        table[rule.key] = rule.intent
    return MappingProxyType(table)


_TABLE: Mapping[MappingKey, str] = _index(DEFAULT_MAPPING_RULES)


class ToolMapper:
    """Resolve only exact, import-validated ``(tool, action, target, value)`` tuples."""

    def __init__(self, rules: tuple[MappingRule, ...] = DEFAULT_MAPPING_RULES) -> None:
        self._table = _TABLE if rules is DEFAULT_MAPPING_RULES else _index(rules)

    @property
    def intents(self) -> frozenset[str]:
        return frozenset(self._table.values())

    def resolve(self, tool: str, arguments: Mapping[str, Any]) -> str:
        """Return the mapped intent, or raise ``ToolMappingError`` (fail closed)."""

        if not isinstance(tool, str) or not tool:
            raise ToolMappingError("INVALID_TOOL", "tool must be a non-empty string")
        if not isinstance(arguments, Mapping):
            raise ToolMappingError("INVALID_ARGUMENTS", "arguments must be an object")
        for field in ("action", "target"):
            if not isinstance(arguments.get(field), str) or not arguments[field]:
                raise ToolMappingError(
                    "INCOMPLETE_TOOL_CALL", f"arguments.{field} is required"
                )
        raw_value = arguments.get("value")
        if raw_value is not None and not isinstance(raw_value, str):
            raise ToolMappingError("INVALID_ARGUMENTS", "arguments.value must be a string")

        key: MappingKey = (tool, arguments["action"], arguments["target"], raw_value)
        intent = self._table.get(key)
        if intent is None:
            raise ToolMappingError(
                "UNSUPPORTED_TOOL_MAPPING", f"no reviewed mapping for {key!r}"
            )
        return intent


DEFAULT_MAPPER = ToolMapper()
