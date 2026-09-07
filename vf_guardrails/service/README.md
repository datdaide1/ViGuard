# `vf_guardrails/service/` — HTTP contract layer (Guardrail↔Agent v1)

The Guardrail as a standalone HTTP service for the **agent-authorization path
(CON-01)**: the Agent's LLM picks a structured tool call and sends a closed
`ActionProposal` (no intent, no text); this service recovers the intent itself,
evaluates the shared `PolicyEngine` against the Guardrail-owned vehicle state,
and returns a schema-exact decision (+ a digest-bound single-use permit only on
`ALLOW`).

> **MÔ PHỎNG.** Không phải xe thật. Không có xác nhận an toàn của OEM. Mọi hành
> động chỉ chạy trong mock actuator của agent.

## Chạy

```bash
py -3 -m vf_guardrails.service                    # 127.0.0.1:8089
py -3 -m vf_guardrails.service --port 9000 --trace-file trace.jsonl
```

Demo cả hai service (guardrail + agent) end-to-end:

```bash
py -3 run_both.py
```

## Endpoints

| Method + path | Vào | Ra |
|---|---|---|
| `POST /v1/evaluate/action` | `ActionProposal` | `GuardrailDecision` — `ALLOW` (+`permit`) / `BLOCK_*` / `CONFIRM` (+`confirmation`) / `ANSWER` (+`answer`) / `UNKNOWN`, hoặc `GuardrailError` |
| `POST /v1/confirmations/confirm` | `{contract_version, request_id, confirmation_id, session_id}` | re-evaluate trên **state mới** → decision mới |
| `POST /v1/monitor/evaluate` | `{contract_version, request_id, active_action_id, intent, vehicle_state?}` | `ALLOW` = cứ chạy tiếp · outcome block + `rule_id` = dừng |
| `POST /v1/evaluate/query` | `{contract_version, tool, arguments}` | `ANSWER`/`UNKNOWN` + `answer={grounded, facts}` |
| `GET /healthz` | — | `{status, policy_checksum}` |
| `GET /v1/trace/{request_id}` | — | trace đầy đủ của request đó (PRD FR-14 / §16) |

**Status codes:** 200 decision · 409 sai `contract_version` / `CONFIRMATION_NOT_ACTIVE` ·
403 `CONFIRMATION_SESSION_MISMATCH` · 400 proposal/`vehicle_state` hỏng · 422 fail-closed
(mapping không có / engine fail-closed) · 404 route/trace không thấy.

## Module

| File | Vai trò |
|---|---|
| `tool_map.py` | 79 dòng `(tool,action,target,value)→intent` — **copy nguyên** của agent (`DEFAULT_MAPPING_RULES`), conformance-test row-by-row. Miss → `UNSUPPORTED_TOOL_MAPPING` (không đoán). |
| `state_store.py` | `VehicleStateStore` — `state_version` đơn điệu, snapshot bất biến, 4 preset. `validate_wire_vehicle_state` kiểm kiểu snapshot agent gửi (monitor). |
| `answer_facts.py` | Chiếu `answer={grounded, facts}` theo intent (5 state query + `explain_feature`). Agent verbalize. |
| `confirmations.py` | `PendingConfirmationStore` — id single-use, TTL 30 s, gắn session gốc. |
| `active_actions.py` | `ActiveActionRegistry` + 5 `MONITORED_INTENTS`. |
| `envelope.py` | Copy `proposal_digest` + `validate_action_proposal` (contract v1). Build decision/permit/error/confirmation/answer schema-exact. |
| `trace.py` | `TraceRecorder` — event từng stage (`guardrail_started`…`guardrail_completed`), mỗi event có `stage_ms` + `since_start_ms` + `policy_checksum`, không log secret. JSONL sink tùy chọn. |
| `app.py` | `GuardrailService.handle(path, payload) → (status, body)` — core không phụ thuộc transport. |
| `http.py` / `__main__.py` | stdlib `ThreadingHTTPServer`, zero dep (P2-D4/D5). |

## Quyết định (P2-D1..D5)

D1 hai service tách, không import chéo (bảng map + digest được **copy**, test khoá drift).
D2 guardrail trả facts có cấu trúc, agent verbalize. D3 `ANSWER` đọc state. D4 stdlib http.
D5 `py -3 -m vf_guardrails.service`.
