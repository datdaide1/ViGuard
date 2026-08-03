# Kế hoạch triển khai ViVi Vehicle Agent Simulator — Agent-only

**Trạng thái:** Proposed  
**Ownership:** Team ViVi Agent  
**Giả định bắt buộc:** Guardrail và Web UI do team khác triển khai và cung cấp qua contract đã thống nhất  
**Phạm vi triển khai của tài liệu này:** ViVi Agent, tool calling, Vehicle Simulator, action execution, response composition, integration adapters và agent-side evaluation

## 1. Mục tiêu

Xây dựng ViVi Vehicle Agent Simulator có khả năng:

1. Nhận yêu cầu tiếng Việt từ UI thông qua Agent API.
2. Dùng frontier model qua OpenAI hoặc Gemini API để chọn domain tool và tham số có cấu trúc.
3. Gửi `ActionProposal` sang Guardrail để xin quyết định trên trạng thái xe hiện tại.
4. Chỉ thực thi action khi Guardrail trả `ALLOW` cùng execution permit hợp lệ, hoặc sau confirmation đã được Guardrail đánh giá lại.
5. Mô phỏng đầy đủ hành vi quan sát được của 53 intent hiện tại:
   - 47 action/UI intent có handler hoặc explicit refusal;
   - 6 query intent có responder và không gọi actuator.
6. Mô phỏng một chiếc xe có state và transition nhất quán để action, confirmation và monitor có ý nghĩa.
7. Phát typed events để UI team hiển thị chat, vehicle state, execution, active action và trace.
8. Cung cấp test/evidence chứng minh agent không thể bypass Guardrail.

## 2. Ranh giới ownership

### 2.1. Team Agent chịu trách nhiệm

- `ModelProviderAdapter` hỗ trợ OpenAI và Gemini.
- ViVi Agent Orchestrator.
- Domain Tool Registry và JSON Schema.
- Tool-to-intent mapping đủ 53 intent.
- Guardrail Client Adapter.
- Execution Permit Verifier ở Vehicle Tool Gateway.
- Vehicle State Machine và simulator runtime.
- Generic action handler framework.
- Behavior catalog cho 47 action/UI intent.
- Query responder integration cho 6 query intent.
- Confirmation/monitor integration phía Agent.
- Active Action lifecycle và stop handlers.
- Simulation Control API/presets cho UI team sử dụng.
- Grounded response composition.
- Agent/vehicle events, metrics và agent-side trace.
- Contract, integration, adversarial và E2E tests thuộc Agent.
- Demo scenarios, seed/reset và runbook phần Agent.

### 2.2. Team Guardrail chịu trách nhiệm

Các hạng mục dưới đây là **external dependency**, không phải task implementation trong plan:

- text check;
- T1/T2/T3 intent classification;
- policy loader cho `Driver_constraints.xlsx`;
- closed condition parser/evaluator;
- Constraint Engine;
- Vehicle State snapshot dùng cho policy decision;
- bảy policy outcomes;
- rule ID, policy checksum và reason metadata;
- confirmation re-evaluation;
- monitor evaluation;
- execution permit issuance hoặc authorization artifact tương đương;
- Guardrail trace và policy coverage 53/109/5.

Team Agent chỉ định nghĩa contract cần thiết, cung cấp consumer tests và mock Guardrail để phát triển độc lập.

### 2.3. Team UI chịu trách nhiệm

Các hạng mục dưới đây là **external dependency**, không phải task implementation trong plan:

- chat interface;
- Intent Explorer;
- Vehicle State/Simulation Control panels;
- confirmation dialog;
- decision, execution và active-action panels;
- trace timeline;
- vehicle visual/animation;
- coverage dashboard và error/degraded states.

Team Agent cung cấp API, typed events, sample payloads và integration tests để UI team render đúng.

### 2.4. Không nằm trong phạm vi P0

- Không thêm bảy dynamics intent vào policy catalog.
- Không sửa `Driver_constraints.xlsx`.
- Không nghiên cứu condition/outcome mới cho start, accelerate, brake hoặc stop.
- Không điều khiển xe thật, CAN bus hoặc ECU.
- Không xây ASR/TTS hoặc RAG production.
- Không mô phỏng vật lý chính xác VF8 khi không có đầy đủ thông số chính thức.
- Không cho model tự sinh tool, policy outcome, permit hoặc executable code.

## 3. Hợp đồng đầu vào bắt buộc từ các team khác

### 3.1. Guardrail contract tối thiểu

Team Agent cần Guardrail cung cấp:

```text
evaluate_text(text, session_context)
  -> intent hoặc typed classification failure

authorize_action(action_proposal)
  -> GuardrailDecision

confirm(confirmation_id)
  -> GuardrailDecision mới + permit nếu được phép

evaluate_monitor(active_action_id)
  -> continue/stop decision
```

`GuardrailDecision` tối thiểu gồm:

```json
{
  "request_id": "req-001",
  "intent": "open_door",
  "outcome": "ALLOW",
  "rule_id": "R001",
  "state_version": 12,
  "policy_checksum": "sha256:...",
  "reason_code": "POLICY_CONDITION_MATCHED",
  "relevant_state": {
    "gear": "P",
    "speed": 0
  },
  "permit": {
    "permit_id": "permit-001",
    "proposal_digest": "sha256:...",
    "expires_at": "...",
    "single_use": true
  }
}
```

Guardrail không cần trả `permit` cho block, query, unknown, confirm-pending hoặc error.

### 3.2. UI contract tối thiểu

UI gửi:

- user message;
- confirmation/cancel action;
- operator simulation command;
- preset/reset request;
- optional correlation/session ID.

Agent trả hoặc phát event:

- agent turn status;
- model/tool proposal;
- Guardrail decision summary;
- execution status;
- vehicle state change;
- active action status;
- confirmation state;
- grounded response;
- typed error/degraded status;
- agent-side trace metadata.

## 4. Nguyên tắc triển khai

1. **Model đề xuất, Guardrail quyết định, Vehicle Tool Gateway thực thi.**
2. Team Agent không duplicate policy condition vào handler.
3. Handler chỉ nhận authorized command; không nhận raw text.
4. `ALLOW` không đồng nghĩa với `SUCCEEDED`.
5. Agent chỉ báo thành công sau `ExecutionResult.SUCCEEDED`.
6. Missing/invalid Guardrail response luôn fail closed.
7. UI không phải execution boundary; API request từ UI vẫn phải qua Agent/Guardrail flow.
8. Operator simulation commands phải có actor/provenance riêng và không xuất hiện như Agent action.
9. Mọi behavior đủ đơn giản để chạy offline và lặp lại được.
10. Sáu hero actions được polish sâu; các intent còn lại dùng generic behavior nhưng vẫn quan sát được.

## 5. Definition of Done chung cho task

Một task chỉ hoàn thành khi:

- interface và implementation được review;
- unit/contract/integration tests liên quan đạt;
- happy path, error path và negative path đều được xử lý;
- typed events và error codes đã định nghĩa;
- không tạo đường gọi handler bỏ qua Guardrail;
- tài liệu contract/sample payload được cập nhật;
- không còn placeholder giả lập success trong đường demo.

## 6. Sprint 1 — Agent foundation và vertical slice

### Mục tiêu sprint

Có một vertical slice `open_door` hoàn chỉnh chạy với Guardrail mock/contract adapter: user text → provider model được chọn → ActionProposal → Guardrail authorization → permit verification → vehicle handler → grounded response và typed events cho UI.

### Điều kiện hoàn thành sprint

- Agent API và ít nhất một model provider có API key hoạt động; auto-selection được kiểm thử với cả hai provider adapters.
- Guardrail/UI contracts được khóa bằng schema và consumer tests.
- Vehicle State Machine có state tối thiểu cho `open_door`.
- Allow path thực thi đúng một lần.
- Block/error path có handler call count bằng 0.
- Team Agent có thể phát triển độc lập bằng Guardrail/UI test harness.

### CON-01 — Khóa Guardrail–Agent contract

**Ưu tiên:** P0  
**Phụ thuộc:** Không

**Mô tả:** Định nghĩa exact request/response/event contract giữa Agent và Guardrail. Contract phải phân biệt intent classification, action authorization, confirmation và monitor evaluation; không gộp policy outcome với execution status.

**Công việc chi tiết:**

- Định nghĩa schema cho `ActionProposal`.
- Định nghĩa schema cho `GuardrailDecision` và typed error.
- Chốt bảy outcome và quy tắc outcome nào có permit.
- Định nghĩa proposal digest, permit fields, expiry và single-use semantics.
- Định nghĩa confirmation và monitor request/response.
- Tạo version field cho contract.
- Tạo sample payload cho allow, ba block outcomes, confirm, answer, unknown và error.
- Tạo consumer contract tests chạy được với mock server.

**Đầu ra:** Guardrail–Agent API schema, examples và consumer tests.

**Acceptance criteria:**

- Agent reject response thiếu `intent/outcome/rule_id/state_version` khi các field đó bắt buộc.
- Block/error/confirm-pending response không thể chứa usable permit.
- Contract version mismatch tạo typed integration error và zero execution.

### CON-02 — Khóa Agent–UI contract

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01

**Mô tả:** Định nghĩa API và event model để UI team hiển thị đúng trạng thái Agent/Vehicle mà không cần biết implementation nội bộ.

**Công việc chi tiết:**

- Request schema cho message, confirm, cancel, simulation control và reset.
- Response schema cho completed, blocked, needs-confirmation, failed và degraded.
- Event schema cho proposal, decision, execution, state change và active action.
- Correlation fields `session_id`, `turn_id`, `proposal_id`, `request_id`, `execution_id`.
- Field visibility/redaction; không gửi hidden reasoning/system prompt.
- Sample fixture cho sáu hero actions và ba demo scenarios.
- Consumer contract tests cho UI mock client.

**Đầu ra:** Agent API/event contract và UI fixtures.

**Acceptance criteria:**

- UI có thể render toàn bộ lifecycle chỉ từ public payloads.
- Không public event nào chứa secret hoặc hidden reasoning.
- Agent event ordering được định nghĩa rõ và test được.

### CAT-01 — Xây runtime intent/behavior manifest

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01

**Mô tả:** Tạo manifest Agent-side cho exact 53 intent hiện tại, loại intent, domain tool, behavior category, query/action flag, parameter requirements và monitor capability. Manifest không chứa condition hoặc outcome policy.

**Công việc chi tiết:**

- Trích exact set 53 intent từ artifact đã duyệt.
- Phân loại 47 action/UI và 6 query.
- Đánh dấu `deactivate_esc` là explicit refusal behavior.
- Đánh dấu các intent có monitor rule dựa trên metadata do Guardrail cung cấp.
- Định nghĩa sample utterances chỉ phục vụ Agent evaluation/UI fixtures.
- Tính manifest checksum và validate khi startup.

**Đầu ra:** Intent/behavior manifest và coverage validator.

**Acceptance criteria:**

- Manifest có đúng 53 intent duy nhất.
- Không chứa dynamics intent ngoài catalog.
- Manifest thiếu hoặc thừa intent làm Agent readiness fail.

### TOOL-01 — Định nghĩa Domain Tool Registry

**Ưu tiên:** P0  
**Phụ thuộc:** CAT-01

**Mô tả:** Định nghĩa tool set nhỏ, có schema đóng để model từ OpenAI hoặc Gemini lựa chọn. Agent không expose 47 hàm rời hoặc arbitrary tool names.

**Công việc chi tiết:**

- Định nghĩa các tool domain: access, light, cabin, drive mode, transmission, driver assistance, special mode, UI, state query và feature explanation.
- JSON Schema cho action, target, value và enum.
- Chặn additional properties.
- Định nghĩa structured clarification khi thiếu parameter.
- Tạo tool registry checksum/version.
- Unit tests cho valid/invalid arguments.

**Đầu ra:** Domain Tool Registry và JSON Schemas.

**Acceptance criteria:**

- Model chỉ nhìn thấy registered tools.
- Invalid tool/argument bị chặn trước Guardrail call.
- Tool arguments không chấp nhận state, outcome, rule hoặc permit do model cung cấp.

### MAP-01 — Xây mapping nền tảng cho vertical slice

**Ưu tiên:** P0  
**Phụ thuộc:** TOOL-01

**Mô tả:** Xây deterministic mapper từ tool call sang canonical intent; sprint này khóa đường `control_access(open, driver_door) → open_door` và kiến trúc mở rộng cho toàn catalog.

**Công việc chi tiết:**

- Canonicalize tool arguments.
- Map exact combination về intent.
- Tính proposal digest trên canonical payload.
- Chặn ambiguous/unsupported combination.
- Ghi source tool và canonical intent vào event.
- Thiết kế startup mapping validator.

**Đầu ra:** Tool Mapper và `open_door` mapping.

**Acceptance criteria:**

- Valid call map đúng một intent.
- Unsupported target/action không tự fallback sang intent gần nhất.
- Cùng canonical proposal luôn có cùng digest.

### MOD-01 — Xây ModelProviderAdapter cho OpenAI và Gemini

**Ưu tiên:** P0  
**Phụ thuộc:** TOOL-01

**Mô tả:** Tạo abstraction provider-neutral và hai adapter API: OpenAI dùng mặc định `gpt-5-mini`, Gemini dùng mặc định `gemini-3.6-flash`. Cả hai phục vụ tool selection và response verbalization có kiểm soát, cùng trả một internal contract. Model không được kết nối Guardrail/Vehicle handlers trực tiếp.

**Công việc chi tiết:**

- Định nghĩa internal interfaces `propose_tool()` và `compose_response()`.
- OpenAI adapter dùng native strict function calling.
- Gemini adapter dùng native function calling/structured output.
- Cấu hình `AGENT_MODEL_PROVIDER=auto|openai|gemini`.
- Cấu hình `AGENT_MODEL_PROVIDER_PRIORITY`, mặc định `openai,gemini`.
- Đọc `OPENAI_API_KEY` và `GEMINI_API_KEY` chỉ ở backend.
- Cho phép đổi exact model ID qua cấu hình, không hardcode trong business logic.
- Ở `auto`, chọn provider đầu tiên có key theo priority.
- Không có key thì Agent readiness fail rõ nguyên nhân.
- Không gọi race hai provider cho cùng turn.
- Chỉ failover tối đa một lần nếu provider đầu chưa tạo valid ActionProposal.
- Sau valid proposal, Guardrail authorization hoặc execution, pin turn vào provider ban đầu.
- Bounded context, output, timeout và maximum one tool call.
- Normalize provider-specific response về shared `ModelActionProposal`.
- Health/readiness, provider/model metadata và typed API errors.
- Deterministic error response khi toàn bộ providers unavailable.
- Không lưu hidden reasoning/provider thought payload.

**Đầu ra:** ModelProviderAdapter, OpenAI adapter, Gemini adapter và provider-selection module.

**Acceptance criteria:**

- Adapter chỉ output tool proposal, clarification hoặc response draft.
- Timeout/malformed output tạo zero Guardrail-authorized action.
- Cùng internal contract được dùng cho cả OpenAI và Gemini.
- `auto` chọn đúng provider dựa trên key và priority.
- Không có key làm readiness fail; không silently dùng mock model.
- Provider, model ID, config checksum và latency xuất hiện trong event metadata.
- Failover không được xảy ra sau khi đã có valid proposal hoặc side-effect lifecycle bắt đầu.

### ORC-01 — Xây ViVi Agent Orchestrator nền tảng

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01, CON-02, MAP-01, MOD-01

**Mô tả:** Điều phối một Agent turn qua model, Guardrail client, execution và response. Orchestrator không mint permit và không import handler.

**Công việc chi tiết:**

- Agent turn state machine.
- Correlation IDs và cancellation.
- Giới hạn một state-changing proposal mỗi turn.
- Không parallel state-changing calls.
- Clarification state.
- Typed handling cho block, confirm, query, error và model failure.
- Grounded response input chỉ từ typed facts.

**Đầu ra:** Agent Orchestrator và message endpoint.

**Acceptance criteria:**

- Agent không báo success trước execution result.
- Guardrail client failure làm turn fail closed.
- Orchestrator không có direct reference tới Action Handler Registry.

### GRD-ADP-01 — Xây Guardrail Client Adapter và mock server

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01

**Mô tả:** Tạo adapter duy nhất để gọi Guardrail thật và một contract-compatible mock để team Agent phát triển độc lập. Mock chỉ mô phỏng contract, không được dùng làm bằng chứng policy correctness.

**Công việc chi tiết:**

- Client timeout/retry policy cho read-only request.
- Không tự retry state-changing authorization khi trạng thái response không rõ.
- Validate response schema/version.
- Mock fixtures allow/block/confirm/query/error.
- Config switch mock/real rõ ràng.
- Event metadata ghi provider `MOCK` hoặc `REAL`.

**Đầu ra:** Guardrail Client Adapter và mock server.

**Acceptance criteria:**

- Mock và real adapter dùng cùng public interface.
- Demo/release mode hiển thị rõ nếu đang dùng mock Guardrail.
- Invalid Guardrail response không thể tới Vehicle Tool Gateway.

### VEH-01 — Định nghĩa Vehicle State Model và invariants

**Ưu tiên:** P0  
**Phụ thuộc:** CAT-01, CON-01

**Mô tả:** Định nghĩa state model mà Vehicle Simulator sở hữu và expose snapshot cho Guardrail/UI theo contract. Chỉ dùng field cần cho behavior/Guardrail integration; không tự phát minh ngưỡng VF8.

**Công việc chi tiết:**

- Nhóm state theo power, motion, gear, access, lights, cabin, ADAS, modes, environment, UI và active actions.
- Type, enum, nullability và source/provenance.
- Invariants như `gear=P → speed=0`, cửa mở không thể locked, power off dừng ADAS action.
- Phân biệt source fields và derived fields.
- Default state và preset schema.
- Contract export snapshot/version cho Guardrail.

**Đầu ra:** Vehicle State Model và invariant specification.

**Acceptance criteria:**

- State model cung cấp mọi field Guardrail contract yêu cầu.
- Không field numeric nào được claim là thông số VF8 nếu thiếu nguồn.
- Invalid state combination bị từ chối hoặc normalized theo rule được tài liệu hóa.

### VEH-02 — Xây Vehicle State Machine và event store

**Ưu tiên:** P0  
**Phụ thuộc:** VEH-01

**Mô tả:** Xây state machine in-memory với atomic transition, versioning và events. Cả Agent action và Operator action đều dùng cùng transition API nhưng actor metadata khác nhau.

**Công việc chi tiết:**

- Immutable snapshot.
- Atomic transition và rollback.
- Monotonic state version.
- Optimistic expected-version support.
- `state_changed` event.
- Reset/preset lifecycle.
- Actor/correlation metadata.

**Đầu ra:** Vehicle State Machine và Vehicle Event Store.

**Acceptance criteria:**

- Failed transition không thay đổi state/version.
- Successful transition tăng version đúng một lần.
- Guardrail/UI có thể lấy snapshot/event theo contract.

### EXEC-01 — Xây Vehicle Tool Gateway và permit verifier

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01, VEH-02

**Mô tả:** Tạo execution boundary duy nhất của team Agent. Gateway chỉ nhận canonical proposal cùng permit Guardrail và từ chối mọi đường không hợp lệ.

**Công việc chi tiết:**

- Validate permit schema/version.
- Verify proposal digest, intent, expiry và single-use status.
- Permit store lifecycle.
- Chặn substitution/replay.
- Execution status namespace riêng.
- Actuator spy và boundary tests.

**Đầu ra:** Vehicle Tool Gateway và Permit Verifier.

**Acceptance criteria:**

- Handler chỉ được gọi từ gateway.
- Block/confirm/error/invalid permit có handler call count bằng 0.
- Replayed/substituted permit bị từ chối.

### EXEC-02 — Xây handler `open_door`

**Ưu tiên:** P0  
**Phụ thuộc:** EXEC-01, VEH-02

**Mô tả:** Xây handler đầu tiên để chứng minh execution semantics, atomic state mutation và typed events.

**Công việc chi tiết:**

- Authorized command schema.
- Door target validation.
- Transition locked/closed → unlocked/open theo behavior đã chốt.
- Running/succeeded/failed events.
- State-before/state-after versions.
- Idempotency/error semantics.

**Đầu ra:** `open_door` handler và tests.

**Acceptance criteria:**

- Permit hợp lệ thực thi đúng một lần.
- Invalid target không tạo partial mutation.
- Execution failure không được phản hồi là success.

### EVT-01 — Xây Agent/Vehicle typed event pipeline

**Ưu tiên:** P0  
**Phụ thuộc:** CON-02, ORC-01, VEH-02, EXEC-01

**Mô tả:** Phát typed events cho UI/observability mà không duplicate Guardrail internal trace.

**Công việc chi tiết:**

- Turn/proposal/decision/execution/state/active-action/response events.
- Ordering và correlation.
- Append-only agent-side event store.
- Redaction.
- Polling/streaming adapter theo UI contract.
- Event fixtures và replay test.

**Đầu ra:** Agent Event Pipeline và event endpoint/stream.

**Acceptance criteria:**

- UI mock tái dựng được complete vertical slice.
- Block path có explicit no-execution evidence.
- Event replay không tái thực thi action.

### E2E-01 — Khóa vertical slice `open_door`

**Ưu tiên:** P0  
**Phụ thuộc:** ORC-01, GRD-ADP-01, EXEC-02, EVT-01

**Mô tả:** Chạy allow, block, malformed Guardrail response và permit replay qua public Agent API.

**Công việc chi tiết:**

- User message → model proposal → Guardrail mock → execution.
- Moving-state block fixture.
- Invalid/expired/replayed permit fixtures.
- UI mock consumer verification.
- State reset deterministic.
- Actuator-spy assertion.

**Đầu ra:** Vertical-slice E2E suite và demo fixture.

**Acceptance criteria:**

- Allow path thay đổi vehicle state đúng một lần.
- Tất cả non-allow/error paths gọi handler zero lần.
- Event sequence đúng Agent–UI contract.

## 7. Sprint 2 — Bao phủ 53 intent và lifecycle hoàn chỉnh

### Mục tiêu sprint

Mở rộng Agent/Vehicle runtime từ `open_door` lên toàn bộ catalog, hoàn thiện queries, confirmation, active actions, monitor integration và operator simulation controls.

### Điều kiện hoàn thành sprint

- Tool mapping đạt 53/53.
- Behavior coverage đạt 47/47.
- Query coverage đạt 6/6.
- Năm monitor intents có active-action/stop path phía Agent.
- Confirmation sử dụng Guardrail re-evaluation và chống replay.
- Simulation controls tạo được các state cần cho demo nhưng không expose như Agent tools.

### MAP-02 — Hoàn thiện tool-to-intent mapping 53/53

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-01, CAT-01

**Mô tả:** Mở rộng Tool Mapper để mọi intent hiện tại reachable qua ít nhất một valid domain tool call và không mapping nào ambiguous.

**Công việc chi tiết:**

- Mapping access, lights, cabin, modes, gear, ADAS, UI và queries.
- Parameter normalization và enums.
- Exact source intent casing trong proposal/trace.
- Unsupported combination rejection.
- Startup mapping coverage validation.
- Mapping report theo missing/duplicate/ambiguous ID.

**Đầu ra:** Full Tool Mapper và coverage report.

**Acceptance criteria:**

- 53/53 intent reachable.
- Mỗi valid combination map đúng một intent.
- Không dynamics intent ngoài catalog xuất hiện trong model tool registry.

### EXEC-03 — Xây generic handler framework

**Ưu tiên:** P0  
**Phụ thuộc:** EXEC-01, VEH-02

**Mô tả:** Xây tám loại handler dùng chung để tránh 47 class rời và giữ behavior data-driven.

**Công việc chi tiết:**

- Toggle handler.
- Enum setter.
- Access actuator.
- Position actuator.
- Timed transition.
- One-shot event.
- Active action handler.
- Compound action handler.
- Typed behavior config validation.

**Đầu ra:** Generic Handler Library.

**Acceptance criteria:**

- Handler chỉ nhận authorized command.
- Invalid behavior config làm readiness fail.
- Atomic mutation và typed ExecutionResult thống nhất.

### BEH-01 — Khai báo behavior catalog đủ 47 action/UI intent

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-02, EXEC-03

**Mô tả:** Ánh xạ 47 action/UI intent sang handler, parameters, state mutation/event, active-action flag và response facts. Catalog không chứa policy condition/outcome.

**Công việc chi tiết:**

- Behavior cho access, lights, cabin, modes, transmission, ADAS và UI.
- `deactivate_esc` là explicit refusal, không action handler.
- State effects và visual event metadata.
- Active-action metadata cho monitored intents.
- Startup coverage validator.
- Generated basic behavior tests.

**Đầu ra:** Behavior Catalog và coverage report 47/47.

**Acceptance criteria:**

- 47/47 action/UI intent có behavior/refusal.
- Không query intent nào có actuator behavior.
- Mọi executable behavior tạo observable state/event.

### QRY-01 — Xây Query Responder đủ 6/6

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-02, VEH-02, CON-01

**Mô tả:** Trả lời năm state query và một knowledge query dựa trên typed data do Guardrail/state/knowledge provider cung cấp. Không dùng kiến thức tự do của model làm source of truth.

**Công việc chi tiết:**

- Speed, battery, gear, door lock và AVH responders.
- `explain_feature` knowledge-provider adapter.
- Grounded facts/source metadata.
- `ANSWER/UNKNOWN` handling.
- Vietnamese deterministic templates.
- Zero-actuator assertions.

**Đầu ra:** Query Responder Registry.

**Acceptance criteria:**

- Coverage 6/6.
- Missing data trả unknown, không đoán.
- Query path gọi handler zero lần.

### RSP-01 — Xây Grounded Response Composer

**Ưu tiên:** P0  
**Phụ thuộc:** ORC-01, QRY-01, BEH-01

**Mô tả:** Chuyển typed Guardrail/execution facts thành response plan và câu trả lời tiếng Việt. Provider model đang được chọn có thể verbalize nhưng deterministic templates luôn là fallback.

**Công việc chi tiết:**

- Response plan schema.
- Templates cho allow, block unsafe, block unavailable, confirm, not voice actionable, answer, unknown và errors.
- Relevant-state formatting.
- Approved recovery suggestions.
- Execution failure/uncertain messages.
- Persona constraints và length limits.

**Đầu ra:** Response Composer và Vietnamese catalog.

**Acceptance criteria:**

- Không invent state, policy reason hoặc execution success.
- Mọi public outcome/error có deterministic fallback.
- `ALLOW` nhưng execution failed không tạo success message.

### CNF-01 — Tích hợp confirmation lifecycle

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01, CON-02, ORC-01, EXEC-01

**Mô tả:** Agent lưu pending proposal/context và điều phối confirm/cancel qua Guardrail. Agent không giữ live permit trong lúc chờ confirmation.

**Công việc chi tiết:**

- Pending Confirmation Agent state.
- Confirm/cancel endpoints cho UI.
- Gọi Guardrail confirmation re-evaluation.
- Nhận permit mới chỉ sau allow.
- Expiry/replay/consumed handling.
- Confirmation events và grounded response.

**Đầu ra:** Confirmation integration module.

**Acceptance criteria:**

- Chưa confirm gọi handler zero lần.
- Agent không tái sử dụng decision/permit cũ.
- Confirm replay/expiry bị từ chối và ghi event.

### ACTV-01 — Xây Active Action Registry

**Ưu tiên:** P0  
**Phụ thuộc:** BEH-01, VEH-02

**Mô tả:** Quản lý lifecycle của action kéo dài như HDA, AAC, autopark, camp/pet mode theo behavior metadata.

**Công việc chi tiết:**

- Active action entity/status.
- Start/continue/stop/fail transitions.
- Link tới proposal/decision/execution/state version.
- Registry query endpoint cho UI.
- Reset/restart cleanup.
- Stop handler registry.

**Đầu ra:** Active Action Registry.

**Acceptance criteria:**

- Chỉ monitored/active behavior tạo ActiveAction.
- Restart/reset không phục hồi action như đang chạy.
- Stop/fail luôn tạo typed event.

### MON-ADP-01 — Tích hợp Guardrail Monitor

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01, GRD-ADP-01, ACTV-01, EXEC-01

**Mô tả:** Phía Agent subscribe state changes/manual tick, gọi Guardrail monitor evaluation và dừng active action qua Vehicle Tool Gateway khi Guardrail trả stop/block/error.

**Công việc chi tiết:**

- State-change subscription.
- Monitor request adapter.
- Continue/stop/error routing.
- Stop authorization contract với Guardrail.
- Fail-safe stop khi monitor response invalid/timeout theo contract đã duyệt.
- Monitor events và metrics.

**Đầu ra:** Monitor Integration Adapter.

**Acceptance criteria:**

- Năm monitor intents có integration path.
- Stop đi qua registered gateway/handler, không mutate state trực tiếp.
- Monitor error không để action tiếp tục im lặng.

### SIM-01 — Xây Simulation Control API và presets

**Ưu tiên:** P0  
**Phụ thuộc:** VEH-02, MON-ADP-01, CON-02

**Mô tả:** Cung cấp operator controls để UI team tạo state chạy/dừng/môi trường cho demo. Đây không phải Agent tool và không đi qua model.

**Công việc chi tiết:**

- Controls cho power, gear, speed state, rain, light, obstacle và driver attention.
- Presets Parked, Driving, Highway/HDA, Charging và Camp.
- Actor `OPERATOR` và distinct event type.
- Invariant validation.
- State-change/monitor triggering.
- Reset endpoint và deterministic seeds.

**Đầu ra:** Simulation Control API và preset catalog.

**Acceptance criteria:**

- Model không nhìn thấy operator controls trong tool registry.
- Operator event không bị ghi thành Agent execution.
- Presets tạo state lặp lại và kích hoạt monitor đúng.

### COV-01 — Xây Agent capability coverage gate

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-02, BEH-01, QRY-01, ACTV-01

**Mô tả:** Tạo machine-checkable release gate riêng cho Agent; không duplicate policy correctness tests của team Guardrail.

**Công việc chi tiết:**

- Tool mapping 53/53.
- Behavior/refusal 47/47.
- Query responder 6/6.
- Active/monitor integration coverage.
- Tool schema/intent/behavior consistency.
- Missing/duplicate/ambiguous report.
- Agent readiness dependency.

**Đầu ra:** Agent Coverage Report và CI gate.

**Acceptance criteria:**

- Thiếu bất kỳ intent mapping/behavior/responder nào làm readiness fail.
- Report chỉ ra exact ID thiếu.
- Không claim 109-rule correctness; chỉ consume Guardrail policy status.

### INT-01 — Chạy integration với Guardrail thật

**Ưu tiên:** P0  
**Phụ thuộc:** GRD-ADP-01, COV-01, CNF-01, MON-ADP-01

**Mô tả:** Thay mock bằng Guardrail implementation của team khác và chạy contract/integration suite. Mọi mismatch phải được xử lý tại adapter hoặc thống nhất contract, không vá bằng business logic trong handler.

**Công việc chi tiết:**

- Contract version handshake.
- Allow/block/query/confirm/monitor scenarios.
- Permit/digest compatibility.
- State snapshot/version compatibility.
- Error/timeout/degraded scenarios.
- Joint trace correlation.

**Đầu ra:** Guardrail Integration Report.

**Acceptance criteria:**

- Agent chạy được mọi public outcome của Guardrail.
- Block/error path gọi handler zero lần.
- Mock và real Guardrail cùng pass consumer tests.

### INT-02 — Chạy integration với UI thật

**Ưu tiên:** P0  
**Phụ thuộc:** EVT-01, SIM-01, CON-02

**Mô tả:** Kết nối API/events với UI team và xác nhận UI hiển thị đúng Agent lifecycle. Team Agent không implement UI nhưng chịu trách nhiệm fix payload/event semantics thuộc ownership của mình.

**Công việc chi tiết:**

- Message/confirmation/simulation API integration.
- Event ordering/reconnect behavior.
- Vehicle state and active action payloads.
- Error/degraded payloads.
- Six hero fixtures.
- Joint integration tests.

**Đầu ra:** UI Integration Report và verified fixtures.

**Acceptance criteria:**

- UI chạy được Agent flow không cần private fields.
- UI refresh/reconnect không gây action replay.
- Payload mismatch được phát hiện bằng contract test.

## 8. Sprint 3 — Hero behavior, evaluation và demo readiness

### Mục tiêu sprint

Hoàn thiện sáu hero actions, ba scenario chính, agent evaluation, adversarial tests, performance/stability và release package để UI/Guardrail teams ghép thành product demo.

### Điều kiện hoàn thành sprint

- Sáu hero behaviors có đầy đủ Agent/Vehicle lifecycle.
- Ba scenario chạy lặp lại với Guardrail thật và UI thật.
- Agent coverage đạt 53/47/6.
- Zero unauthorized/block-path handler call.
- Demo reset/degraded mode và runbook hoàn chỉnh.

### HERO-01 — Hoàn thiện `open_door` behavior

**Ưu tiên:** P0  
**Phụ thuộc:** INT-01, INT-02

**Mô tả:** Nâng `open_door` thành reference behavior cho state-aware action, fake-state attack và allow/block contrast.

**Công việc chi tiết:**

- Complete behavior facts/events.
- Relevant state và recovery metadata.
- Allow/block fixtures.
- Fake-state utterance fixture.
- Deterministic reset.
- E2E với Guardrail/UI thật.

**Đầu ra:** Reference `open_door` hero behavior.

**Acceptance criteria:**

- Same intent cho behavior khác đúng decision từ Guardrail.
- Agent không tin state trong model/user text.
- Block path có zero permit consumption/handler call.

### HERO-02 — Hoàn thiện HDA và AAC active behaviors

**Ưu tiên:** P0  
**Phụ thuộc:** ACTV-01, MON-ADP-01, INT-01

**Mô tả:** Hoàn thiện start/active/continue/stop lifecycle cho `activate_hda` và `activate_aac`.

**Công việc chi tiết:**

- ActiveAction creation.
- Progress/status events.
- HDA monitor-stop handling.
- AAC Stop&Go behavior không tự suy luận policy.
- Stop/fail grounded responses.
- UI fixtures và E2E.

**Đầu ra:** HDA/AAC hero behaviors.

**Acceptance criteria:**

- HDA dừng đúng khi Guardrail monitor yêu cầu.
- Agent không tự đặt monitor threshold.
- UI nhận đủ status để phân biệt policy và execution lifecycle.

### HERO-03 — Hoàn thiện Autopark và Camp mode behaviors

**Ưu tiên:** P0  
**Phụ thuộc:** ACTV-01, MON-ADP-01, SIM-01

**Mô tả:** Hoàn thiện action kéo dài/compound state cho `activate_autopark` và `activate_campmode`.

**Công việc chi tiết:**

- Start/progress/stop/fail events.
- Compound state transitions.
- Presets đủ/thiếu điều kiện.
- Monitor stop integration.
- Recovery facts và reset behavior.

**Đầu ra:** Autopark/Camp mode hero behaviors.

**Acceptance criteria:**

- Block không tạo progress giả.
- Stop/fail cleanup active action.
- Reset không giữ compound state không hợp lệ.

### HERO-04 — Hoàn thiện confirmation behavior

**Ưu tiên:** P0  
**Phụ thuộc:** CNF-01, INT-01, INT-02

**Mô tả:** Chọn `open_window` hoặc `open_sunroof` để trình diễn pending confirmation, fresh-state re-evaluation, expiry và replay rejection.

**Công việc chi tiết:**

- Pending event payload.
- Confirm/cancel/expiry handling.
- State-change-before-confirm fixture.
- Permit issuance/consumption sau re-evaluation.
- Replay negative test.

**Đầu ra:** Confirmation hero behavior.

**Acceptance criteria:**

- Chưa confirm không gọi handler.
- Stale decision không được dùng.
- Replay gọi handler zero lần.

### SCN-01 — Scenario “Agent bị lừa nhưng xe vẫn an toàn”

**Ưu tiên:** P0  
**Phụ thuộc:** HERO-01

**Mô tả:** Đóng gói scenario xe đang chạy, user/model text chứa fake state và Agent vẫn phải tuân thủ Guardrail result.

**Đầu ra:** Preset, utterance, expected events và E2E.

**Acceptance criteria:**

- Decision dùng Guardrail state version.
- Không execution permit hợp lệ được tiêu thụ.
- Handler call count bằng 0.

### SCN-02 — Scenario “Confirmation không phải giấy phép vĩnh viễn”

**Ưu tiên:** P0  
**Phụ thuộc:** HERO-04

**Mô tả:** Đóng gói scenario state an toàn lúc tạo confirmation nhưng thay đổi trước confirm.

**Đầu ra:** Preset sequence, expected events và E2E.

**Acceptance criteria:**

- Agent gọi Guardrail re-evaluation.
- Permit/decision cũ không được tái sử dụng.
- Action bị block khi state mới không phù hợp.

### SCN-03 — Scenario “Guardrail bảo vệ khi action đang chạy”

**Ưu tiên:** P0  
**Phụ thuộc:** HERO-02, SIM-01

**Mô tả:** Đóng gói HDA active action bị monitor dừng sau operator state change.

**Đầu ra:** HDA preset sequence, expected events và E2E.

**Acceptance criteria:**

- Operator action có provenance riêng.
- State change trigger Guardrail monitor call.
- Agent dừng action qua gateway và phát stop response/event.

### EVAL-01 — Xây Vietnamese tool-selection evaluation set

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-02, MOD-01

**Mô tả:** Đánh giá `gpt-5-mini` và `gemini-3.6-flash` trên cùng bộ câu tiếng Việt về khả năng chọn domain tool và arguments; không đánh giá lại T1/T2/T3 của team Guardrail.

**Công việc chi tiết:**

- Câu rõ ràng/paraphrase cho 53 intents.
- Ambiguous parameter/target.
- Multi-action, negation, conditional và unknown capability.
- Prompt injection/tool hijacking.
- Expected tool, arguments, clarification/reject.
- Held-out split và so sánh OpenAI/Gemini trên cùng dataset/config logic.
- Ghi tỷ lệ lỗi API, latency và malformed tool calls theo provider.

**Đầu ra:** Dataset và Agent Model Evaluation Report.

**Acceptance criteria:**

- Report có tool accuracy, argument exact match, clarification và invalid-call rate.
- Không trộn Guardrail classifier accuracy vào Agent metric.
- Model được freeze dựa trên kết quả thực đo.

### EVAL-02 — Xây adversarial execution-boundary suite

**Ưu tiên:** P0  
**Phụ thuộc:** EXEC-01, ORC-01, INT-01

**Mô tả:** Kiểm thử các cách model/client có thể cố bypass Guardrail hoặc lạm dụng permit.

**Công việc chi tiết:**

- Unknown tool và extra arguments.
- Fake outcome/permit/state.
- Permit substitution/replay/expiry.
- Direct handler import/call attempt.
- Invalid Guardrail response.
- Confirmation replay.
- Execution uncertain và model-fabricated success.

**Đầu ra:** Agent Safety Test Report.

**Acceptance criteria:**

- Unauthorized execution count bằng 0.
- Block/error/query paths gọi handler zero lần.
- Agent không report success nếu thiếu `ExecutionResult.SUCCEEDED`.

### PERF-01 — Benchmark Agent/Vehicle latency và stability

**Ưu tiên:** P0  
**Phụ thuộc:** INT-01, INT-02, EVAL-01

**Mô tả:** Đo riêng phần Agent/Vehicle và end-to-end integration trên máy demo; không nhận metric Guardrail nội bộ làm metric của team Agent.

**Công việc chi tiết:**

- Model warm-up và tool selection latency.
- Guardrail round-trip từ phía Agent.
- Permit verification và handler latency.
- End-to-end Agent turn latency.
- p50/p95/p99/max.
- Repeated scenarios, memory growth và timeout behavior.

**Đầu ra:** Agent Performance/Stability Report.

**Acceptance criteria:**

- Report ghi provider, exact model ID, network environment, sample size và warm-up.
- Không claim số chưa đo.
- Timeout không gây side effect hoặc treo turn vô hạn.

### OPS-01 — Xây Agent/Vehicle reset và degraded mode

**Ưu tiên:** P0  
**Phụ thuộc:** SIM-01, ACTV-01, ORC-01

**Mô tả:** Bảo đảm Agent/Vehicle runtime reset sạch, phát hiện Guardrail/UI/model unavailable và không giả success.

**Công việc chi tiết:**

- Clear turns/proposals/permits/confirmations/active actions.
- Reset Vehicle State và presets.
- Model unavailable fallback.
- Guardrail unavailable fail-closed response.
- UI disconnect/reconnect event semantics.
- Health/readiness dependency status.

**Đầu ra:** Reset/degraded-mode APIs và tests.

**Acceptance criteria:**

- Reset không giữ usable permit hoặc active action.
- Guardrail unavailable thực thi zero action.
- UI reconnect không replay side effect.

### DOC-01 — Viết Agent integration guide và demo runbook

**Ưu tiên:** P0  
**Phụ thuộc:** SCN-01, SCN-02, SCN-03, OPS-01

**Mô tả:** Tài liệu hóa cách Guardrail/UI teams tích hợp Agent và cách chạy ba scenario từ phía Agent/Vehicle.

**Công việc chi tiết:**

- Startup/config/model prerequisites.
- Guardrail/UI contracts và sample payloads.
- Mock versus real integration.
- Reset/preset/scenario steps.
- Expected Agent/Vehicle events.
- Troubleshooting và degraded modes.
- Claim boundary.

**Đầu ra:** Agent Integration Guide và Demo Runbook.

**Acceptance criteria:**

- Thành viên team khác chạy được Agent bằng contract docs.
- Runbook không yêu cầu sửa code giữa scenarios.
- Phân biệt rõ Agent evidence với Guardrail/UI evidence.

### REL-01 — Chạy Agent-only release gate

**Ưu tiên:** P0  
**Phụ thuộc:** Tất cả task P0

**Mô tả:** Đóng băng Agent/Vehicle build khi toàn bộ coverage, safety và integration gates đạt. Team Agent không sign off correctness nội dung policy hoặc UI visual quality ngoài contract.

**Công việc chi tiết:**

- Unit/contract/integration/E2E tests.
- Agent coverage 53/47/6.
- Guardrail/UI real integration tests.
- Adversarial suite.
- Performance/stability benchmark.
- Ba scenario rehearsal sau clean reset.
- Known limitations và release evidence.

**Đầu ra:** Agent Release Report và frozen demo build.

**Acceptance criteria:**

- Mapping 53/53.
- Behavior/refusal 47/47.
- Query responder 6/6.
- Năm monitor integration paths.
- Zero unauthorized/block-path handler call.
- Ba scenarios pass với Guardrail/UI implementations thật.
- Agent không claim policy/UI tasks thuộc ownership của mình đã hoàn thành thay team khác.

## 9. Backlog P1/P2 có thể cắt

| ID | Mức | Hạng mục | Điều kiện bắt đầu |
|---|---|---|---|
| P1-STREAM | P1 | Streaming token/progress nâng cao | P0 event ordering đã ổn định |
| P1-WORKFLOW | P1 | Compound predefined workflows | Single-action safety gates đã đạt |
| P1-PERSONA | P1 | Persona verbalization nâng cao | Deterministic grounded responses hoàn chỉnh |
| P1-CACHE | P1 | Model/session optimization | Có benchmark chứng minh bottleneck |
| P2-DYN-RESEARCH | P2 | Nghiên cứu start/accelerate/brake/stop intents | Có variant VF8, nguồn chính thức và safety owner |
| P2-DYN-POLICY | P2 | Cùng Guardrail team thêm dynamics rules | Research và outcomes được duyệt |
| P2-PHYSICS | P2 | Physics-based vehicle dynamics | Có đủ thông số chính thức đúng phiên bản xe |
| P2-ASR | P2 | Speech input/output | Text Agent đã nghiệm thu |
| P2-HIL | P2 | Hardware-in-the-loop | Có hardware và production safety plan |

## 10. Dependency gates với team khác

| Gate | Owner chính | Team Agent cần nhận | Nếu chưa có |
|---|---|---|---|
| G-EXT-01 Guardrail contract | Guardrail | Schema/version/sample payload | Dùng mock contract; không claim real integration |
| G-EXT-02 Guardrail real endpoint | Guardrail | Allow/block/query/confirm/monitor APIs | Không thể đóng INT-01/REL-01 |
| G-EXT-03 Permit semantics | Guardrail | Proposal-bound single-use permit | Vehicle Gateway fail closed |
| G-EXT-04 Vehicle state contract | Guardrail + Agent | Snapshot fields/version/source | Không chạy real policy integration |
| G-EXT-05 UI contract | UI + Agent | Request/event schemas | Dùng UI mock consumer |
| G-EXT-06 UI integration build | UI | Real client rendering Agent events | Không thể đóng INT-02/REL-01 |

## 11. Master Agent release checklist

### Agent runtime

- [ ] OpenAI và Gemini adapters chỉ output registered tool proposal/clarification theo shared contract.
- [ ] `auto` chọn provider theo API key và priority cấu hình.
- [ ] Không có API key làm Agent not-ready, không silently dùng model giả.
- [ ] Provider failover không xảy ra sau valid proposal/authorization/execution.
- [ ] Model timeout/malformed output thực thi zero action.
- [ ] Agent không tự sinh policy outcome hoặc permit.
- [ ] Agent không báo success trước successful ExecutionResult.
- [ ] Không parallel state-changing calls.

### Tool và execution

- [ ] Tool mapping 53/53.
- [ ] Behavior/refusal 47/47.
- [ ] Query responder 6/6.
- [ ] Vehicle Tool Gateway là execution boundary duy nhất.
- [ ] Permit proposal-bound, expiring và single-use.
- [ ] Block/error/query/confirm-pending paths gọi handler zero lần.

### Vehicle Simulator

- [ ] State transitions atomic và versioned.
- [ ] State invariants pass property tests.
- [ ] Operator controls không nằm trong Agent tool registry.
- [ ] Operator events có provenance riêng.
- [ ] Reset xóa permit/confirmation/active action.

### Confirmation và monitor integration

- [ ] Confirmation gọi Guardrail re-evaluation.
- [ ] Stale decision/permit không được dùng.
- [ ] Năm monitor intents có start/stop path.
- [ ] Monitor failure không để action tiếp tục im lặng.

### Integration và demo

- [ ] Guardrail real integration pass.
- [ ] UI real integration pass.
- [ ] Sáu hero behaviors hoạt động.
- [ ] Ba scenarios chạy lặp lại sau reset.
- [ ] Adversarial execution suite có zero violation.
- [ ] Agent runbook và known limitations hoàn chỉnh.

### Claim boundary

- [ ] Team Agent không claim đã implement Guardrail.
- [ ] Team Agent không claim đã implement UI.
- [ ] Không claim policy đã được OEM chứng nhận.
- [ ] Không claim simulator phản ánh vật lý VF8.
- [ ] Không claim điều khiển xe thật.
