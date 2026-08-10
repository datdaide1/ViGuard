# ViVi Agent integration guide

Tài liệu này dành cho team Guardrail, UI và người đóng gói deployment muốn tích hợp runtime ViVi Agent hiện có. Checkout này cung cấp domain runtime và các endpoint framework-neutral; **chưa cung cấp HTTP server, CLI production, ASR, CAN bus hay actuator xe thật**. Adapter HTTP/WebSocket và transport tới model/Guardrail là trách nhiệm của deployment layer.

## 1. Chạy kiểm tra đầu tiên

Yêu cầu Python 3.11+ và `pytest`. Từ repository root trên PowerShell:

```powershell
$env:PYTHONPATH = ".;src"
python -m pytest --import-mode=importlib `
  tests/test_runtime_bootstrap.py `
  tests/contracts/guardrail/test_consumer_contract.py `
  tests/contracts/agent_ui/test_consumer_contract.py `
  tests/operations/test_runtime_operations.py -q
```

Kết quả pass chứng minh catalog/registry khởi động được, payload hai contract được validate, và reset/readiness/reconnect tuân theo OPS-01. Nó không chứng minh endpoint Guardrail/UI bên ngoài đang online.

Runtime catalog được tạo bằng:

```python
from vivi_agent import build_runtime

runtime = build_runtime()
print(runtime.intent_manifest.checksum)
print(runtime.tool_registry.checksum)
```

Có thể override hai artifact mà không sửa code bằng `VIVI_AGENT_INTENT_MANIFEST_PATH` và `VIVI_AGENT_TOOL_REGISTRY_PATH`. Loader fail closed nếu artifact hoặc mapping không hợp lệ.

## 2. Prerequisites và cấu hình model

Model boundary nhận transport đồng bộ do deployment layer inject. Các biến cấu hình chuẩn:

| Biến | Giá trị/mặc định |
| --- | --- |
| `AGENT_MODEL_PROVIDER` | `auto`, `openai` hoặc `gemini`; mặc định `auto` |
| `AGENT_MODEL_PROVIDER_PRIORITY` | mặc định `openai,gemini` |
| `OPENAI_MODEL_ID` | mặc định `gpt-5-mini` |
| `GEMINI_MODEL_ID` | mặc định `gemini-3.6-flash` |
| `AGENT_MODEL_TIMEOUT_SECONDS` | mặc định `10` |
| `OPENAI_API_KEY`, `GEMINI_API_KEY` | chỉ ở backend; không được đưa vào public event |

Readiness của model đòi hỏi đồng thời credential và transport đã cấu hình. Không có mock fallback ngầm. Chi tiết seam và retry/pinning nằm tại [`src/vivi_agent/model_providers/README.md`](../../../src/vivi_agent/model_providers/README.md).

## 3. Biên tích hợp Guardrail

Canonical contract là [`src/vivi_agent/contracts/guardrail/v1/README.md`](../../../src/vivi_agent/contracts/guardrail/v1/README.md), schema là `guardrail-agent.schema.json`, sample là `examples.json`. Deployment adapter ánh xạ ba operation:

| Operation | Ý nghĩa |
| --- | --- |
| `POST /v1/evaluate/action` | đánh giá proposal mới |
| `POST /v1/confirmations/confirm` | xác nhận và đánh giá lại trên state mới |
| `POST /v1/monitor/evaluate` | đánh giá lại active action khi state đổi |

Ví dụ proposal tối thiểu (giá trị ID/checksum chỉ để minh họa):

```json
{
  "contract_version": "1.0.0",
  "proposal_id": "prop-001",
  "session_id": "demo-01",
  "source_turn_id": "turn-001",
  "tool": "control_access",
  "arguments": {"action": "open", "target": "driver_door"},
  "model_provider": "openai",
  "model_id": "gpt-5-mini"
}
```

Chỉ outcome `ALLOW` được mang permit proposal-bound, có hạn và single-use. `CONFIRM` không phải permit; confirm tạo request mới và bắt buộc đánh giá lại. Timeout, non-2xx, version mismatch hoặc response sai schema phải trở thành typed integration error và **zero execution**. Không retry operation có thể cấp hoặc tiêu thụ authority sau khi đã có kết quả không chắc chắn.

`examples.json` là nguồn sample payload đầy đủ cho bảy outcome, confirmation và monitor. Không copy permit sang UI, log public hoặc analytics.

## 4. Biên tích hợp UI

Canonical contract là [`src/vivi_agent/contracts/agent_ui/v1/README.md`](../../../src/vivi_agent/contracts/agent_ui/v1/README.md), schema là `agent-ui.schema.json`, sample là `fixtures.json`.

UI gửi một trong năm request type: `message`, `confirm`, `cancel`, `simulation_control`, `reset`. Ví dụ message:

```json
{
  "contract_version": "1.0.0",
  "kind": "request",
  "request_type": "message",
  "session_id": "session-demo",
  "turn_id": "turn-001",
  "request_id": "req-001",
  "occurred_at": "2026-08-03T09:00:00Z",
  "message": "Mở cửa ghế lái"
}
```

### Routing status của năm request type

Checkout này chưa có một HTTP/WebSocket dispatcher chung. Deployment phải validate payload bằng `validate_public_payload(...)` trước khi route và validate public response/event trước khi gửi về UI.

| Request type | Callable hiện có | Mapping bắt buộc | Trạng thái public adapter |
| --- | --- | --- | --- |
| `message` | `MessageEndpoint.post_message(payload, cancellation)` | truyền nguyên closed payload đã validate | Có framework-neutral endpoint |
| `confirm` | `ConfirmationManager.confirm(...)` | `confirmation_id`, `session_id`, injected `GuardrailClientAdapter`, `VehicleToolGateway`, `request_id`, cancellation token | Chưa có Agent–UI endpoint/response serializer |
| `cancel` | `ConfirmationManager.cancel(...)` | `confirmation_id`, `session_id`; không gọi Guardrail hoặc executor | Chưa có Agent–UI endpoint/response serializer |
| `simulation_control` | `SimulationController`, và `GuardrailMonitorAdapter.tick(...)` cho manual monitor tick | xem bảng control bên dưới; actor/operator ID phải lấy từ authenticated operator context, không tin giá trị do model sinh | Chưa có public dispatcher |
| `reset` | `OperationsEndpoint.post_reset(payload)` | truyền closed reset payload | Có framework-neutral endpoint |

Health và reconnect không phải request type trong Agent–UI v1: deployment gọi lần lượt `OperationsEndpoint.get_health()` và `OperationsEndpoint.reconnect(session_id, connection_id)`. ACK được ghi qua `UIConnectionRegistry.acknowledge(...)`; checkout chưa cung cấp HTTP endpoint cho ACK.

Adapter cho `confirm` phải chuyển `ConfirmationResult` thành một Agent–UI response hợp lệ và không được trả `decision`, permit hoặc raw Guardrail payload ra UI. Fresh `ALLOW` chỉ được thực thi qua injected `VehicleToolGateway`; mọi outcome/error khác là zero action. Adapter cho `cancel` chuyển result sang public response nhưng tuyệt đối không gọi Guardrail/executor.

Contract `simulation_control.parameters` hiện là object mở và chưa đóng schema chi tiết. Runtime seam khả dụng là:

| `control` | Runtime seam | Tình trạng mapping |
| --- | --- | --- |
| `load_preset` | `SimulationController.apply_preset(parameters["preset"], operator_id=...)` | Runtime chỉ nhận `parked`, `driving`, `highway_hda`, `charging`, `camp`; fixture contract hiện dùng `highway` nên deployment không được suy diễn alias cho tới khi contract được thống nhất |
| `set_state` | `SimulationControl(...)` rồi `SimulationController.apply_controls(...)` | Chưa có canonical parameter shape/serializer; cần contract revision hoặc adapter agreement trước khi expose |
| `tick` | `GuardrailMonitorAdapter.tick(session_id=...)` | Chưa có canonical parameter/result mapping; không được coi tick là vehicle mutation |

Vì ba public adapter/mapping trên chưa tồn tại, tài liệu này **không claim toàn bộ năm request type đã runnable qua một application endpoint**. DOC-01 giữ trạng thái `in_progress`; owner của deployment wiring cần bổ sung adapter tests rồi mới chuyển `completed`.

`simulation_control` là operator API riêng, không đăng ký trong Agent tool registry và không đi qua model.

UI render response status `completed`, `blocked`, `needs_confirmation`, `failed` hoặc `degraded`; đồng thời consume public events theo `sequence`. Luồng action hợp lệ là `proposal → decision → execution(started) → state/active-action events → terminal execution`. `BLOCK_*` và `CONFIRM` không có execution event.

Khi mất kết nối, client ACK sequence cuối đã render. `UIConnectionRegistry.reconnect(session_id, connection_id)` chỉ trả event có sequence lớn hơn ACK; việc đọc lại event **không replay side effect**. Client deduplicate bằng `(session_id, sequence)` và ACK sau khi render thành công.

## 5. Reset, preset và readiness

`OperationsEndpoint.post_reset(payload)` nhận `scope`:

- `session`: dừng action, hủy confirmation, revoke permit, xóa event/cursor của đúng session; không reset state xe.
- `simulator`: invalidates state-dependent data của mọi session và reset xe về `parked_powered_off`.
- `all`: reset toàn bộ runtime và simulator.

Reset hoàn tất không giữ usable permit hay active action cũ. Nếu vehicle reset lỗi, runtime trả typed error `VEHICLE_RESET_FAILED`; caller không được tiếp tục scenario trên state không chắc chắn.

`SimulationController.apply_preset(...)` hỗ trợ `parked`, `driving`, `highway_hda`, `charging`, `camp`. Đây là operator evidence (`actor=OPERATOR`), không phải Agent execution. `OperationsEndpoint.get_health()` tách `live` khỏi `ready` và nêu rõ dependency `model`, `guardrail`, `ui` nào chưa available.

## 6. Mock và integration thật

| Thành phần | Offline/mock evidence | Real integration gate |
| --- | --- | --- |
| Model | fake transport trong unit/E2E tests | credential + provider transport thật |
| Guardrail | contract mock/test doubles | endpoint team Guardrail, contract version và policy checksum được thống nhất |
| Vehicle | `VehicleStateMachine` + mock handlers | không nằm trong pilot; không có vehicle actuator thật |
| UI | contract fixtures + mock consumer | UI thật render public payload/event và ACK/reconnect |

Mock pass chỉ chứng minh Agent-side protocol và safety boundary tương ứng. Team Guardrail sở hữu correctness của classifier/policy/rule; team UI sở hữu visual/interaction quality; Agent team sở hữu proposal/decision/execution ordering, permit enforcement, state transition và public event emission.

## 7. Degraded modes

| Hiện tượng | Public behavior | Execution |
| --- | --- | --- |
| Model unavailable | response `degraded`, capability `intent_resolution`, retryable theo payload | zero action |
| Guardrail unavailable/malformed | fail closed; typed Agent-side integration failure | zero action |
| Vehicle gateway failure | response `failed` với stable error code | không báo completed |
| UI disconnected | Agent lưu event; reconnect từ ACK cursor | không replay handler |
| Readiness false | health vẫn `live=true`, nêu dependency lỗi | không nhận traffic cần dependency đó |

Troubleshooting chi tiết và ba scenario có trong [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md).

## 8. Claim boundary

Các test và tài liệu này là **Agent/Vehicle simulator evidence**. Chúng không chứng nhận policy đúng cho xe thật, model không thể bị prompt injection, Guardrail production đã đạt SLA, UI đã đạt chất lượng hình ảnh, hay hệ thống tuân thủ ISO 26262/OEM requirements. Release chỉ được claim end-to-end sau khi external gates tương ứng có evidence từ team sở hữu.
