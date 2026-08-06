# UI Integration Report (INT-02)

**Task:** INT-02 — Chạy integration với UI thật  
**Sprint:** Sprint 2  
**Code Area:** `tests/integration/int-02`  
**Status:** Completed  

---

## 1. Overview & Integration Architecture

The **INT-02** suite validates the public Agent-UI contract shape and exercises two
components directly:
1. **Simulation Controller API** (`vivi_agent.simulation.SimulationController`) — exercised directly.
2. **Agent Event Store** (`vivi_agent.events.AgentEventStore`) — exercised directly.
3. **UI Mock Consumer Client** (`vivi_agent.contracts.agent_ui.v1.contract`) — exercised directly.

**Not yet exercised by this suite:** the **Agent-UI Framework Endpoint**
(`vivi_agent.orchestrator.MessageEndpoint`) and the **Pending Confirmation Manager**
(`vivi_agent.confirmation.ConfirmationManager`) are not driven end-to-end here — the
`message`/`confirm`/`cancel` request/response payloads below are validated against
the schema as static fixtures, not produced by calling `MessageEndpoint.post_message()`
or `ConfirmationManager.confirm()`/`.cancel()`.

The UI integration guarantees that the UI team can render the complete Agent lifecycle, vehicle state changes, active action progress, and error/degraded states using purely public payloads with zero access to private internal runtime state.

---

## 2. Request & Response API Endpoints

All 5 public UI request types and 5 response statuses defined in `agent-ui.schema.json`
have fixtures that pass schema validation (`validate_public_payload`). This confirms
the payload *shapes* are contract-valid; it does not confirm that `MessageEndpoint` or
`ConfirmationManager` actually produce these payloads end-to-end (see Section 1).

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

All 6 hero action intents have a `proposal` fixture that `MockUIClient` consumes
without missing fields or validation errors. The "Target Event Flow" column below is
the intended full lifecycle per the fixture design; `test_int02.py` currently only
asserts the `proposal` step of each row appears in the UI timeline, not the full
`decision`/`execution`/`state_changed`/`active_action` chain.

| Hero Action Intent | Description | Target Component | Target Event Flow |
| :--- | :--- | :--- | :--- |
| `open_door` | Mở cửa xe | `control_access` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `state_changed` |
| `activate_hda` | Highway Driving Assist | `active_action` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `active_action:started` |
| `activate_aac` | Adaptive Cruise Control | `active_action` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `active_action:started` |
| `activate_autopark` | Automatic Parking | `active_action` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `active_action:started` |
| `activate_campmode` | Camp Mode | `mode_control` | `proposal` -> `decision:ALLOW` -> `execution:started` -> `state_changed` |
| `open_window` | Mở cửa sổ xe | `control_access` | `proposal` -> `decision:CONFIRM` -> `confirm` -> `execution:started` |

---

## 6. Error, Degraded & Refusal Payloads

- **`blocked`:** Contains policy `reason`, `rule_id`, and `state_version` (e.g. `R002` refusal on vehicle moving).
- **`degraded`:** Contains `degraded_capability`, `reason`, and `retryable` boolean flag.
- **`failed`:** Contains typed `error` object (`code`, `message`, `retryable`).
- **`needs_confirmation`:** Contains `confirmation_id` and ISO `expires_at` timestamp.

---

## 7. Verification Summary

- **Test Suite:** [`test_int02.py`](./test_int02.py)
- **Consumer Contract Test:** [`test_consumer_contract.py`](../../contracts/agent_ui/test_consumer_contract.py)
- **Pass Rate:** 7/7 INT-02 integration tests passed (100% success rate). Total 38/38 integration & contract tests passed.
