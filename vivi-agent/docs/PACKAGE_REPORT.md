# ViVi Agent package report

**Package version:** 1.0.0
**Prepared:** 2026-08-10
**Scope:** Agent-only Python package for simulator and external integration

## Delivered

- Standalone text Agent public API and optional Guardrail decision coordinator.
- Gemini/OpenAI production HTTP transports, deterministic fast path, 12 RPM
  default limiter, bounded retry and safe provider diagnostics.
- 123-intent runtime inventory, 11 tools and 148 mappings.
- Vehicle state model, atomic state machine, generic handlers, queries,
  responses, confirmations, workflows, events and simulator controls.
- Agent-owned Guardrail authorization port plus optional ViGuard adapter.
- Closed Agent–UI payload/event contract and framework-neutral endpoints.
- Unit, contract, integration, E2E, performance and adversarial tests.
- EVAL-01 fixed baseline and EVAL-02 coverage for all 70 candidate intents.
- Self-contained build metadata, examples and zip verification tooling.

## Verified evidence before packaging

- Full repository suite before restructure: `942 passed, 2 skipped, 123 subtests`.
- Portable package suite after relocation: `934 passed, 2 skipped, 123 subtests`.
- Live Gemini 3.5 Flash Lite smoke at 12 RPM: representative HVAC, navigation,
  charging query and LKA cases passed 4/4.
- Candidate workbook-to-code comparison: 70 rows and exact intent/description match.
- Runtime readiness: 123 intents, 11 tools, 148 mappings, full coverage PASS.
- Provider error feedback fix includes allowlisted diagnostics, redaction and tests.

The eight removed tests belonged to the tracker-dependent legacy release gate;
the executable Agent behavior and integration suites remain in the package.

## Explicit limitations

- No real vehicle actuator, CAN/ECU integration or hardware-in-the-loop.
- No claim that prompt injection is impossible; Agent prompt is defense-in-depth.
- No Guardrail policy/rule engine or UI implementation in this package.
- ETA, range and charge-limit queries return unknown until telemetry supplies data.
- Command-only capabilities prove command dispatch, not physical state change.
- Simulator tests do not establish OEM/regulatory/ISO 26262 safety.

## Removed as obsolete

Task-scaffold files, tracker/workspace scaffold, stale 53-intent reports, old
generated result JSON and the tracker-dependent legacy release gate were removed
from the portable package. Git history remains the recovery path. Project-wide
Guardrail specs, PRDs, workbooks, research, brief and golden dataset were left
outside and unchanged.
