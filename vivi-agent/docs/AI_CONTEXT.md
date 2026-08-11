# Context for AI/code agents

Read `README.md`, then `docs/ARCHITECTURE.md` and `docs/INTEGRATION.md` before
editing code.

## Non-negotiable invariants

1. Agent does not invent or enforce Guardrail policy conditions.
2. Model output never supplies trusted vehicle state, permit, rule or outcome.
3. Tool calls pass closed registry validation and exact mapping before execution.
4. Query paths never call actuators and never guess missing telemetry.
5. `CONFIRM` is not executable; acceptance requires a fresh Guardrail decision.
6. Block/error/pending-confirmation paths create zero side effects.
7. Duplicate request IDs execute at most once within the runtime process.
8. Public UI events exclude credentials, prompts, permits and hidden reasoning.
9. Command-only handler success means command dispatch, not observed vehicle state.
10. Any new intent must have catalog, tool, mapping, handler/query and tests.

## Current canonical entry points

- `vivi_agent.build_agent_runtime_from_env()`
- `AgentRuntime.handle_text(...)`
- `GuardedAgentCoordinator.handle_decision(...)`
- `GuardedAgentCoordinator.resolve_confirmation(...)`
- `MessageEndpoint.post_message(...)`
- `OperationsEndpoint.get_health()/post_reset()/reconnect()`

## Do not reintroduce

- dependency on project-root Guardrail PRD/workbook at runtime;
- dynamic `eval()` or model-generated executable code;
- raw provider response bodies in exceptions/logs;
- implicit `.env` loading;
- model fallback that silently executes when provider readiness fails;
- hard-coded old counts such as 53/47/6 for the complete runtime catalog.

## Validation after a change

Run `python scripts/verify_package.py`, focused tests for the modified boundary,
then `python -m pytest -q`. Keep live provider tests separate and quota-bounded.
