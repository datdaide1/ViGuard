# Kiến trúc ViVi Agent

## 1. Mục tiêu và boundary

ViVi Agent biến một yêu cầu text thành đúng một tool call đã đăng ký, thực thi
handler của tool và trả kết quả. Agent sở hữu intent/tool catalog, model
routing, state model, handler execution, response, session/idempotency và các
contract tích hợp. Agent không sở hữu UI, policy workbook, rule evaluation,
CAN bus hay actuator vật lý.

Hai composition mode được hỗ trợ:

1. `AgentRuntime` chạy độc lập cho simulator/test: text → route → tool → action.
2. `GuardedAgentCoordinator` dùng khi ghép hệ thống: Guardrail quyết định trước;
   chỉ `ALLOW` hoặc confirmation được chấp nhận kèm decision mới đi vào Agent.

```text
UI / caller
    │ text + request/session IDs
    ▼
External Guardrail (recommended deployment boundary)
    ├─ BLOCK   → response từ chối, zero execution
    ├─ CONFIRM → pending; accept cần fresh decision
    └─ ALLOW   → trusted intent hint
                    │
                    ▼
             ViVi Text Agent
             ├─ deterministic sample router
             └─ Gemini/OpenAI tool selection fallback
                    │ validated tool call
                    ▼
        ToolRegistry → ToolMapper → HandlerRegistry
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
  VehicleState mutation   typed one-shot command
          │                    │
          └──── execution result / telemetry ────┘
```

## 2. Runtime flow

`AgentRuntime.handle_text` nhận `text`, `session_id`, `request_id`, `turn_id`
và optional trusted `intent_hint`. Runtime đọc immutable vehicle snapshot và
đưa snapshot vào system context; state do user nói trong text không được xem là
trusted state.

`DeterministicFirstRouter` ưu tiên sample utterance đã review để giảm latency và
quota. Route cần free-text parameter không bao giờ dùng placeholder; nó rơi xuống
model để extract giá trị hoặc clarification. Model output phải qua closed tool
schema và exact mapping trước execution. Mọi tool, target, action hoặc field lạ
đều bị từ chối.

Runtime cache tối đa 1.024 request result và giữ 12 history message mỗi session.
Lock theo request bảo đảm duplicate request chạy đúng một lần; lock theo session
serialize side effects nhưng không chặn session khác.

## 3. Catalog và tool model

Catalog runtime có 123 intent:

- baseline 53 intent từ manifest v1;
- 70 Agent capability candidate được lưu tại `catalog/candidate.py`, không chứa
  condition, outcome hoặc rule của Guardrail.

Startup fail closed nếu manifest checksum, tool registry, mapping coverage,
query coverage, behavior coverage hoặc monitored intent coverage bị lệch.
`control_vehicle_capability` chứa capability glossary tiếng Việt để model nhỏ
như Gemini 3.5 Flash Lite có đủ semantic context. Free-text `value` tối đa 512
ký tự và không được model cung cấp state, permit, rule hoặc outcome.

## 4. Execution và VehicleState

`VehicleStateMachine` giữ immutable versioned state. Handler có state field dùng
atomic transition và tăng `state_version`. Capability chưa được mô hình hóa
thành state field phát one-shot command có intent-specific event name; command
này là lệnh cho actuator adapter, không phải bằng chứng xe thật đã đổi trạng thái.
Deployment phải cập nhật state từ telemetry sau khi actuator hoàn tất.

Query không gọi actuator. Nếu dữ liệu như ETA, range hoặc charge limit chưa có
trong trusted state, responder trả `UNKNOWN` thay vì đoán. `get_chargestatus`
đọc trực tiếp `power.charging` hiện có.

## 5. Model boundary và latency

Provider-neutral router hỗ trợ Gemini và OpenAI. Default Gemini là
`gemini-3.5-flash-lite`; rate limiter mặc định 12 RPM, có tối đa một retry cho
timeout, connection error, HTTP 429 và 5xx trước khi proposal hợp lệ tồn tại.
Không retry 4xx hoặc action sau khi side effect bắt đầu.

Provider error chỉ expose allowlisted `status/code/message`, redact secret và
truncate; raw response body, key và authorization header không được log.

## 6. Security model

System prompt coi user/history là untrusted data, cấm thay system instruction,
tool/argument giả, credential extraction và hidden reasoning request. History
không được chứa role `system`. Đây là defense-in-depth cho Agent, không phải
policy engine và không tạo quyền thực thi.

External Guardrail vẫn chịu trách nhiệm classify/policy/condition và trả
`ALLOW`, `CONFIRM` hoặc block. Confirmation accept không biến decision cũ thành
permit; coordinator yêu cầu fresh Guardrail decision, kiểm tra intent không đổi
và chống concurrent replay.

## 7. Module map

| Module | Trách nhiệm |
| --- | --- |
| `runtime.py` | Public composition, deterministic routing, session/idempotency |
| `catalog/` | Intent inventory, checksum và startup validation |
| `tools/registry/` | Model-visible closed tool schemas |
| `tools/mapping/` | Exact tool call → canonical intent |
| `model_providers/` | Provider adapters, selection, HTTP transports, RPM/retry |
| `orchestrator/` | Turn state machine, Agent containment, Guardrail coordinator |
| `vehicle/state/` | Immutable state, invariants, versioned transition |
| `vehicle/execution/` | Handler registry, generic handlers, execution verification |
| `behaviors/`, `queries/`, `responses/` | Action/query/refusal/response catalogs |
| `authorization/` | Stable external authorization ports and semantic contract |
| `integrations/viguard/` | Optional ViGuard wire adapter and mock |
| `contracts/agent_ui/` | Closed UI request/response/event contract |
| `events/`, `operations/`, `simulation/` | Public lifecycle, reset/health, simulator controls |

## 8. Architectural decisions

- External authorization được inject qua stable port; xem
  [decisions/ADR-001-EXTERNAL-AUTHORIZATION-PORT.md](decisions/ADR-001-EXTERNAL-AUTHORIZATION-PORT.md).
- Tool definitions và mappings là code-reviewed static data; model không tạo
  tool hay executable code.
- Query thiếu dữ liệu trả unknown; không dùng LLM để bịa telemetry.
- In-process simulator chứng minh software behavior, không chứng nhận safety xe thật.
