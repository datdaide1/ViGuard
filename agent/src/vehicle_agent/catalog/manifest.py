"""Load and validate the versioned Agent-side intent manifest.

This module deliberately contains no Guardrail condition or outcome policy.  It
only proves that the Agent has loaded the exact approved intent inventory and
that the checked-in manifest has not been changed without updating its digest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .candidate import CANDIDATE_CAPABILITIES, CANDIDATE_INTENTS, CANDIDATE_QUERY_INTENTS

MANIFEST_PATH = Path(__file__).with_name("intent_manifest.v1.json")
MANIFEST_VERSION = "1.0.0"

# This allowlist is intentionally independent of the JSON manifest.  A missing
# or extra JSON entry must therefore fail readiness instead of redefining truth.
BASE_APPROVED_INTENTS = frozenset(
    {
        "open_door", "open_trunk", "open_chargeport", "turnoff_highbeam",
        "turnon_highbeam", "turnoff_lowbeam", "turnon_lowbeam", "lock_doors",
        "unlock_doors", "OPEN_BONNET", "AD_WIPER_MAX", "switch_drivemode_sport",
        "switch_drivemode_eco", "switch_drivemode_normal", "activate_creepmode",
        "turnoff_LKA", "activate_campmode", "activate_petmode", "activate_valetmode",
        "SHIFT_GEAR_REVERSE", "ad_steeringwheel", "activate_autopark", "fold_backseat",
        "open_sunroof", "ad_driverseat_angle", "ad_driverseat_pos", "open_window",
        "restore_driverseat_pos", "activate_epb", "deactivate_hud", "activate_aac",
        "activate_hda", "shift_gear_park", "fold_mirrors", "activate_ahb",
        "turnon_turnsignal_right", "turnon_turnsignal_left", "turnoff_turnsignal_right",
        "turnoff_turnsignal_left", "turnon_hazardlight", "turnoff_hazardlight",
        "turnon_corneringlight", "turnon_interiorlight", "activate_tcs", "deactivate_esc",
        "activate_avh", "open_noti_center", "get_current_speed", "get_battery_pct",
        "get_gear", "get_door_lock_status", "get_avh_status", "explain_feature",
    }
)
APPROVED_INTENTS = BASE_APPROVED_INTENTS | CANDIDATE_INTENTS

FORBIDDEN_DYNAMICS_INTENTS = frozenset(
    {"power_on", "start", "accelerate", "brake", "stop", "emergency_stop", "steer"}
)
QUERY_INTENTS = frozenset(
    {"get_current_speed", "get_battery_pct", "get_gear", "get_door_lock_status", "get_avh_status", "explain_feature"}
) | CANDIDATE_QUERY_INTENTS
MONITORED_INTENTS = frozenset(
    {"activate_campmode", "activate_petmode", "activate_autopark", "activate_aac", "activate_hda"}
)
ALLOWED_KINDS = frozenset({"action", "query", "refusal"})
ALLOWED_DOMAIN_TOOLS = frozenset(
    {
        "control_access",
        "control_light",
        "control_cabin",
        "set_drive_mode",
        "control_transmission",
        "control_driver_assistance",
        "control_special_mode",
        "control_ui",
        "query_vehicle_state",
        "explain_vehicle_feature",
        "control_vehicle_capability",
    }
)
ALLOWED_BEHAVIORS = frozenset(
    {
        "access_mutation", "toggle", "enum_mutation", "active_mode", "position_mutation",
        "active_action", "timed_mutation", "compound_mutation", "compound_toggle", "ui_event",
        "state_query", "knowledge_query", "explicit_refusal",
    }
)
BEHAVIORS_BY_KIND = {
    "action": ALLOWED_BEHAVIORS
    - {"state_query", "knowledge_query", "explicit_refusal"},
    "query": frozenset({"state_query", "knowledge_query"}),
    "refusal": frozenset({"explicit_refusal"}),
}


class CatalogReadinessError(RuntimeError):
    """Raised when catalog startup validation fails closed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.readiness = False


@dataclass(frozen=True)
class IntentDefinition:
    intent: str
    kind: str
    domain_tool: str
    behavior_category: str
    required_parameters: tuple[str, ...]
    monitor_rule_ids: tuple[str, ...]
    sample_utterances: tuple[str, ...]

    @property
    def is_query(self) -> bool:
        return self.kind == "query"

    @property
    def is_action(self) -> bool:
        return self.kind in {"action", "refusal"}

    @property
    def monitor_capable(self) -> bool:
        return bool(self.monitor_rule_ids)


@dataclass(frozen=True)
class IntentManifest:
    manifest_version: str
    catalog_source: str
    checksum: str
    intents: tuple[IntentDefinition, ...]

    def by_intent(self, intent: str) -> IntentDefinition:
        for definition in self.intents:
            if definition.intent == intent:
                return definition
        raise KeyError(intent)


def _canonical_payload(raw: Mapping[str, Any]) -> bytes:
    payload = {key: value for key, value in raw.items() if key != "checksum"}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def manifest_checksum(raw: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_payload(raw)).hexdigest()


def _require_string(value: Any, field: str, intent: str = "manifest") -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogReadinessError("INVALID_MANIFEST", f"{intent}.{field} must be a non-empty string")
    return value


def _string_tuple(value: Any, field: str, intent: str, *, non_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (non_empty and not value):
        raise CatalogReadinessError("INVALID_MANIFEST", f"{intent}.{field} must be a string array")
    result = tuple(_require_string(item, field, intent) for item in value)
    if len(result) != len(set(result)):
        raise CatalogReadinessError("INVALID_MANIFEST", f"{intent}.{field} contains duplicates")
    return result


def validate_manifest(raw: Mapping[str, Any]) -> IntentManifest:
    """Validate raw manifest data and return immutable runtime definitions."""
    if not isinstance(raw, Mapping):
        raise CatalogReadinessError("INVALID_MANIFEST", "manifest root must be an object")
    if set(raw) != {"manifest_version", "catalog_source", "checksum", "intents"}:
        raise CatalogReadinessError("INVALID_MANIFEST", "manifest root fields do not match the closed schema")

    version = _require_string(raw["manifest_version"], "manifest_version")
    if version != MANIFEST_VERSION:
        raise CatalogReadinessError("MANIFEST_VERSION_MISMATCH", f"expected {MANIFEST_VERSION}, got {version}")
    source = _require_string(raw["catalog_source"], "catalog_source")
    checksum = _require_string(raw["checksum"], "checksum")
    expected_checksum = manifest_checksum(raw)
    if checksum != expected_checksum:
        raise CatalogReadinessError("MANIFEST_CHECKSUM_MISMATCH", f"expected {expected_checksum}, got {checksum}")

    entries = raw["intents"]
    if not isinstance(entries, list):
        raise CatalogReadinessError("INVALID_MANIFEST", "intents must be an array")
    definitions: list[IntentDefinition] = []
    expected_fields = {
        "intent", "kind", "domain_tool", "behavior_category", "required_parameters",
        "monitor_rule_ids", "sample_utterances",
    }
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != expected_fields:
            raise CatalogReadinessError("INVALID_MANIFEST", "each intent must match the closed entry schema")
        intent = _require_string(entry["intent"], "intent")
        kind = _require_string(entry["kind"], "kind", intent)
        domain_tool = _require_string(entry["domain_tool"], "domain_tool", intent)
        behavior = _require_string(entry["behavior_category"], "behavior_category", intent)
        if kind not in ALLOWED_KINDS:
            raise CatalogReadinessError("INVALID_MANIFEST", f"{intent} has unsupported kind {kind!r}")
        if domain_tool not in ALLOWED_DOMAIN_TOOLS:
            raise CatalogReadinessError(
                "INVALID_MANIFEST", f"{intent} has unsupported domain_tool {domain_tool!r}"
            )
        if behavior not in BEHAVIORS_BY_KIND[kind]:
            raise CatalogReadinessError(
                "INVALID_MANIFEST",
                f"{intent} behavior {behavior!r} is incompatible with kind {kind!r}",
            )
        definitions.append(
            IntentDefinition(
                intent=intent,
                kind=kind,
                domain_tool=domain_tool,
                behavior_category=behavior,
                required_parameters=_string_tuple(entry["required_parameters"], "required_parameters", intent),
                monitor_rule_ids=_string_tuple(entry["monitor_rule_ids"], "monitor_rule_ids", intent),
                sample_utterances=_string_tuple(entry["sample_utterances"], "sample_utterances", intent, non_empty=True),
            )
        )

    definitions.extend(
        IntentDefinition(
            intent=item.intent,
            kind=item.kind,
            domain_tool=(
                "control_driver_assistance"
                if item.intent == "turnon_LKA"
                else "control_vehicle_capability"
            ),
            behavior_category="state_query" if item.kind == "query" else "ui_event",
            required_parameters=("value",) if item.requires_value else (),
            monitor_rule_ids=(),
            sample_utterances=(item.description,),
        )
        for item in CANDIDATE_CAPABILITIES
    )

    names = [definition.intent for definition in definitions]
    if len(names) != len(set(names)):
        raise CatalogReadinessError("DUPLICATE_INTENT", "manifest contains duplicate intent names")
    actual = set(names)
    missing, extra = APPROVED_INTENTS - actual, actual - APPROVED_INTENTS
    if missing or extra:
        raise CatalogReadinessError(
            "INTENT_COVERAGE_MISMATCH",
            f"missing={sorted(missing)!r}, extra={sorted(extra)!r}",
        )
    if actual & FORBIDDEN_DYNAMICS_INTENTS:
        raise CatalogReadinessError("FORBIDDEN_DYNAMICS_INTENT", repr(sorted(actual & FORBIDDEN_DYNAMICS_INTENTS)))

    by_name = {definition.intent: definition for definition in definitions}
    actual_queries = {name for name, definition in by_name.items() if definition.is_query}
    if actual_queries != QUERY_INTENTS:
        raise CatalogReadinessError("QUERY_COVERAGE_MISMATCH", f"expected={sorted(QUERY_INTENTS)!r}, actual={sorted(actual_queries)!r}")
    if by_name["deactivate_esc"].kind != "refusal" or by_name["deactivate_esc"].behavior_category != "explicit_refusal":
        raise CatalogReadinessError("REFUSAL_BEHAVIOR_MISMATCH", "deactivate_esc must remain an explicit refusal")
    actual_monitored = {name for name, definition in by_name.items() if definition.monitor_capable}
    if actual_monitored != MONITORED_INTENTS:
        raise CatalogReadinessError("MONITOR_COVERAGE_MISMATCH", f"expected={sorted(MONITORED_INTENTS)!r}, actual={sorted(actual_monitored)!r}")
    return IntentManifest(
        version,
        f"{source}; Intents_Candidate.xlsx#Intents_Candidate (70 Agent capabilities, no policy conditions)",
        checksum,
        tuple(definitions),
    )


def load_manifest(path: Path | str = MANIFEST_PATH) -> IntentManifest:
    """Load the catalog during startup; any defect raises a readiness error."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogReadinessError("MANIFEST_LOAD_FAILED", str(exc)) from exc
    return validate_manifest(raw)
