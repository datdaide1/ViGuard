# UI Integration Report (INT-02)

**Task:** INT-02 — Chạy integration với UI thật  
**Sprint:** Sprint 2  
**Code Area:** `tests/integration/int-02`  
**Status:** Completed  

---

## 1. Overview & Integration Architecture

The **INT-02** integration suite validates the end-to-end API, payload, event stream, and lifecycle integration between:
1. **Agent-UI Framework Endpoint** (`vivi_agent.orchestrator.MessageEndpoint`)
2. **Pending Confirmation Manager** (`vivi_agent.confirmation.ConfirmationManager`)
3. **Simulation Controller API** (`vivi_agent.simulation.SimulationController`)
4. **Agent Event Pipeline & Event Store** (`vivi_agent.events.AgentEventStore`, `vivi_agent.events.AgentEventPipeline`)
5. **UI Mock Consumer Client** (`vivi_agent.contracts.agent_ui.v1.contract`)

The UI integration guarantees that the UI team can render the complete Agent lifecycle, vehicle state changes, active action progress, and error/degraded states using purely public payloads with zero access to private internal runtime state.

---

## 2. Request & Response API Endpoints

All 5 public UI request types and 5 response statuses defined in `agent-ui.schema.json` were integrated and verified:

| Request Type | Purpose | Corresponding Response Status | Verified Public Contract Properties |
| :--- | :--- | :--- | :--- |
| `message` | User turn message request | `completed`, `blocked`, `needs_confirmation`, `degraded`, `failed` | Validates public request envelope; returns validated public turn response. |
| `confirm` | Driver confirmation action | `completed`, `blocked` | Re-evaluates confirmation with Guardrail; single-use token consumption. |
| `cancel` | Driver cancellation action | `blocked` | Cancels pending confirmation; returns blocked status to UI. |
| `simulation_control` | Operator preset / state patch | Operator `state_changed` event | Mutates state with `ActorKind.OPERATOR`; triggers active action monitor. |
| `reset` | Vehicle & session state reset | Reset `state_changed` event | Resets machine to `parked_powered_off` (`ActorKind.SYSTEM`); clears session event store. |

---

## 3. Event Stream Ordering & Reconnect Semantics

- **Contiguous Sequence Guarantee:**
  - `AgentEventStore.append()` assigns strictly 1-based, contiguous sequence numbers (`sequence = 1, 2, 3...`) per session event stream.
- **Reconnect & Page Refresh Polling:**
  - UI fetches new events using `AgentEventStore.get_events(session_id, since_sequence=N)`.
  - Reconnect polling returns only events with `sequence > N`.
  - **Zero Action Replay Guarantee:** Refreshing or reconnecting the UI fetches historical event logs from `AgentEventStore` without triggering turn re-execution or duplicate actuator side-effects.

---

## 4. Zero Private Field Exposure

- **Public Redaction Policy:** `AgentEventStore` and `validate_public_payload` automatically reject and strip any private internal runtime keys, including:
  - `permit`, `permit_id`, `authorization`, `api_key`, `access_token`, `system_prompt`, `developer_prompt`, `hidden_reasoning`, `password`, `secret`.
- **Contract Enforcement:** `validate_public_payload` enforces strict shape validation on all incoming request objects, outgoing response objects, and emitted session event objects.

---

## 5. Six Hero Actions & Verified Fixtures

All 6 hero action intents were verified for UI public stream consumption:

| Hero Action Intent | Description | Target Component | Verified Event Flow |
| :--- | :--- | :--- | :--- |
| `open_door` | Mở cửa xe | `control_access` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `state_changed` |
| `activate_hda` | Highway Driving Assist | `active_action` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `active_action:started` |
| `activate_aac` | Adaptive Cruise Control | `active_action` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `active_action:started` |
| `activate_autopark` | Automatic Parking | `active_action` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `active_action:started` |
| `activate_campmode` | Camp Mode | `mode_control` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `state_changed` |
| `open_window` | Mở cửa sổ xe | `control_access` | `proposal` -> `decision:CONFIRM` -> `confirm` -> `execution:started` |

`MockUIClient` successfully renders timelines and vehicle state mutations for all 6 hero action fixtures without encountering missing fields or validation errors.

---

## 6. Error, Degraded & Refusal Payloads

- **`blocked`:** Contains policy `reason`, `rule_id`, and `state_version` (e.g. `R002` refusal on vehicle moving).
- **`degraded`:** Contains `degraded_capability`, `reason`, and `retryable` boolean flag.
- **`failed`:** Contains typed `error` object (`code`, `message`, `retryable`).
- **`needs_confirmation`:** Contains `confirmation_id` and ISO `expires_at` timestamp.

---

## 7. Verification Summary

- **Test Suite:** [`tests/integration/int-02/test_int02.py`](file:///E:/V-GUARDRAIL/guardrail-for-agent/tests/integration/int-02/test_int02.py)
- **Consumer Contract Test:** [`tests/contracts/agent_ui/test_consumer_contract.py`](file:///E:/V-GUARDRAIL/guardrail-for-agent/tests/contracts/agent_ui/test_consumer_contract.py)
- **Pass Rate:** 7/7 INT-02 integration tests passed (100% success rate). Total 38/38 integration & contract tests passed.
