from __future__ import annotations

import pytest

from vivi_agent.tools.registry import load_registry
from vivi_agent.workflows import (
    AgentWorkflowEngine,
    MAX_WORKFLOW_STEPS,
    WORKFLOW_TOOL_NAME,
    WorkflowDefinition,
    WorkflowRegistry,
    WorkflowRunStatus,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowValidationError,
    load_default_workflows,
)


def test_default_workflow_is_closed_bounded_and_model_visible():
    registry = load_default_workflows(load_registry())
    assert registry.ids == ("park_and_secure", "prepare_camp_mode")
    schema = registry.model_schema()
    assert schema["parameters"]["additionalProperties"] is False
    assert set(schema["parameters"]["properties"]["workflow_id"]["enum"]) == set(registry.ids)

    with pytest.raises(WorkflowValidationError, match="UNKNOWN_WORKFLOW"):
        registry.resolve_model_call({"workflow_id": "model_invented"})
    with pytest.raises(WorkflowValidationError, match="INVALID_WORKFLOW_CALL"):
        registry.resolve_model_call({"workflow_id": "park_and_secure", "extra": "fake"})


def test_registry_rejects_unbounded_invalid_and_non_action_steps_at_startup():
    registry = load_registry()
    too_long = WorkflowDefinition(
        "too_long", "bad", "bad", tuple(
            WorkflowStep("control_access", {"action": "lock", "target": "all_doors"})
            for _ in range(MAX_WORKFLOW_STEPS + 1)
        )
    )
    with pytest.raises(WorkflowValidationError, match="INVALID_WORKFLOW_LENGTH"):
        WorkflowRegistry(registry, (too_long,))

    invalid = WorkflowDefinition(
        "invalid", "bad", "bad",
        (WorkflowStep("control_access", {"action": "lock", "target": "trunk"}),),
    )
    with pytest.raises(WorkflowValidationError, match="INVALID_WORKFLOW_STEP"):
        WorkflowRegistry(registry, (invalid,))

    query = WorkflowDefinition(
        "query", "bad", "bad",
        (WorkflowStep("query_vehicle_state", {"action": "get", "target": "current_speed"}),),
    )
    with pytest.raises(WorkflowValidationError, match="NON_ACTION_WORKFLOW_STEP"):
        WorkflowRegistry(registry, (query,))


def test_engine_runs_reviewed_steps_in_order_through_an_injected_agent_port():
    engine = AgentWorkflowEngine(load_default_workflows(load_registry()))
    seen = []

    def run_step(step, index, total):
        seen.append((step.tool_name, dict(step.arguments), index, total))
        return WorkflowStepResult(True, f"step {index + 1}", {"index": index})

    result = engine.run_model_call(
        WORKFLOW_TOOL_NAME, {"workflow_id": "park_and_secure"}, run_step
    )
    assert result.status is WorkflowRunStatus.COMPLETED
    assert result.completed_steps == result.total_steps == 4
    assert [item[0] for item in seen] == [
        "control_transmission", "control_transmission", "control_access", "control_cabin"
    ]
    assert [item[2] for item in seen] == [0, 1, 2, 3]


def test_engine_stops_after_generic_step_failure_without_running_later_steps():
    engine = AgentWorkflowEngine(load_default_workflows(load_registry()))
    seen = []

    def run_step(step, index, total):
        seen.append(step.tool_name)
        return WorkflowStepResult(index != 1, "stopped" if index == 1 else "ok", {})

    result = engine.run_model_call(
        WORKFLOW_TOOL_NAME, {"workflow_id": "park_and_secure"}, run_step
    )
    assert result.status is WorkflowRunStatus.STOPPED
    assert result.completed_steps == 1
    assert len(seen) == 2


def test_engine_cancellation_stops_before_the_next_agent_step():
    engine = AgentWorkflowEngine(load_default_workflows(load_registry()))
    seen = []

    def run_step(step, index, total):
        seen.append(step.tool_name)
        return WorkflowStepResult(True, "ok", {})

    result = engine.run_model_call(
        WORKFLOW_TOOL_NAME,
        {"workflow_id": "park_and_secure"},
        run_step,
        cancelled=lambda: len(seen) == 1,
    )
    assert result.status is WorkflowRunStatus.CANCELLED
    assert result.completed_steps == 1
    assert len(seen) == 1


def test_unknown_workflow_and_wrong_runner_result_fail_before_extra_steps():
    engine = AgentWorkflowEngine(load_default_workflows(load_registry()))
    calls = []
    with pytest.raises(WorkflowValidationError, match="UNKNOWN_WORKFLOW"):
        engine.run_model_call(
            WORKFLOW_TOOL_NAME,
            {"workflow_id": "invented"},
            lambda *args: calls.append(args),
        )
    assert calls == []

    with pytest.raises(TypeError, match="WorkflowStepResult"):
        engine.run_model_call(
            WORKFLOW_TOOL_NAME,
            {"workflow_id": "prepare_camp_mode"},
            lambda *args: {"success": True},
        )
