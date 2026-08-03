"""Closed, versioned registry for model-selected domain tools.

The registry validates model output before a proposal can cross the Guardrail
boundary.  Vehicle state and Guardrail decision data are intentionally absent
from every public tool schema.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

REGISTRY_PATH = Path(__file__).with_name("domain_tools.v1.json")
REGISTRY_VERSION = "1.0.0"
ARGUMENT_FIELDS = frozenset({"action", "target", "value"})
FORBIDDEN_MODEL_FIELDS = frozenset({"state", "outcome", "rule", "rule_id", "permit"})
APPROVED_TOOL_NAMES = frozenset(
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
    }
)


class ToolCallValidationError(ValueError):
    """Raised when a model emits an unknown tool or invalid arguments."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ClarificationRequest:
    """Structured result for a supported call that lacks required parameters."""

    tool_name: str
    action: str | None
    missing_parameters: tuple[str, ...]
    allowed_values: Mapping[str, tuple[str, ...]]
    code: str = "MISSING_TOOL_PARAMETER"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "clarification",
            "code": self.code,
            "tool_name": self.tool_name,
            "action": self.action,
            "missing_parameters": list(self.missing_parameters),
            "allowed_values": {key: list(value) for key, value in self.allowed_values.items()},
        }


@dataclass(frozen=True)
class ValidatedToolCall:
    tool_name: str
    arguments: Mapping[str, str]


@dataclass(frozen=True)
class ToolSignature:
    action: str
    targets: tuple[str, ...]
    values: tuple[str, ...]

    @property
    def required_fields(self) -> tuple[str, ...]:
        return ("action", "target", "value") if self.values else ("action", "target")


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    signatures: tuple[ToolSignature, ...]

    def model_schema(self) -> dict[str, Any]:
        variants = []
        for signature in self.signatures:
            properties: dict[str, Any] = {
                "action": {"type": "string", "const": signature.action},
                "target": {"type": "string", "enum": sorted(signature.targets)},
            }
            if signature.values:
                properties["value"] = {"type": "string", "enum": sorted(signature.values)}
            variants.append(
                {
                    "type": "object",
                    "properties": properties,
                    "required": list(signature.required_fields),
                    "additionalProperties": False,
                }
            )
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"oneOf": variants},
        }


@dataclass(frozen=True)
class ToolRegistry:
    registry_version: str
    checksum: str
    tools: tuple[ToolDefinition, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self.tools)

    def model_tools(self) -> tuple[dict[str, Any], ...]:
        """Return neutral declarations for provider adapters to serialize."""
        return tuple(tool.model_schema() for tool in self.tools)

    def by_name(self, name: str) -> ToolDefinition:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise ToolCallValidationError("UNKNOWN_TOOL", f"tool {name!r} is not registered")

    def validate_call(
        self, name: str, arguments: Mapping[str, Any]
    ) -> ValidatedToolCall | ClarificationRequest:
        """Validate a model call before any Guardrail adapter is invoked."""
        tool = self.by_name(name)
        if not isinstance(arguments, Mapping):
            raise ToolCallValidationError("INVALID_ARGUMENTS", "arguments must be an object")
        fields = set(arguments)
        forbidden = fields & FORBIDDEN_MODEL_FIELDS
        if forbidden:
            raise ToolCallValidationError(
                "FORBIDDEN_ARGUMENT", f"model cannot supply {sorted(forbidden)!r}"
            )
        extra = fields - ARGUMENT_FIELDS
        if extra:
            raise ToolCallValidationError("ADDITIONAL_PROPERTY", f"unexpected fields {sorted(extra)!r}")
        for key, value in arguments.items():
            if not isinstance(value, str) or not value:
                raise ToolCallValidationError("INVALID_ARGUMENTS", f"{key} must be a non-empty string")

        action = arguments.get("action")
        action_signatures = tuple(item for item in tool.signatures if item.action == action)
        if action is None:
            return ClarificationRequest(
                name, None, ("action",),
                MappingProxyType({"action": tuple(sorted({item.action for item in tool.signatures}))}),
            )
        if not action_signatures:
            raise ToolCallValidationError("INVALID_ACTION", f"unsupported {name} action {action!r}")

        target = arguments.get("target")
        if target is None:
            targets = tuple(sorted({item for sig in action_signatures for item in sig.targets}))
            return ClarificationRequest(name, action, ("target",), MappingProxyType({"target": targets}))
        target_signatures = tuple(sig for sig in action_signatures if target in sig.targets)
        if not target_signatures:
            raise ToolCallValidationError(
                "INVALID_TARGET", f"target {target!r} is not valid for {name}.{action}"
            )

        allowed_values = tuple(sorted({item for sig in target_signatures for item in sig.values}))
        value = arguments.get("value")
        if allowed_values and value is None:
            return ClarificationRequest(
                name, action, ("value",), MappingProxyType({"value": allowed_values})
            )
        if allowed_values and value not in allowed_values:
            raise ToolCallValidationError(
                "INVALID_VALUE", f"value {value!r} is not valid for {name}.{action}.{target}"
            )
        if not allowed_values and value is not None:
            raise ToolCallValidationError(
                "UNEXPECTED_VALUE", f"{name}.{action}.{target} does not accept value"
            )
        normalized = {key: arguments[key] for key in ("action", "target", "value") if key in arguments}
        return ValidatedToolCall(name, MappingProxyType(normalized))


def _canonical_payload(raw: Mapping[str, Any]) -> bytes:
    payload = {key: value for key, value in raw.items() if key != "checksum"}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def registry_checksum(raw: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_payload(raw)).hexdigest()


def _parse_registry(raw: Mapping[str, Any]) -> ToolRegistry:
    if set(raw) != {"registry_version", "checksum", "tools"}:
        raise ToolCallValidationError("INVALID_REGISTRY", "registry root must match closed schema")
    if raw["registry_version"] != REGISTRY_VERSION:
        raise ToolCallValidationError("REGISTRY_VERSION_MISMATCH", repr(raw["registry_version"]))
    expected = registry_checksum(raw)
    if raw["checksum"] != expected:
        raise ToolCallValidationError("REGISTRY_CHECKSUM_MISMATCH", f"expected {expected}")
    if not isinstance(raw["tools"], list):
        raise ToolCallValidationError("INVALID_REGISTRY", "tools must be an array")

    tools: list[ToolDefinition] = []
    for entry in raw["tools"]:
        if not isinstance(entry, Mapping) or set(entry) != {"name", "description", "signatures"}:
            raise ToolCallValidationError("INVALID_REGISTRY", "tool must match closed schema")
        if not all(isinstance(entry[key], str) and entry[key] for key in ("name", "description")):
            raise ToolCallValidationError("INVALID_REGISTRY", "tool name and description are required")
        signatures: list[ToolSignature] = []
        if not isinstance(entry["signatures"], list) or not entry["signatures"]:
            raise ToolCallValidationError("INVALID_REGISTRY", "tool signatures cannot be empty")
        for signature in entry["signatures"]:
            if not isinstance(signature, Mapping) or not set(signature) <= {"action", "target", "value"}:
                raise ToolCallValidationError("INVALID_REGISTRY", "signature fields are invalid")
            if set(signature) not in ({"action", "target"}, {"action", "target", "value"}):
                raise ToolCallValidationError("INVALID_REGISTRY", "signature needs action and target")
            action, targets = signature["action"], signature["target"]
            values = signature.get("value", [])
            if not isinstance(action, str) or not action or not _valid_enum(targets) or not _valid_enum(values, empty=True):
                raise ToolCallValidationError("INVALID_REGISTRY", "signature enums must be unique strings")
            signatures.append(ToolSignature(action, tuple(targets), tuple(values)))
        tools.append(ToolDefinition(entry["name"], entry["description"], tuple(signatures)))
    names = [tool.name for tool in tools]
    if len(names) != len(set(names)):
        raise ToolCallValidationError("INVALID_REGISTRY", "duplicate tool name")
    actual_names = set(names)
    if actual_names != APPROVED_TOOL_NAMES:
        raise ToolCallValidationError(
            "TOOL_COVERAGE_MISMATCH",
            f"missing={sorted(APPROVED_TOOL_NAMES - actual_names)!r}, "
            f"extra={sorted(actual_names - APPROVED_TOOL_NAMES)!r}",
        )
    return ToolRegistry(raw["registry_version"], raw["checksum"], tuple(tools))


def _valid_enum(value: Any, *, empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (empty or bool(value))
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def load_registry(path: Path | str = REGISTRY_PATH) -> ToolRegistry:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ToolCallValidationError("REGISTRY_LOAD_FAILED", str(exc)) from exc
    if not isinstance(raw, Mapping):
        raise ToolCallValidationError("INVALID_REGISTRY", "registry root must be an object")
    return _parse_registry(raw)
