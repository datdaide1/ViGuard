# Agent–UI public contract v1

This contract is the only payload surface the UI needs to render Agent and
Vehicle lifecycle state. It deliberately excludes Guardrail permits, model
thought payloads, prompts, credentials, and other execution-authority data.

## Public operations

| Request type | Purpose |
| --- | --- |
| `message` | Start one Agent turn from user text. |
| `confirm` / `cancel` | Resolve one pending confirmation. Confirm always causes fresh Guardrail evaluation. |
| `simulation_control` | Apply an operator-owned preset/state/tick; it is not an Agent tool. |
| `reset` | Reset session, simulator, or both without replaying side effects. |

Responses use exactly one of `completed`, `blocked`, `needs_confirmation`,
`failed`, or `degraded`. Policy outcome and execution status remain separate:
the UI learns policy decisions from `decision` events and execution state from
`execution`/`active_action` events.

## Ordering

Every event in a session has a contiguous, increasing `sequence`. For an Agent
action the legal causal order is:

1. `proposal`
2. `decision`
3. only after `ALLOW`: exactly one `execution(started)`
4. zero or more `state_changed` / `active_action` events
5. exactly one `execution(succeeded|failed|stopped)` and/or terminal `active_action`

`BLOCK_*` and `CONFIRM` never have execution events. A later confirmation is a
new request and fresh decision. `OPERATOR` state changes may occur without an
Agent proposal/execution and preserve their distinct actor provenance.

`validate_event_stream` enforces contiguous order; matching session, turn,
request, proposal and execution correlation; proposal-before-decision;
ALLOW-before-execution; a single execution terminal transition; and no Agent
state/active-action effects after execution terminates.

## Visibility and evolution

Payload shapes are closed. The semantic validator recursively rejects secret,
credential, prompt, hidden-reasoning, provider-thought, and permit fields.
Public payloads expose only stable reason codes and grounded display text.

Version matching is exact for v1. Additive or breaking changes require an
explicitly agreed contract version; consumers must not silently accept unknown
fields.

Files:

- `agent-ui.schema.json`: closed request, response, and event schema.
- `contract.py`: dependency-free semantic/redaction/ordering validator.
- `fixtures.json`: five request types, five response statuses, six hero action samples, and three complete demo scenario streams.
