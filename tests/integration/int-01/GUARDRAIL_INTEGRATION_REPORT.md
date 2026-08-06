# Guardrail Integration Report (INT-01)

**Task:** INT-01 — Chạy integration với Guardrail thật  
**Sprint:** Sprint 2  
**Code Area:** `tests/integration/int-01`  
**Status:** Completed  

---

## 1. Overview & Integration Architecture

The **INT-01** integration suite validates the end-to-end contract and protocol integration between:
1. **Agent Orchestrator** (`vivi_agent.orchestrator.AgentOrchestrator`)
2. **Guardrail Client Adapter** (`vivi_agent.adapters.guardrail.GuardrailClientAdapter`)
3. **HTTP Guardrail Server & Protocol Specification** (`vivi_agent.contracts.guardrail.v1`)
4. **Vehicle Execution Gateway** (`vivi_agent.vehicle.execution.VehicleToolGateway`)

Both `GuardrailProvider.MOCK` and `GuardrailProvider.REAL` providers share the exact same typed interface (`GuardrailClientAdapter`), enforcing identical contract compliance and fail-closed security properties across mock dev environments and real external endpoints.

---

## 2. Contract Version Handshake

- **Contract Version:** `1.0.0`
- **Handshake Mechanism:**
  - Client sends `X-Guardrail-Contract-Version: 1.0.0` HTTP header with every POST evaluation request.
  - Client includes `"contract_version": "1.0.0"` in every evaluation body (`/v1/evaluate/action`, `/v1/evaluate/query`, `/v1/confirmations/confirm`, `/v1/monitor/evaluate`).
  - Mismatched versions (e.g. `99.0.0`) trigger a typed `CONTRACT_VERSION_MISMATCH` HTTP 409 error or adapter exception.
  - Fail-closed guarantee: `execution_allowed = False`, 0 vehicle actuator handler calls.

---

## 3. Public Outcome Coverage & Zero-Handler-Call Verification

The Guardrail schema defines 7 public outcome types. `test_int01.py` exercises 4 of
them end-to-end through the orchestrator (`test_public_outcome_*`); the remaining 3
are defined in the contract/fixtures but are **not yet exercised by this PR's test
suite** and are called out explicitly below rather than claimed as verified:

| Outcome | Decision Purpose | Orchestrator Status | Vehicle Handler Calls | Verified Security Property |
| :--- | :--- | :--- | :---: | :--- |
| `ALLOW` | Authorized action | `COMPLETED` | **1** | Permit digest matches canonical proposal SHA256; executed once. |
| `BLOCK_UNSAFE` | Safety rule refusal (e.g. R002) | `BLOCKED` | **0** | Fail-closed; handler call count strictly ZERO. |
| `CONFIRM` | Confirmation required | `NEEDS_CONFIRMATION` | **0** | Returns confirmation ID & prompt; 0 handler calls. |
| `ANSWER` | Informational query | `COMPLETED` | **0** | Grounded facts response returned; 0 handler calls. |
| `BLOCK_UNAVAILABLE` | System state refusal | _not tested_ | _not tested_ | **Not covered by test_int01.py** — fixture exists in examples.json but no test drives it through the orchestrator. |
| `NOT_VOICE_ACTIONABLE` | Non-voice UI intent | _not tested_ | _not tested_ | **Not covered by test_int01.py** — fixture exists in examples.json but no test drives it through the orchestrator. |
| `UNKNOWN` | Unmapped outcome | _not tested_ | _not tested_ | **Not covered by test_int01.py** — fixture exists in examples.json but no test drives it through the orchestrator. |

---

## 4. Permit & Proposal Digest Compatibility

- **Digest Format:** `sha256:[0-9a-f]{64}` canonical hash over action proposal fields (`tool`, `arguments`, `session_id`, etc.).
- **Permit Binding:**
  - On `ALLOW`, `permit.proposal_digest` must match the SHA256 digest of the mapped canonical proposal.
  - Any mismatch in permit digest, proposal ID, or intent raises `PROPOSAL_MISMATCH` or `INVALID_PERMIT` and halts turn execution immediately.
  - Non-ALLOW outcomes (`BLOCK_*`, `CONFIRM`, `ANSWER`) must NOT include a permit. Any permit attached to a non-ALLOW outcome raises `PERMIT_FORBIDDEN`.

---

## 5. State Snapshot & Version Compatibility

- **State Version Tracking:** `state_version` integers are tracked across turn evaluations.
- **Relevant State Snapshot:** `relevant_state` dictionary (e.g., `{"gear": "P", "speed": 0}`) is parsed and attached to evaluation decisions.
- **Monitor Route (`/v1/monitor/evaluate`):** Accepts active action payload with state snapshot/version and returns updated Guardrail decision (e.g., `BLOCK_UNSAFE` at state_version 13).
- **Confirmation Re-evaluation (`/v1/confirmations/confirm`):** Submits confirmation request to obtain fresh evaluation decision bound to the proposal digest.

---

## 6. Degraded, Timeout & Error Scenarios

- **Network Failures & Unreachable Endpoints:**
  - State-changing proposals (`/v1/evaluate/action`): **0 retries** to prevent double-execution, raises `GUARDRAIL_UNAVAILABLE` with `retryable = False` and `execution_allowed = False`.
  - Read-only queries (`/v1/evaluate/query`): **Bounded retries** (up to `read_only_retries` count) with backoff before raising `GUARDRAIL_UNAVAILABLE` with `retryable = True`.
- **Malformed HTTP / Server Errors (HTTP 500):**
  - Invalid JSON or untyped HTTP errors raise `MALFORMED_GUARDRAIL_RESPONSE`.
  - Guarantees 0 handler execution calls under all malformed or error responses.

---

## 7. Joint Trace Correlation

The joint trace correlation maps identifiers across Agent turn, Guardrail adapter, and Vehicle execution gateway:
- **`session_id`**: Session boundary identifier.
- **`turn_id` / `source_turn_id`**: Traceable turn ID.
- **`proposal_id`**: Generated proposal identifier.
- **`request_id`**: Request tracking ID.
- **`trace` steps:** `(TurnState.RECEIVED -> TurnState.RESOLVING -> TurnState.PROPOSED -> TurnState.AUTHORIZING -> TurnState.EXECUTING -> TurnState.COMPLETED)`.

---

## 8. Verification & Test Suite Summary

- **Test Suite:** [`tests/integration/int-01/test_int01.py`](file:///E:/V-GUARDRAIL/guardrail-for-agent/tests/integration/int-01/test_int01.py)
- **Pass Rate:** 10/10 tests passed (100% success rate).
- **Consumer Contract Compatibility:** Pass rate 100% on both `GuardrailProvider.MOCK` and `GuardrailProvider.REAL`.
- **Known Gap:** `BLOCK_UNAVAILABLE`, `NOT_VOICE_ACTIONABLE`, and `UNKNOWN` outcomes are not yet exercised by an orchestrator-level test (see Section 3) — remains open against the "Agent chạy được mọi public outcome của Guardrail" acceptance criterion.
