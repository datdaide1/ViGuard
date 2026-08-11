"""Agent-only coordinator for reviewed predefined workflows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from .registry import WORKFLOW_TOOL_NAME, WorkflowRegistry, WorkflowStep


class WorkflowRunStatus(str, Enum):
    COMPLETED = "completed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class WorkflowStepResult:
    success: bool
    message: str
    facts: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.success, bool) or not isinstance(self.message, str):
            raise TypeError("step result requires boolean success and text message")
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))


@dataclass(frozen=True)
class WorkflowRunResult:
    workflow_id: str
    status: WorkflowRunStatus
    completed_steps: int
    total_steps: int
    message: str
    step_results: tuple[WorkflowStepResult, ...]


class AgentWorkflowEngine:
    """Expand one closed model selection and coordinate its steps in order.

    ``step_runner`` is an injected Agent runtime port. This module deliberately
    knows nothing about policy engines, vehicle handlers, UI, or transport.
    """

    def __init__(self, registry: WorkflowRegistry) -> None:
        self._registry = registry

    def run_model_call(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        step_runner: Callable[[WorkflowStep, int, int], WorkflowStepResult],
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> WorkflowRunResult:
        if tool_name != WORKFLOW_TOOL_NAME:
            raise ValueError(f"unsupported workflow tool {tool_name!r}")
        if not callable(step_runner) or (cancelled is not None and not callable(cancelled)):
            raise TypeError("step_runner and cancelled must be callable")
        workflow = self._registry.resolve_model_call(arguments)
        results: list[WorkflowStepResult] = []
        total = len(workflow.steps)
        for index, step in enumerate(workflow.steps):
            if cancelled is not None and cancelled():
                return WorkflowRunResult(
                    workflow.workflow_id,
                    WorkflowRunStatus.CANCELLED,
                    len(results),
                    total,
                    "Workflow was cancelled.",
                    tuple(results),
                )
            result = step_runner(step, index, total)
            if not isinstance(result, WorkflowStepResult):
                raise TypeError("step_runner must return WorkflowStepResult")
            results.append(result)
            if not result.success:
                return WorkflowRunResult(
                    workflow.workflow_id,
                    WorkflowRunStatus.STOPPED,
                    index,
                    total,
                    result.message,
                    tuple(results),
                )
        return WorkflowRunResult(
            workflow.workflow_id,
            WorkflowRunStatus.COMPLETED,
            total,
            total,
            workflow.success_message,
            tuple(results),
        )
