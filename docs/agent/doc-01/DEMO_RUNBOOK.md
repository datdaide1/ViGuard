# ViVi Agent demo runbook

Runbook này chạy ba scenario SCN-01/02/03 bằng harness đã version-control. Mỗi scenario tự dựng runtime cô lập; không cần sửa code hoặc payload giữa các lần chạy. Đây là demo Agent/Vehicle simulator, không phải live Guardrail/UI rehearsal.

## 1. Chuẩn bị một lần

Từ repository root:

```powershell
$env:PYTHONPATH = ".;src"
python --version
python -m pytest --version
```

Yêu cầu Python 3.11+ và `pytest`. Trước mỗi rehearsal đầy đủ, chạy gate ngắn:

```powershell
python -m pytest --import-mode=importlib `
  tests/contracts/guardrail/test_consumer_contract.py `
  tests/contracts/agent_ui/test_consumer_contract.py `
  tests/operations/test_runtime_operations.py -q
```

Nếu gate fail, không chạy tiếp và không claim demo pass.

## 2. Clean reset và preset

Harness của từng test tạo state machine/session mới, tương đương clean reset. Với app adapter thật, trước scenario gọi reset `all`:

```json
{"contract_version":"1.0.0","kind":"request","request_type":"reset","session_id":"demo","request_id":"reset-001","occurred_at":"2026-08-10T08:00:00Z","scope":"all"}
```

Chỉ bắt đầu khi response là `completed` và health có `ready=true`. Sau reset, load preset bằng operator-only `simulation_control`; adapter deployment ánh xạ request này tới `SimulationController.apply_preset`, không tới Agent/model.

Lưu ý: checkout hiện chưa có public dispatcher cho `simulation_control`. Các bước live-adapter ở đoạn này chỉ áp dụng sau khi deployment đã cung cấp và test mapping được mô tả trong Integration Guide. Nếu chưa có adapter đó, chỉ chạy harness pytest bên dưới và ghi evidence là offline Agent/Vehicle simulator.

## 3. Scenario 1 — Agent bị lừa, xe vẫn an toàn

Preset: `driving` (30 km/h). Agent-side mock router vẫn đề xuất `open_door` dù utterance nói xe đã dừng.

```powershell
python -m pytest tests/e2e/scenarios/test_scn01_agent_fooled_vehicle_safe.py -q
```

Expected evidence:

- response `blocked`, decision `BLOCK_UNSAFE`, state version khớp snapshot thật;
- public event chỉ có `proposal(AGENT)` rồi `decision(GUARDRAIL)`;
- không có execution/state change;
- gateway và actuator call count bằng 0; door vẫn closed;
- cùng utterance trên preset `parked` được allow, chứng minh decision thay đổi theo state thật chứ không theo lời khai.

## 4. Scenario 2 — Confirmation không phải permit vĩnh viễn

Scenario bắt đầu ở state cho phép tạo confirmation, sau đó operator đổi state trước khi confirm.

```powershell
python -m pytest tests/e2e/scenarios/test_scn02_confirmation_not_a_permanent_permit.py -q
```

Expected evidence:

- decision đầu là `CONFIRM` và không có executable permit;
- state đổi bởi `OPERATOR` trước confirm;
- confirm tạo proposal/decision mới trên state version mới;
- outcome mới block action; actuator call count bằng 0;
- replay confirmation cũ không tạo side effect.

Expected public sequence: `proposal → decision(CONFIRM) → state_changed(OPERATOR) → proposal mới → decision(BLOCK_UNSAFE)`. Không có execution event.

## 5. Scenario 3 — Guardrail dừng active action

Preset: `highway_hda`. HDA được allow và bắt đầu, sau đó operator làm mất điều kiện driver attention; monitor yêu cầu stop.

```powershell
python -m pytest tests/e2e/scenarios/test_scn03_guardrail_stops_active_action.py -q
```

Expected evidence:

- ban đầu có `ALLOW`, một execution start và active action start;
- operator state change kích hoạt monitor evaluation;
- stop đi qua registered stop handler, không phải Guardrail tự mutate xe;
- active action và execution kết thúc ở `stopped` với reason `MONITOR_STOP_REQUIRED`;
- không có event/action tiếp tục sau terminal stop.

Expected public sequence: `proposal → decision(ALLOW) → execution(started) → active_action(started) → state_changed(OPERATOR) → active_action(stopped) → execution(stopped)`.

## 6. Chạy cả ba không sửa code

```powershell
python -m pytest tests/e2e/scenarios -q
```

Ghi lại commit SHA, Python/pytest version, command, số test pass/fail và timestamp. Không đổi fixture để “làm pass” giữa scenarios. Nếu cần chạy lại, reset `all` và dùng cùng commit.

## 7. Disconnect/reconnect check

Để kiểm tra semantics UI riêng:

```powershell
python -m pytest tests/operations/test_runtime_operations.py -q -k "reconnect or readiness"
```

Expected: reconnect trả đúng event sau ACK cursor; đọc lại event không gọi executor/handler. UI nên deduplicate bằng `(session_id, sequence)` và ACK sau render.

## 8. Troubleshooting

| Lỗi | Kiểm tra | Xử lý an toàn |
| --- | --- | --- |
| `ModuleNotFoundError: vivi_agent` | `PYTHONPATH` | đặt `$env:PYTHONPATH = ".;src"` tại repo root |
| Model degraded | health/config/transport | kiểm tra key + injected transport; không dùng mock fallback ngầm |
| Guardrail timeout/schema error | adapter logs không chứa secret | fail closed, zero action; kiểm tra exact contract version |
| `ready=false` | `unavailable_dependencies` | khôi phục dependency rồi đọc health lại; không bỏ qua readiness |
| Reset trả `VEHICLE_RESET_FAILED` | simulator result | dừng rehearsal; không reuse permit/action/state cũ |
| UI thấy event trùng | ACK cursor/connection ID | deduplicate theo sequence; reconnect không gọi handler |
| Scenario test fail | test name và first assertion | lưu output + SHA; không chỉnh expected event tại chỗ |

## 9. Evidence ownership

- SCN tests chứng minh hành vi Agent/Vehicle simulator trong checkout này.
- `actor=GUARDRAIL` trong event là attribution của decision từ test double/contract; không tự động chứng minh Guardrail service thật đã chạy.
- `actor=OPERATOR` chứng minh state được đổi qua simulation control, không phải Agent tool.
- Contract/UI fixtures chứng minh payload parse/render được bằng consumer test, không chứng minh UI visual quality.
- Chỉ rehearsal với endpoint thật, UI thật và evidence do các team sở hữu mới được dùng để đóng external integration/release gates.
