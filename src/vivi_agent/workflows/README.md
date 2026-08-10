# Agent predefined workflows

`WorkflowRegistry` is a closed Agent-side catalog. The model can select only
`run_predefined_workflow(workflow_id=...)`; it cannot invent steps or attach
extra arguments. Pass the registry explicitly as `workflow_registry` when
constructing an OpenAI or Gemini adapter. Without that opt-in, the existing
single-action model tool surface is unchanged.

`AgentWorkflowEngine` expands the selected definition and calls an injected
`step_runner` sequentially. The port accepts a typed `WorkflowStep` and returns
a typed `WorkflowStepResult`. The engine stops on the first failed result or
when its cancellation callback becomes true.

This package is Agent-only. It does not import or understand UI contracts,
Guardrail decisions, permits, vehicle handlers, policy rules, or transports.
Those concerns remain outside the workflow engine and may be composed behind
the generic step port by a separate runtime integration.
