# Guardrail-Agent contract v1.0.0

This directory is the Agent team's consumer contract for Guardrail. It defines protocol shape and fail-closed semantics; it does not implement or certify Guardrail policy logic.

## Operations

| Operation | Request | Successful response |
|---|---|---|
| `POST /v1/evaluate/action` | `actionProposal` | `guardrailResult` |
| `POST /v1/confirmations/confirm` | `confirmationRequest` | fresh `guardrailResult` |
| `POST /v1/monitor/evaluate` | `monitorRequest` | fresh `guardrailResult` |

Transport failures and malformed responses become local `ContractValidationError` values and allow zero execution. `GuardrailError` is a tagged integration error, not an eighth policy outcome.

## Outcome and permit rules

The closed outcome set is `ALLOW`, `BLOCK_UNSAFE`, `BLOCK_UNAVAILABLE`, `CONFIRM`, `NOT_VOICE_ACTIONABLE`, `ANSWER`, and `UNKNOWN`.

- Only `ALLOW` contains an `ActionPermit`.
- A permit is proposal-bound, expiring, and single-use.
- `CONFIRM` contains only a pending confirmation. Confirming sends a new request and requires a fresh decision; the old decision never becomes executable.
- Query outcomes never contain permits and never reach an actuator.
- Monitor evaluation produces a new decision. The Agent-side monitor adapter decides whether to continue or request a registered stop path in later tasks; Guardrail responses do not mutate simulator state directly.

## Proposal digest

`proposal_digest` is `sha256:` followed by the lowercase SHA-256 hex digest of UTF-8 JSON for this projection:

```json
{
  "arguments": {},
  "contract_version": "1.0.0",
  "proposal_id": "...",
  "session_id": "...",
  "source_turn_id": "...",
  "tool": "..."
}
```

Serialization uses lexicographically sorted keys, no insignificant whitespace, unescaped Unicode, and rejects NaN/Infinity. Provider/model fields are trace metadata and are deliberately excluded. The Vehicle Tool Gateway must additionally compare the permit's intent, rule, state version, policy checksum, expiry, and consumption status before execution.

## Compatibility

Version matching is exact in v1. A mismatch raises `CONTRACT_VERSION_MISMATCH` and is fail-closed. Any compatible additive evolution requires a new agreed contract version; consumers must not silently ignore unknown execution-authority fields.

## Artifacts

- `guardrail-agent.schema.json`: JSON Schema Draft 2020-12 definitions.
- `examples.json`: the seven outcomes, typed error, confirmation request, and monitor request.
- `../../authorization/contract.py`: Agent-owned semantic validation and digest reference.
- `../mock_server.py`: deterministic protocol mock for Agent integration tests only.
