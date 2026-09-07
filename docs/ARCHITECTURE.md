# Architecture

Two independent services with one HTTP contract between them.

```
                 ┌──────────────────────── agent/ ────────────────────────┐
   user text ───▶│  model router ─▶ tool registry ─▶ tool→intent mapper   │
                 │       │                                                │
                 │       ▼                                                │
                 │  ActionProposal {tool, arguments, session/turn ids}    │
                 └───────┬────────────────────────────────────────────────┘
                         │  POST /v1/evaluate/action
                         ▼
                 ┌──────────────────────── guardrail/ ───────────────────┐
                 │  service/  ─ recover intent (same map) ─┐             │
                 │  policy/   ◀───────────────────────────┘             │
                 │    read owned VehicleState snapshot                  │
                 │    evaluate 109 rules → one of 7 outcomes            │
                 │  service/  build decision (+ permit only on ALLOW)   │
                 └───────┬─────────────────────────────────────────────┘
                         │  GuardrailDecision / GuardrailError
                         ▼
                 ┌──────────────────────── agent/ ────────────────────────┐
                 │  ALLOW    → verify permit digest → execute once        │
                 │  CONFIRM  → ask user → re-POST to /confirmations/confirm│
                 │  BLOCK_*  → refuse, zero execution                     │
                 │  ANSWER   → verbalize the guardrail's structured facts │
                 └────────────────────────────────────────────────────────┘
```

## The guardrail — `guardrail/`

### `policy/` — constraint engine

| Module | Role |
|---|---|
| `conditions.py` | closed, `eval()`-free evaluator for the workbook's `condition` column |
| `rules.py` | loads `policy/constraints.csv` (109 rules / 53 intents / 104 gate + 5 monitor); **fails closed** if any count is off or any condition won't parse |
| `state.py` | `VehicleState` — 19 vehicle fields + 2 request parameters, names/enums from the workbook |
| `engine.py` | `PolicyEngine.evaluate(intent, state) → Decision` — exactly one of 7 outcomes, or fail-closed (no match / multi-match / eval error / unknown intent) |

The engine is deterministic and reproduces the workbook exactly (100% on the
labelled dataset). Fail-closed means `outcome = None`; the HTTP layer turns that
into a typed error, never an outcome.

### `classifier/` — text → intent (the gateway path only)

Used when a request arrives as free text (a UI/gateway), **not** on the
agent-authorization path. `tfidf.py` (TF-IDF char+word n-grams + LinearSVC) is
the primary classifier; `keyword.py` is the untrained baseline. See
`docs/METRICS.md`.

### `service/` — HTTP contract layer

stdlib `http.server`, no framework. Endpoints: `/v1/evaluate/action`,
`/v1/confirmations/confirm`, `/v1/monitor/evaluate`, `/v1/evaluate/query`,
`GET /v1/trace/{request_id}`, `GET /healthz`. Owns the vehicle-state mock
(`state_store.py`), the pending-confirmation store, the active-action registry,
the request trace (`trace.py`), and the schema-exact wire envelope + digest
(`envelope.py`). Details in `guardrail/service/README.md`.

## The agent — `agent/src/vehicle_agent/`

Turns a text request into exactly one registered tool call, executes its
handler, returns the result. Owns the intent/tool catalog, model routing, the
vehicle state machine, handler execution, responses, session/idempotency, and
the integration contracts. Does **not** own policy evaluation, the UI, or a
physical actuator.

| Module | Role |
|---|---|
| `runtime.py` | public composition, deterministic-first routing, session/idempotency |
| `catalog/` | 53 baseline intents + candidate capabilities; checksum + startup validation |
| `tools/registry/`, `tools/mapping/` | closed model-visible tool schemas; exact `(tool, action, target, value) → intent` |
| `model_providers/` | provider-neutral router (OpenAI / Gemini), RPM limit, bounded retry, secret redaction |
| `orchestrator/` | turn state machine; agent-containment prompt; the guardrail coordinator |
| `vehicle/state/`, `vehicle/execution/` | immutable versioned state; handler registry; execution verification |
| `behaviors/`, `queries/`, `responses/` | action / query / refusal / response catalogs |
| `authorization/` | stable authorization ports + digest/validation semantics |
| `integrations/aegis/` | the Aegis wire adapter + a deterministic mock server |
| `contracts/agent_ui/` | closed UI request / response / event contract |

The **authorization boundary** is a stable port (`ActionAuthorizer`,
`ConfirmationAuthorizer`, `MonitorAuthorizer`). All Aegis-specific HTTP/wire code
lives under `integrations/aegis`; core agent packages never import it. Another
authorization service could implement the same ports.

## The wire contract (v1)

Closed JSON envelopes, validated fail-closed on both sides:

- **`ActionProposal`** carries only `tool` + `arguments` + ids — never an intent,
  never free text. The guardrail recovers the intent independently with the same
  deterministic map the agent used, and the agent checks the returned
  `decision.intent` matches its own mapping.
- **`GuardrailDecision`** — `contract_version, kind, request_id, proposal_id,
  intent, outcome, rule_id, state_version, policy_checksum, reason_code,
  relevant_state`; optional `answer` / `confirmation` / `permit`. Any unexpected
  field fails the decision closed.
- **`ActionPermit`** — only on `ALLOW`, required on `ALLOW`. Bound to a sha256
  digest of the exact proposal, single-use, time-boxed; its `intent / rule_id /
  state_version / policy_checksum` must equal the decision's.
- **`CONFIRM`** issues a single-use, time-boxed `confirmation_id`. Confirming
  re-evaluates against a **fresh** state snapshot — a stale confirmation never
  carries the original permit forward.
- **Monitor** re-checks a running action; anything other than `ALLOW` is a
  fail-safe stop.

Schema: `agent/src/vehicle_agent/integrations/aegis/wire/guardrail-agent.schema.json`,
examples in `wire/examples.json`.
