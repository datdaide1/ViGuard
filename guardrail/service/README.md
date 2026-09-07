# `guardrail/service/` — HTTP contract layer

The guardrail as a standalone HTTP service for the **agent-authorization path**:
the agent sends a closed `ActionProposal` (a structured tool call — no intent, no
free text); this service recovers the intent with the same deterministic map the
agent used, evaluates the shared `PolicyEngine` against the guardrail-owned
vehicle state, and returns a schema-exact decision with a digest-bound single-use
permit only on `ALLOW`.

> Simulation only — no real vehicle, no OEM sign-off. Every action runs in the
> agent's mock actuator.

## Run

```bash
py -3 -m guardrail.service                                  # 127.0.0.1:8089
py -3 -m guardrail.service --port 9000 --trace-file trace.jsonl
py -3 run_demo.py                                           # both services, end-to-end
```

## Endpoints

| Method + path | In | Out |
|---|---|---|
| `POST /v1/evaluate/action` | `ActionProposal` | `GuardrailDecision` — `ALLOW` (+`permit`) / `BLOCK_*` / `CONFIRM` (+`confirmation`) / `ANSWER` (+`answer`) / `UNKNOWN`, or `GuardrailError` |
| `POST /v1/confirmations/confirm` | `{contract_version, request_id, confirmation_id, session_id}` | re-evaluate against a **fresh** state snapshot → a new decision |
| `POST /v1/monitor/evaluate` | `{contract_version, request_id, active_action_id, intent, vehicle_state?}` | `ALLOW` = keep running · a blocking outcome + `rule_id` = stop |
| `POST /v1/evaluate/query` | `{contract_version, tool, arguments}` | `ANSWER` / `UNKNOWN` + `answer = {grounded, facts}` |
| `GET /healthz` | — | `{status, policy_checksum}` |
| `GET /v1/trace/{request_id}` | — | the full request trace |

**Status codes:** 200 decision · 409 wrong `contract_version` /
`CONFIRMATION_NOT_ACTIVE` · 403 `CONFIRMATION_SESSION_MISMATCH` · 400 malformed
proposal / `vehicle_state` · 422 fail-closed (no mapping / engine fail-closed) ·
404 unknown route or trace.

## Modules

| File | Role |
|---|---|
| `tool_map.py` | `(tool, action, target, value) → intent` — a verbatim copy of the agent's map, row-by-row conformance-tested. A miss fails closed (`UNSUPPORTED_TOOL_MAPPING`), never a guess. |
| `state_store.py` | `VehicleStateStore` — monotonic `state_version`, immutable per-request snapshot, presets. `validate_wire_vehicle_state` type-checks an agent-supplied monitor snapshot. |
| `answer_facts.py` | Projects `answer = {grounded, facts}` per intent (5 state queries + `explain_feature`). The agent verbalizes. |
| `confirmations.py` | `PendingConfirmationStore` — single-use id, TTL, bound to the originating session. |
| `active_actions.py` | `ActiveActionRegistry` + the 5 `MONITORED_INTENTS`. |
| `envelope.py` | Copied `proposal_digest` + `validate_action_proposal`; builds schema-exact decision / permit / error / confirmation / answer. |
| `trace.py` | `TraceRecorder` — per-stage events (`guardrail_started` … `guardrail_completed`), each with `stage_ms` + `since_start_ms` + `policy_checksum`. No secrets. Optional JSONL sink. |
| `app.py` | `GuardrailService.handle(path, payload) → (status, body)` — transport-free core. |
| `http.py` / `__main__.py` | stdlib `ThreadingHTTPServer`, zero third-party deps. |

See `docs/DECISIONS.md` for the contract and digest rules.
