# Hướng dẫn tích hợp Guardrail, UI và actuator

## 1. Contract tổng quát

Deployment nên đặt Guardrail trước Agent:

```text
text → Guardrail classify/rules → ALLOW | CONFIRM | BLOCK
ALLOW → Agent với trusted intent hint → validated tool → actuator
CONFIRM → UI hỏi lại → fresh Guardrail decision → Agent nếu ALLOW
BLOCK → trả response của Guardrail, zero Agent execution
```

Không truyền raw permit, policy internals hoặc hidden model data cho UI.

## 2. Ghép Guardrail

`GuardedAgentCoordinator` nhận contract nhỏ:

```python
from vivi_agent.orchestrator import (
    GuardedAgentCoordinator,
    GuardedTurnRequest,
    UpstreamGuardrailDecision,
)

result = coordinator.handle_decision(
    GuardedTurnRequest("session-1", "turn-1", "request-1", "Mở cốp"),
    UpstreamGuardrailDecision(
        request_id="request-1",
        intent="open_trunk",
        outcome="ALLOW",
        state_version=42,
    ),
)
```

Block/confirm phải có human-facing `response`. Confirm cần unique
`confirmation_id` và future `expires_at`. Khi user đồng ý, caller phải gọi lại
Guardrail trên state mới rồi truyền `refreshed_decision`; không reuse decision
cũ. Từ chối confirm trả blocked/cancelled và không gọi Agent.

Nếu tích hợp ViGuard wire v1, dùng `integrations/viguard/` và schema/examples
trong `integrations/viguard/wire/`. Core Agent chỉ import `authorization/` ports;
integration implementation không được leak vào model/tool packages.

## 3. Ghép UI

Canonical UI contract nằm tại `contracts/agent_ui/v1/`:

- validate mọi request và response bằng `validate_public_payload`;
- `MessageEndpoint` là callable framework-neutral, có thể bọc bằng FastAPI,
  Flask, gRPC hoặc WebSocket adapter;
- response status gồm `completed`, `blocked`, `needs_confirmation`, `failed`,
  `degraded`;
- public events có sequence tăng liên tục; UI ACK sau render và reconnect từ
  sequence cuối để không replay side effect;
- không expose prompt, chain-of-thought, API key, permit hay provider payload.

UI adapter nên map mỗi request type một cách tường minh. `simulation_control`
là operator API và không được đăng ký làm Agent tool.

## 4. Ghép actuator/simulator

`HandlerRegistry` là execution seam. Có hai loại behavior:

1. State-backed handler: mutate `VehicleStateMachine` atomically và trả version.
2. Command-only handler: trả `one_shot_event` như
   `candidate_capability_turnon_ac_commanded`.

Để ghép actuator thật hoặc simulator khác, adapter nhận canonical intent/tool
arguments, dispatch lệnh, trả structured result và đẩy telemetry về state
provider. Không báo completed nếu actuator timeout/fail. Không tự tăng state
version nếu chưa có state transition/telemetry hợp lệ.

Package không chứa CAN, ECU mapping hay hardware safety case. Team actuator
phải định nghĩa timeout, acknowledgement, idempotency key, retry semantics và
reconciliation với telemetry của hệ thống đích.

## 5. Ghép model

Biến môi trường chuẩn:

| Biến | Default |
| --- | --- |
| `AGENT_MODEL_PROVIDER` | `auto` |
| `AGENT_MODEL_PROVIDER_PRIORITY` | `openai,gemini` |
| `GEMINI_MODEL_ID` | `gemini-3.5-flash-lite` |
| `OPENAI_MODEL_ID` | `gpt-5-mini` |
| `AGENT_MODEL_TIMEOUT_SECONDS` | `10` |
| `AGENT_MODEL_RPM` | `12` |

Production secret chỉ lấy từ secret manager/process environment. Nếu cần SDK
riêng, inject callable `ProviderTransport(payload, timeout_seconds)`; transport
không được log credential hoặc raw reasoning.

## 6. Integration acceptance checklist

- Guardrail block và pending confirm tạo zero actuator call.
- Accepted confirm dùng fresh decision/current state và không replay được.
- Agent intent sau mapping khớp trusted intent của Guardrail.
- Duplicate `(session_id, request_id)` chạy side effect đúng một lần.
- Actuator failure không được render thành completed.
- Query path không gọi actuator.
- UI reconnect không replay handler.
- Logs không chứa key, permit, prompt hoặc raw provider body.
- Health/readiness phân biệt process live với dependency ready.
