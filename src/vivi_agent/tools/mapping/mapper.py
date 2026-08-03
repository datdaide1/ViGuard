"""Fail-closed mapping from validated model tool calls to policy intents.

MAP-01 intentionally contains only the first vertical-slice mapping.  Mapping
coverage for the rest of the catalog belongs to MAP-02.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from ...catalog.manifest import IntentManifest
from ...contracts.guardrail.v1.contract import (
    ContractValidationError,
    proposal_digest,
    validate_action_proposal,
)
from ..registry import ClarificationRequest, ToolRegistry, ValidatedToolCall


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
    def key(self) -> tuple[str, str, str, str | None]:
        return (self.tool_name, self.action, self.target, self.value)


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


DEFAULT_MAPPING_RULES = (
    MappingRule("control_access", "open", "driver_door", "open_door"),
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
    ) -> Mapping[tuple[str, str, str, str | None], MappingRule]:
        if not rules:
            raise MappingReadinessError("EMPTY_MAPPING", "at least one reviewed mapping is required")

        validated: dict[tuple[str, str, str, str | None], MappingRule] = {}
        for rule in rules:
            if rule.key in validated:
                raise MappingReadinessError(
                    "AMBIGUOUS_MAPPING", f"duplicate mapping key {rule.key!r}"
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
        return MappingProxyType(validated)

    def map_proposal(self, proposal: Mapping[str, Any]) -> MappedProposal:
        """Validate, canonicalize and map an ActionProposal before Guardrail."""

        try:
            validate_action_proposal(proposal)
        except ContractValidationError as exc:
            raise UnsupportedToolMappingError("INVALID_ACTION_PROPOSAL", str(exc)) from exc

        call = self._registry.validate_call(proposal["tool"], proposal["arguments"])
        if isinstance(call, ClarificationRequest):
            raise UnsupportedToolMappingError(
                "INCOMPLETE_TOOL_CALL", f"missing {list(call.missing_parameters)!r}"
            )

        arguments = MappingProxyType(
            {key: call.arguments[key] for key in ("action", "target", "value") if key in call.arguments}
        )
        key = (
            call.tool_name,
            arguments["action"],
            arguments["target"],
            arguments.get("value"),
        )
        rule = self._rules.get(key)
        if rule is None:
            raise UnsupportedToolMappingError(
                "UNSUPPORTED_TOOL_MAPPING", f"no exact reviewed mapping for {key!r}"
            )

        definition = self._manifest.by_intent(rule.intent)
        canonical_proposal = dict(proposal)
        canonical_proposal["arguments"] = dict(arguments)
        digest = proposal_digest(canonical_proposal)
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
