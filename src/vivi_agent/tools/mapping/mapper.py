"""Fail-closed mapping from validated model tool calls to policy intents.

MAP-01 delivered the first vertical-slice mapping only.  MAP-02 completes
coverage: every intent in the approved 53-intent manifest is reachable
through at least one exact `(tool, action, target, value)` mapping, and every
valid registry combination resolves to exactly one intent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from ...catalog.manifest import IntentManifest
from ...catalog.candidate import CANDIDATE_CAPABILITIES
from ...authorization import (
    AuthorizationContractError,
    authorization_request_digest,
    validate_action_proposal,
)
from ..registry import ClarificationRequest, ToolRegistry, ValidatedToolCall

MappingKey = tuple[str, str, str, str | None]


def _mapping_key(tool_name: str, arguments: Mapping[str, str]) -> MappingKey:
    """Build the single canonical lookup key used at startup and runtime."""

    return (
        tool_name,
        arguments["action"],
        arguments["target"],
        arguments.get("value"),
    )


class MappingReadinessError(RuntimeError):
    """Raised when reviewed mappings are invalid or ambiguous at startup."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.readiness = False


class UnsupportedToolMappingError(ValueError):
    """Raised before Guardrail when a valid tool call has no exact mapping."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.execution_allowed = False


@dataclass(frozen=True)
class MappingRule:
    tool_name: str
    action: str
    target: str
    intent: str
    value: str | None = None

    @property
    def key(self) -> MappingKey:
        arguments = {"action": self.action, "target": self.target}
        if self.value is not None:
            arguments["value"] = self.value
        return _mapping_key(self.tool_name, arguments)


@dataclass(frozen=True)
class CanonicalAction:
    intent: str
    normalized_arguments: Mapping[str, str]
    behavior_id: str
    policy_required: bool = True


@dataclass(frozen=True)
class MappingEvent:
    source_tool: str
    canonical_intent: str
    proposal_digest: str
    kind: str = "tool_mapped"

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "source_tool": self.source_tool,
            "canonical_intent": self.canonical_intent,
            "proposal_digest": self.proposal_digest,
        }


@dataclass(frozen=True)
class MappedProposal:
    canonical_action: CanonicalAction
    proposal_digest: str
    event: MappingEvent


@dataclass(frozen=True)
class MappingCoverageReport:
    """Non-raising analysis of a candidate rule set (MAP-02 coverage report).

    Unlike :meth:`ToolMapper._validate_rules` (which fails closed on the
    first defect found), this walks the entire candidate rule set and
    returns every finding at once, grouped by kind, for authoring/CI use.
    """

    missing_intents: tuple[str, ...]
    duplicate_keys: tuple[MappingKey, ...]
    ambiguous_keys: tuple[MappingKey, ...]

    @property
    def is_complete(self) -> bool:
        return not (self.missing_intents or self.duplicate_keys or self.ambiguous_keys)


def _sort_mapping_keys(keys: Iterable[MappingKey]) -> tuple[MappingKey, ...]:
    """Sort MappingKeys for stable, deterministic report output.

    The trailing `value` field is `str | None`; Python cannot compare `None`
    to `str`, so a plain `sorted()` over raw keys raises `TypeError` the
    moment two keys share every field except `value` where one is `None` and
    the other is a string. Substitute `""` for `None` for ordering purposes
    only (no real registry value is ever an empty string).
    """
    return tuple(sorted(keys, key=lambda key: (key[0], key[1], key[2], key[3] or "")))


def build_coverage_report(
    rules: tuple[MappingRule, ...], manifest: IntentManifest
) -> MappingCoverageReport:
    """Report missing/duplicate/ambiguous mapping IDs for a candidate rule set."""

    intents_by_key: dict[MappingKey, list[str]] = {}
    for rule in rules:
        intents_by_key.setdefault(rule.key, []).append(rule.intent)

    duplicate_keys = _sort_mapping_keys(
        key for key, intents in intents_by_key.items() if len(intents) > 1 and len(set(intents)) == 1
    )
    ambiguous_keys = _sort_mapping_keys(
        key for key, intents in intents_by_key.items() if len(set(intents)) > 1
    )

    covered_intents = {rule.intent for rule in rules}
    manifest_intents = {definition.intent for definition in manifest.intents}
    missing_intents = tuple(sorted(manifest_intents - covered_intents))

    return MappingCoverageReport(
        missing_intents=missing_intents,
        duplicate_keys=duplicate_keys,
        ambiguous_keys=ambiguous_keys,
    )


# Reviewed 53/53 intent coverage. One row per valid `domain_tools.v1.json`
# combination (78 total); five domain_tool groups intentionally repeat the
# same intent across several rows because the tool's `target`/`value`
# becomes a normalized parameter on that single intent (steering wheel /
# driver seat angle / driver seat position direction, window side, and
# explainable feature) rather than a distinct intent per combination.
DEFAULT_MAPPING_RULES = (
    # control_access
    MappingRule("control_access", "open", "driver_door", "open_door"),
    MappingRule("control_access", "open", "trunk", "open_trunk"),
    MappingRule("control_access", "open", "charge_port", "open_chargeport"),
    MappingRule("control_access", "open", "bonnet", "OPEN_BONNET"),
    MappingRule("control_access", "lock", "all_doors", "lock_doors"),
    MappingRule("control_access", "unlock", "all_doors", "unlock_doors"),
    # control_light
    MappingRule("control_light", "turn_on", "high_beam", "turnon_highbeam"),
    MappingRule("control_light", "turn_on", "low_beam", "turnon_lowbeam"),
    MappingRule("control_light", "turn_on", "left_turn_signal", "turnon_turnsignal_left"),
    MappingRule("control_light", "turn_on", "right_turn_signal", "turnon_turnsignal_right"),
    MappingRule("control_light", "turn_on", "hazard_light", "turnon_hazardlight"),
    MappingRule("control_light", "turn_on", "cornering_light", "turnon_corneringlight"),
    MappingRule("control_light", "turn_on", "interior_light", "turnon_interiorlight"),
    MappingRule("control_light", "turn_off", "high_beam", "turnoff_highbeam"),
    MappingRule("control_light", "turn_off", "low_beam", "turnoff_lowbeam"),
    MappingRule("control_light", "turn_off", "left_turn_signal", "turnoff_turnsignal_left"),
    MappingRule("control_light", "turn_off", "right_turn_signal", "turnoff_turnsignal_right"),
    MappingRule("control_light", "turn_off", "hazard_light", "turnoff_hazardlight"),
    MappingRule("control_light", "activate", "automatic_high_beam", "activate_ahb"),
    # control_cabin
    MappingRule("control_cabin", "set", "wiper", "AD_WIPER_MAX", value="max"),
    MappingRule("control_cabin", "adjust", "steering_wheel", "ad_steeringwheel", value="forward"),
    MappingRule("control_cabin", "adjust", "steering_wheel", "ad_steeringwheel", value="backward"),
    MappingRule("control_cabin", "adjust", "steering_wheel", "ad_steeringwheel", value="up"),
    MappingRule("control_cabin", "adjust", "steering_wheel", "ad_steeringwheel", value="down"),
    MappingRule("control_cabin", "adjust", "driver_seat_angle", "ad_driverseat_angle", value="forward"),
    MappingRule("control_cabin", "adjust", "driver_seat_angle", "ad_driverseat_angle", value="backward"),
    MappingRule("control_cabin", "adjust", "driver_seat_angle", "ad_driverseat_angle", value="up"),
    MappingRule("control_cabin", "adjust", "driver_seat_angle", "ad_driverseat_angle", value="down"),
    MappingRule("control_cabin", "adjust", "driver_seat_position", "ad_driverseat_pos", value="forward"),
    MappingRule("control_cabin", "adjust", "driver_seat_position", "ad_driverseat_pos", value="backward"),
    MappingRule("control_cabin", "adjust", "driver_seat_position", "ad_driverseat_pos", value="up"),
    MappingRule("control_cabin", "adjust", "driver_seat_position", "ad_driverseat_pos", value="down"),
    MappingRule("control_cabin", "fold", "back_seat", "fold_backseat"),
    MappingRule("control_cabin", "fold", "mirrors", "fold_mirrors"),
    MappingRule("control_cabin", "open", "sunroof", "open_sunroof"),
    MappingRule("control_cabin", "open", "driver_window", "open_window"),
    MappingRule("control_cabin", "open", "front_passenger_window", "open_window"),
    MappingRule("control_cabin", "open", "rear_left_window", "open_window"),
    MappingRule("control_cabin", "open", "rear_right_window", "open_window"),
    MappingRule("control_cabin", "restore", "driver_seat_position", "restore_driverseat_pos"),
    # set_drive_mode
    MappingRule("set_drive_mode", "set", "drive_mode", "switch_drivemode_eco", value="eco"),
    MappingRule("set_drive_mode", "set", "drive_mode", "switch_drivemode_normal", value="normal"),
    MappingRule("set_drive_mode", "set", "drive_mode", "switch_drivemode_sport", value="sport"),
    # control_transmission
    MappingRule("control_transmission", "shift", "gear", "shift_gear_park", value="park"),
    MappingRule("control_transmission", "shift", "gear", "SHIFT_GEAR_REVERSE", value="reverse"),
    MappingRule("control_transmission", "activate", "electronic_parking_brake", "activate_epb"),
    # control_driver_assistance
    MappingRule("control_driver_assistance", "activate", "auto_park", "activate_autopark"),
    MappingRule("control_driver_assistance", "activate", "adaptive_cruise_control", "activate_aac"),
    MappingRule("control_driver_assistance", "activate", "highway_drive_assist", "activate_hda"),
    MappingRule("control_driver_assistance", "activate", "traction_control", "activate_tcs"),
    MappingRule("control_driver_assistance", "activate", "auto_vehicle_hold", "activate_avh"),
    MappingRule("control_driver_assistance", "deactivate", "lane_keeping_assist", "turnoff_LKA"),
    MappingRule("control_driver_assistance", "activate", "lane_keeping_assist", "turnon_LKA"),
    MappingRule("control_driver_assistance", "deactivate", "electronic_stability_control", "deactivate_esc"),
    # control_special_mode
    MappingRule("control_special_mode", "activate", "creep_mode", "activate_creepmode"),
    MappingRule("control_special_mode", "activate", "camp_mode", "activate_campmode"),
    MappingRule("control_special_mode", "activate", "pet_mode", "activate_petmode"),
    MappingRule("control_special_mode", "activate", "valet_mode", "activate_valetmode"),
    # control_ui
    MappingRule("control_ui", "open", "notification_center", "open_noti_center"),
    MappingRule("control_ui", "deactivate", "head_up_display", "deactivate_hud"),
    # query_vehicle_state
    MappingRule("query_vehicle_state", "get", "current_speed", "get_current_speed"),
    MappingRule("query_vehicle_state", "get", "battery_percentage", "get_battery_pct"),
    MappingRule("query_vehicle_state", "get", "gear", "get_gear"),
    MappingRule("query_vehicle_state", "get", "door_lock_status", "get_door_lock_status"),
    MappingRule("query_vehicle_state", "get", "auto_vehicle_hold_status", "get_avh_status"),
    # explain_vehicle_feature (14 combinations -> 1 intent, `target` is the
    # normalized `feature` parameter)
    MappingRule("explain_vehicle_feature", "explain", "adaptive_cruise_control", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "auto_park", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "auto_vehicle_hold", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "automatic_high_beam", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "camp_mode", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "creep_mode", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "electronic_parking_brake", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "electronic_stability_control", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "head_up_display", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "highway_drive_assist", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "lane_keeping_assist", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "pet_mode", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "traction_control", "explain_feature"),
    MappingRule("explain_vehicle_feature", "explain", "valet_mode", "explain_feature"),
) + tuple(
    MappingRule(
        "control_vehicle_capability",
        item.operation,
        item.intent,
        item.intent,
        value="*" if item.requires_value else None,
    )
    for item in CANDIDATE_CAPABILITIES
    if item.intent != "turnon_LKA"
)


class ToolMapper:
    """Resolve only exact, startup-validated tool/action/target/value tuples."""

    def __init__(
        self,
        registry: ToolRegistry,
        manifest: IntentManifest,
        rules: tuple[MappingRule, ...] = DEFAULT_MAPPING_RULES,
    ) -> None:
        self._registry = registry
        self._manifest = manifest
        self._rules = self._validate_rules(rules)

    @property
    def rules(self) -> tuple[MappingRule, ...]:
        return tuple(self._rules.values())

    def _validate_rules(
        self, rules: tuple[MappingRule, ...]
    ) -> Mapping[MappingKey, MappingRule]:
        if not rules:
            raise MappingReadinessError("EMPTY_MAPPING", "at least one reviewed mapping is required")

        validated: dict[MappingKey, MappingRule] = {}
        for rule in rules:
            if rule.key in validated:
                existing = validated[rule.key]
                if existing.intent == rule.intent:
                    # Same key, same intent: a redundant/copy-pasted row.
                    # Harmless in effect but still an authoring mistake, so
                    # it still fails closed -- with a code that matches
                    # build_coverage_report's "duplicate" (not "ambiguous")
                    # bucket for the identical situation.
                    raise MappingReadinessError(
                        "DUPLICATE_MAPPING",
                        f"redundant duplicate mapping key {rule.key!r} (intent {rule.intent!r})",
                    )
                raise MappingReadinessError(
                    "AMBIGUOUS_MAPPING",
                    f"key {rule.key!r} maps to conflicting intents "
                    f"{existing.intent!r} and {rule.intent!r}",
                )
            try:
                definition = self._manifest.by_intent(rule.intent)
            except KeyError as exc:
                raise MappingReadinessError(
                    "UNKNOWN_MAPPING_INTENT", f"intent {rule.intent!r} is not in the catalog"
                ) from exc
            if definition.domain_tool != rule.tool_name:
                raise MappingReadinessError(
                    "MAPPING_DOMAIN_MISMATCH",
                    f"intent {rule.intent!r} belongs to {definition.domain_tool!r}",
                )

            arguments = {"action": rule.action, "target": rule.target}
            if rule.value is not None:
                arguments["value"] = rule.value
            try:
                call = self._registry.validate_call(rule.tool_name, arguments)
            except ValueError as exc:
                raise MappingReadinessError("INVALID_MAPPING_CALL", str(exc)) from exc
            if not isinstance(call, ValidatedToolCall):
                raise MappingReadinessError("INCOMPLETE_MAPPING_CALL", repr(rule.key))
            validated[rule.key] = rule

        # Reuse build_coverage_report's definition of "missing" instead of
        # re-deriving the same set difference here, so the fail-closed gate
        # and the non-raising report can never silently disagree about what
        # counts as covered.
        missing = build_coverage_report(tuple(validated.values()), self._manifest).missing_intents
        if missing:
            raise MappingReadinessError(
                "INCOMPLETE_MAPPING_COVERAGE",
                f"no reviewed mapping reaches intents: {list(missing)!r}",
            )
        return MappingProxyType(validated)

    def map_proposal(self, proposal: Mapping[str, Any]) -> MappedProposal:
        """Validate, canonicalize and map an ActionProposal before Guardrail."""

        try:
            validate_action_proposal(proposal)
        except AuthorizationContractError as exc:
            raise UnsupportedToolMappingError("INVALID_ACTION_PROPOSAL", str(exc)) from exc

        try:
            call = self._registry.validate_call(proposal["tool"], proposal["arguments"])
        except ValueError as exc:
            raise UnsupportedToolMappingError(
                getattr(exc, "code", "INVALID_TOOL_CALL"), str(exc)
            ) from exc
        if isinstance(call, ClarificationRequest):
            raise UnsupportedToolMappingError(
                "INCOMPLETE_TOOL_CALL", f"missing {list(call.missing_parameters)!r}"
            )

        arguments = MappingProxyType(
            {key: call.arguments[key] for key in ("action", "target", "value") if key in call.arguments}
        )
        key = _mapping_key(call.tool_name, arguments)
        rule = self._rules.get(key)
        if rule is None and "value" in arguments:
            rule = self._rules.get((call.tool_name, arguments["action"], arguments["target"], "*"))
        if rule is None:
            raise UnsupportedToolMappingError(
                "UNSUPPORTED_TOOL_MAPPING", f"no exact reviewed mapping for {key!r}"
            )

        definition = self._manifest.by_intent(rule.intent)
        canonical_proposal = dict(proposal)
        canonical_proposal["arguments"] = dict(arguments)
        digest = authorization_request_digest(canonical_proposal)
        action = CanonicalAction(
            intent=rule.intent,
            normalized_arguments=arguments,
            behavior_id=definition.behavior_category,
        )
        event = MappingEvent(call.tool_name, rule.intent, digest)
        return MappedProposal(action, digest, event)


def load_default_mapper(registry: ToolRegistry, manifest: IntentManifest) -> ToolMapper:
    """Startup boundary: validate all reviewed mappings and fail closed."""

    return ToolMapper(registry, manifest)
