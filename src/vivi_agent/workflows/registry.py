"""Closed registry of reviewed multi-step workflows.

Workflows only sequence existing domain-tool calls. They never contain policy
outcomes, vehicle state, permits, handlers, or arbitrary executable code.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from ..tools.registry import (
    ClarificationRequest,
    ToolCallValidationError,
    ToolRegistry,
    ValidatedToolCall,
)

WORKFLOW_TOOL_NAME = "run_predefined_workflow"
MAX_WORKFLOW_STEPS = 8
STATE_CHANGING_WORKFLOW_TOOLS = frozenset(
    {
        "control_access",
        "control_light",
        "control_cabin",
        "set_drive_mode",
        "control_transmission",
        "control_driver_assistance",
        "control_special_mode",
        "control_ui",
    }
)


class WorkflowValidationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class WorkflowStep:
    tool_name: str
    arguments: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    description: str
    success_message: str
    steps: tuple[WorkflowStep, ...]


DEFAULT_WORKFLOWS = (
    WorkflowDefinition(
        "park_and_secure",
        "Park, apply the parking brake, lock the doors, and fold the mirrors.",
        "Đã hoàn tất quy trình đỗ và bảo vệ xe.",
        (
            WorkflowStep("control_transmission", {"action": "shift", "target": "gear", "value": "park"}),
            WorkflowStep("control_transmission", {"action": "activate", "target": "electronic_parking_brake"}),
            WorkflowStep("control_access", {"action": "lock", "target": "all_doors"}),
            WorkflowStep("control_cabin", {"action": "fold", "target": "mirrors"}),
        ),
    ),
    WorkflowDefinition(
        "prepare_camp_mode",
        "Park, apply the parking brake, and activate camp mode.",
        "Đã hoàn tất quy trình chuẩn bị chế độ cắm trại.",
        (
            WorkflowStep("control_transmission", {"action": "shift", "target": "gear", "value": "park"}),
            WorkflowStep("control_transmission", {"action": "activate", "target": "electronic_parking_brake"}),
            WorkflowStep("control_special_mode", {"action": "activate", "target": "camp_mode"}),
        ),
    ),
)


class WorkflowRegistry:
    def __init__(
        self, tool_registry: ToolRegistry, definitions: tuple[WorkflowDefinition, ...]
    ) -> None:
        if not definitions:
            raise WorkflowValidationError("EMPTY_WORKFLOW_REGISTRY", "at least one workflow is required")
        validated: dict[str, WorkflowDefinition] = {}
        for definition in definitions:
            if not definition.workflow_id or definition.workflow_id in validated:
                raise WorkflowValidationError("INVALID_WORKFLOW_ID", repr(definition.workflow_id))
            if not definition.description.strip() or not definition.success_message.strip():
                raise WorkflowValidationError("INVALID_WORKFLOW_TEXT", definition.workflow_id)
            if not 1 <= len(definition.steps) <= MAX_WORKFLOW_STEPS:
                raise WorkflowValidationError("INVALID_WORKFLOW_LENGTH", definition.workflow_id)
            for step in definition.steps:
                if step.tool_name not in STATE_CHANGING_WORKFLOW_TOOLS:
                    raise WorkflowValidationError(
                        "NON_ACTION_WORKFLOW_STEP", f"{definition.workflow_id}:{step.tool_name}"
                    )
                try:
                    result = tool_registry.validate_call(step.tool_name, step.arguments)
                except ToolCallValidationError as exc:
                    raise WorkflowValidationError(
                        "INVALID_WORKFLOW_STEP", f"{definition.workflow_id}:{exc.code}"
                    ) from exc
                if isinstance(result, ClarificationRequest) or not isinstance(result, ValidatedToolCall):
                    raise WorkflowValidationError(
                        "INCOMPLETE_WORKFLOW_STEP", f"{definition.workflow_id}:{step.tool_name}"
                    )
            validated[definition.workflow_id] = definition
        self._definitions = MappingProxyType(validated)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def resolve_model_call(self, arguments: Mapping[str, Any]) -> WorkflowDefinition:
        if not isinstance(arguments, Mapping) or set(arguments) != {"workflow_id"}:
            raise WorkflowValidationError(
                "INVALID_WORKFLOW_CALL", "arguments must contain only workflow_id"
            )
        workflow_id = arguments.get("workflow_id")
        if not isinstance(workflow_id, str) or workflow_id not in self._definitions:
            raise WorkflowValidationError("UNKNOWN_WORKFLOW", repr(workflow_id))
        return self._definitions[workflow_id]

    def model_schema(self) -> dict[str, Any]:
        return {
            "name": WORKFLOW_TOOL_NAME,
            "description": "Run one reviewed multi-step vehicle workflow.",
            "parameters": {
                "type": "object",
                "properties": {"workflow_id": {"type": "string", "enum": list(self.ids)}},
                "required": ["workflow_id"],
                "additionalProperties": False,
            },
        }


def load_default_workflows(tool_registry: ToolRegistry) -> WorkflowRegistry:
    return WorkflowRegistry(tool_registry, DEFAULT_WORKFLOWS)
