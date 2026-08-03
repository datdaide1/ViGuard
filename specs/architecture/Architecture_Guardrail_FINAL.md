# Architecture Specification: ViGuard cho ViVi Agent Simulator

## 0. Tóm tắt kiến trúc

Hệ thống là một modular monolith chạy local, gồm Web UI và backend API, nhưng vẫn giữ boundary rõ ràng: **UI gọi Guardrail Gateway trước; Guardrail trả decision package; ViVi Agent chỉ nhận package đó để phản hồi hoặc thực thi.** Guardrail phân loại text qua T1/T2/T3, chụp Vehicle State Mock và đánh giá constraint trong 109 rule. Guardrail chỉ trả một trong bảy outcome của workbook.

Boundary quan trọng nhất là: **Guardrail quyết định outcome nhưng không thực thi action; chỉ Outcome Router của ViVi Agent được gọi Mock Actuator.** Bất kỳ lỗi classification, lỗi policy, block outcome, missing handler hoặc monitor failure nào cũng fail-safe và không thực thi.

## 1. Bối cảnh

Demo phải mô phỏng đầu-cuối đủ 53 ý định với Guardrail nằm ngoài và đứng trước ViVi Agent. Guardrail là toàn bộ khối phân loại ý định, đọc trạng thái và đánh giá điều kiện ràng buộc; ViVi Agent không nhận văn bản thô để tự quyết định mà chỉ biến `GuardrailDecision` thành phản hồi hoặc hành động mô phỏng.

Workbook hiện có 109 rule: 104 rule `gate`, 5 rule `monitor` và 7 kết quả. Cú pháp điều kiện không hoàn toàn đồng nhất, chẳng hạn dùng cả `=` và `==`, từ khóa logic viết hoa, kiểm tra giá trị rỗng và lời gọi hàm. Vì vậy hệ thống cần bộ phân tích cú pháp đóng thay vì thực thi biểu thức trực tiếp.

## 2. Quyết định kiến trúc

Giải pháp được chọn là một modular monolith chạy local, trong đó UI và backend được đóng gói trong cùng một deployment unit. Backend vẫn chia thành các module có interface rõ ràng; policy và intent catalog được quản lý như data. Lựa chọn này giảm độ phức tạp vận hành cho demo nhưng vẫn giữ boundary cần thiết để thay thế hoặc tách module trong tương lai.

```text
ViVi Web UI
  | POST /commands
  v
Guardrail Gateway
  +--> T1 Regex/Template Matcher
  +--> T2 Lightweight Intent Classifier
  +--> T3 SLM Fallback
  +--> State Store (snapshot)
  +--> Constraint Engine (gate)
  |        returns GuardrailDecision (7 outcomes)
  v
ViVi Agent
  +--> Outcome Router
         +--> Response Composer
         +--> Confirmation Manager --> Guardrail re-evaluation
         +--> Mock Actuator
         +--> Query Responder
  +--> Monitor Coordinator <--> Guardrail Monitor Evaluation
  +--> Trace Store

Policy Loader --> validated in-memory policy
Driver_constraints.xlsx --> Policy Loader
```

## 3. Bất biến kiến trúc

1. Text input là entry point duy nhất; không có ASR trong v1.
2. Guardrail đọc state để đánh giá constraint nhưng không gọi actuator.
3. Constraint Engine bên trong Guardrail không đọc utterance; chỉ nhận intent, state snapshot và evaluation context.
4. Chỉ Outcome Router được gọi Mock Actuator.
5. Mọi block, unknown và pending confirmation đều không gọi actuator.
6. Policy phải load toàn bộ 109 rule hoặc fail closed.
7. UI và automated tests phải bao phủ đủ 53 intent.
8. Không dùng `eval()` hoặc thực thi code lấy từ workbook.
9. Mọi action/state đều có nhãn simulation; không claim tích hợp xe thật.
10. UI gửi text vào Guardrail Gateway trước ViVi Agent; Agent không được bypass Guardrail.
11. T1/T2/T3 chỉ resolve intent; Constraint Engine mới tạo outcome từ intent + state.

## 4. Thành phần

Hệ thống được triển khai trong một process để demo dễ cài đặt, nhưng bên trong vẫn chia thành các module có responsibility và dependency direction rõ ràng. Cách tổ chức này giúp đội triển khai không phải vận hành nhiều service, đồng thời vẫn chứng minh được rằng ViVi Agent không thể tự gọi classifier hoặc bypass Guardrail outcome.

### 4.1. Giao diện web ViVi

UI gồm chat, text input, Intent Explorer đủ 53 intent, Vehicle State panel, execution panel và trace timeline. UI chỉ gửi command tới Guardrail Gateway; nó không tự gọi classifier, policy hoặc actuator. State editor dùng endpoint riêng và mỗi thay đổi tạo một version mới để decision có thể tham chiếu chính xác.

### 4.2. Guardrail Gateway

Guardrail Gateway là backend entry point cho mọi text command. Nó tạo request ID, điều phối ba tầng intent resolution, lấy state snapshot và gọi Constraint Engine. Gateway không có quyền execute action. Sau khi có kết quả hoàn chỉnh, nó chuyển một immutable `GuardrailDecision` sang ViVi Agent.

```text
RECEIVED_BY_GUARDRAIL
 -> CLASSIFIED | CLASSIFICATION_FAILED
 -> CONSTRAINT_EVALUATED
 -> GUARDRAIL_DECISION | GUARDRAIL_ERROR
 -> HANDED_TO_AGENT
```

Gateway tạo request ID, chạy đúng một tuyến T1/T2/T3, lấy state snapshot, gọi Constraint Engine và chuyển immutable GuardrailDecision sang ViVi Agent.

### 4.3. Kiểm tra văn bản trong Guardrail

Bước kiểm tra văn bản là kiểm soát nội bộ trước bộ phân loại. Nó chuẩn hóa chữ, khoảng trắng và kiểm tra các giới hạn đầu vào. Bước này không công bố kết quả quyết định riêng. Văn bản không hợp lệ hoặc có dấu hiệu tấn công tạo một lỗi Guardrail có kiểu rõ ràng và dừng an toàn; hệ thống không được tự thêm kết quả thứ tám ngoài bảy giá trị trong workbook.

### 4.4. Luồng xác định ý định

Luồng này trả một trong 53 ý định hoặc trạng thái nội bộ `CLASSIFICATION_FAILED`. Ba tầng được sắp theo chi phí tăng dần để câu đơn giản kết thúc sớm, còn SLM chỉ xử lý phần khó:

1. **T1 — Regex/Template Matcher:** so khớp tất định sau normalization; không gọi model.
2. **T2 — Lightweight Intent Classifier:** phân loại text vào 53 nhãn; chỉ accept khi confidence và score margin đạt threshold.
3. **T3 — SLM Fallback:** model nhỏ bị giới hạn output vào whitelist 53 intent; không có tool/action/outcome authority.

Cơ chế kết thúc sớm là bắt buộc: T2 không chạy nếu T1 đã xác định được ý định; T3 không chạy nếu T1 hoặc T2 đã thành công. Các mẫu, bộ biến đổi và mô hình được nạp sẵn trước khi hệ thống báo sẵn sàng. Đầu ra của cả ba tầng chỉ là ý định, không phải kết quả Guardrail.

Contract:

```json
{
  "intent": "open_door",
  "status": "CLASSIFIED",
  "tier": "T1",
  "confidence": 1.0,
  "evidence": "mở cửa xe",
  "latency_ms": 2.1
}
```

Pipeline không phải API độc lập; kết quả chỉ được dùng bên trong Guardrail. Output thành công của Guardrail chỉ xuất hiện sau Constraint Engine và là một trong bảy outcome workbook.

### 4.5. ViVi Agent

ViVi Agent đứng sau Guardrail. Đầu vào của Agent là `GuardrailDecision` hoặc một lỗi Guardrail có kiểu, không phải văn bản thô để tự phân loại. Agent chịu trách nhiệm soạn phản hồi, hiển thị xác nhận, trình bày câu trả lời và điều phối hành động. Nó không được thay đổi `intent`, `outcome`, `rule_id` hoặc `state_version` mà Guardrail trả về. Ranh giới này giúp kiểm tra độc lập hai câu hỏi: Guardrail có quyết định đúng theo policy không, và Agent có tuân thủ quyết định đó không.

### 4.6. Vehicle State Store

Kho trạng thái giữ dữ liệu xe mô phỏng trong bộ nhớ và có thể khởi tạo từ JSON cục bộ. Mỗi lần thay đổi làm tăng `state_version`. Guardrail nhận một bản sao bất biến gồm phiên bản và thời điểm chụp, nhờ đó rule đã đánh giá và nhật ký luôn nói về cùng một trạng thái. Lược đồ trường được đối chiếu với các định danh xuất hiện trong 109 điều kiện để phát hiện thiếu dữ liệu ngay khi khởi động.

### 4.7. Policy Loader

Bộ nạp đọc sheet `Constraints` và chuyển workbook thành một tập policy bất biến trong bộ nhớ. Trước khi công bố tập này, nó phải kiểm tra toàn bộ các điều kiện sau:

- đúng 5 cột `rule_id`, `intent`, `condition`, `check_mode`, `outcome`;
- đúng 109 rule duy nhất `R001`–`R109`;
- đủ 53 intent;
- `check_mode` chỉ là `gate` hoặc `monitor`;
- outcome thuộc whitelist;
- mọi condition parse thành AST hợp lệ;
- function/identifier/operator thuộc whitelist.

Nếu một kiểm tra thất bại, ứng dụng chuyển sang trạng thái `POLICY_INVALID`. Giao diện vẫn có thể hiển thị chẩn đoán, nhưng điểm cuối nhận câu lệnh bị khóa. Thiết kế này tránh trường hợp hệ thống chạy với 108 rule chỉ vì đã âm thầm bỏ qua một dòng lỗi.

### 4.8. Condition Parser và Evaluator

Pipeline:

```text
raw condition
 -> tokenize
 -> normalize (`=` -> equality; keyword casing)
 -> parse closed grammar
 -> validate AST whitelist
 -> evaluate against state snapshot + mock function registry
```

Ngữ pháp tối thiểu hỗ trợ giá trị đúng/sai, số, chuỗi, null, phép so sánh, dấu ngoặc, `AND`/`OR`/`NOT`, `is None`, `is not None` và các lời gọi hàm trong danh sách cho phép. Nó cố ý không hỗ trợ truy cập thuộc tính tùy ý, import, đánh chỉ mục tự do hoặc thực thi mã. Do đó workbook có thể biểu diễn policy nhưng không trở thành một kênh chạy mã Python.

### 4.9. Constraint Engine trong Guardrail

Bộ đánh giá cung cấp hai thao tác tách biệt. `evaluate_gate(intent, state_snapshot)` chạy trước khi Agent phản hồi hoặc thực thi và chỉ xét rule `gate` của ý định. `evaluate_monitor(active_action, state_snapshot)` chạy trong lúc hành động mô phỏng đang hoạt động và chỉ xét rule `monitor`. Việc tách hai chế độ ngăn rule theo dõi bị dùng nhầm như điều kiện cấp quyền ban đầu.

```json
{
  "intent": "open_door",
  "rule_id": "R002",
  "check_mode": "gate",
  "outcome": "BLOCK_UNSAFE",
  "state_version": 7,
  "reason_code": "POLICY_CONDITION_MATCHED"
}
```

Một lần đánh giá hợp lệ phải dẫn tới đúng một kết quả. Nếu không rule nào khớp hoặc nhiều rule cùng khớp trái thiết kế, Guardrail trả lỗi policy và dừng an toàn. Nó không tự chọn rule đầu tiên, vì làm như vậy sẽ che giấu lỗ hổng hoặc mâu thuẫn trong workbook.

### 4.10. Outcome Router

ViVi Agent dùng bảng dưới đây như hợp đồng định tuyến duy nhất. Mọi đường gọi bộ thực thi đều tập trung tại đây, nhờ đó kiểm thử có thể khẳng định các kết quả chặn không phát sinh hành động.

| Kết quả | Hướng xử lý |
|---|---|
| `ALLOW` | Mock Actuator |
| `BLOCK_UNSAFE` | Block Response |
| `BLOCK_UNAVAILABLE` | Block Response |
| `CONFIRM` | Confirmation Manager |
| `NOT_VOICE_ACTIONABLE` | Block Response |
| `ANSWER` | Query Responder |
| `UNKNOWN` | Unknown Response |

### 4.11. Confirmation Manager

`CONFIRM` tạo `PendingConfirmation` chứa mã yêu cầu, ý định, rule, tham số, phiên bản trạng thái và thời điểm hết hạn. Đối tượng này chỉ ghi nhận việc người dùng cần xác nhận; nó không chứa quyền gọi bộ thực thi. Khi người dùng đồng ý, Guardrail phải đọc lại trạng thái và đánh giá lần nữa để tránh dùng một quyết định đã cũ.

Khi confirm:

1. Kiểm tra pending còn hiệu lực và chưa dùng.
2. Đọc state snapshot mới.
3. Chạy lại gate policy.
4. Nếu outcome block: kết thúc block.
5. Nếu `ALLOW`: thực thi.
6. Nếu vẫn `CONFIRM` cùng intent/rule: confirmation hiện tại cho phép thực thi một lần.
7. Outcome khác hoặc rule khác: yêu cầu xác nhận mới hoặc fail closed.

### 4.12. Mock Actuator Registry

Registry có một handler cho toàn bộ action/UI intent. Mỗi handler mô tả cách thể hiện action trong môi trường simulation. Handler chỉ được phép:

- cập nhật Vehicle State Mock;
- tạo/cập nhật active action;
- ghi actuator event.

Handler không có external side effect. Query intent không đăng ký action handler. Coverage test so sánh registry với tập intent cần action để phát hiện ngay một intent có `ALLOW` nhưng chưa có cách mô phỏng.

### 4.13. Query Responder

Ý định hỏi trạng thái đọc ảnh chụp trạng thái và điền vào mẫu câu tiếng Việt. `explain_feature` dùng bản đồ kiến thức giả lập, không phải hệ thống RAG sản xuất. Khi thiếu dữ liệu, bộ trả lời giữ nguyên `UNKNOWN`, nói rõ chưa có thông tin và không gọi bộ thực thi.

### 4.14. Monitor Engine

Sau khi thực thi, ý định có rule `monitor` tạo một `ActiveAction`. Bộ theo dõi chạy khi trạng thái thay đổi, khi người demo bấm kiểm tra hoặc khi bộ đếm thời gian kích hoạt. `BLOCK_UNSAFE` và `BLOCK_UNAVAILABLE` làm dừng hành động; `ALLOW` cho phép tiếp tục. Mỗi lần kiểm tra ghi phiên bản trạng thái và rule để người xem hiểu vì sao hành động được giữ hoặc dừng.

### 4.15. Response Composer và Trace Store

Bộ soạn phản hồi ánh xạ kết quả và mã lý do sang thông báo tiếng Việt, tách câu chữ dành cho người dùng khỏi biểu thức kỹ thuật trong policy. Kho truy vết chỉ ghi nối tiếp các sự kiện của phiên demo, nhờ đó lịch sử không bị sửa trong lúc chạy. Đây chưa phải kho kiểm toán sản xuất: dữ liệu có thể mất khi khởi động lại và chưa có cơ chế lưu giữ dài hạn.

## 5. Hợp đồng API

### `POST /api/commands`

Input:

```json
{ "text": "mở cửa xe" }
```

Output:

```json
{
  "request_id": "req_123",
  "intent": "open_door",
  "pipeline_status": "BLOCKED",
  "outcome": "BLOCK_UNSAFE",
  "message": "Không thể thực hiện vì điều kiện an toàn hiện tại chưa phù hợp.",
  "rule_id": "R002",
  "state_version": 7,
  "actuator_called": false
}
```

### 5.2. Các endpoint còn lại

- `GET /api/intents`: danh sách đủ 53 intent và câu mẫu.
- `GET /api/state`, `PATCH /api/state`: xem/chỉnh Vehicle State Mock.
- `POST /api/confirmations/{id}/confirm|cancel`: xử lý xác nhận.
- `POST /api/monitor/tick`: chạy monitor tick thủ công.
- `GET /api/traces/{request_id}`: xem trace end-to-end.
- `GET /api/policy/status`: số intent/rule, checksum và validation status.

## 6. Kiến trúc thông tin giao diện

```text
+---------------------------------------------------------+
| ViVi Agent Simulator                         SIMULATION |
+----------------------+----------------------------------+
| Chat + text input    | Vehicle State Mock              |
| ViVi responses       | presets + editable fields       |
+----------------------+----------------------------------+
| Intent Explorer: search/filter 53 intents              |
+---------------------------------------------------------+
| Pipeline trace | guard | intent | rule | outcome | act. |
+---------------------------------------------------------+
| Active actions / monitor events                         |
+---------------------------------------------------------+
```

Block response nổi bật lý do và state; raw condition chỉ nằm trong detail/debug panel. Confirmation phải là hành động rõ ràng, không dùng một toast tự biến mất.

## 7. Xử lý lỗi và nguyên tắc dừng an toàn

| Lỗi | Hành vi |
|---|---|
| Policy file thiếu/không hợp lệ | Không nhận command; hiển thị `POLICY_INVALID` |
| Không phân loại được intent | Guardrail error response, không constraint evaluation/actuator |
| State field thiếu | Policy đánh giá fail closed hoặc match nhánh explicit null/default |
| Nhiều gate rule cùng match | `POLICY_AMBIGUOUS`, không actuator |
| Không gate rule nào match | `POLICY_NO_MATCH`, không actuator |
| Actuator handler thiếu | `ACTUATOR_NOT_IMPLEMENTED`, không giả thành công |
| Confirmation hết hạn/đã dùng | Từ chối |
| Monitor evaluation lỗi | Dừng active action fail-safe |

## 8. Chiến lược kiểm thử

1. Loader tests: 109/109 rule, 53/53 intent, schema/outcome/mode validation.
2. Parser tests: mọi condition hiện tại parse được; malicious expressions bị từ chối.
3. Classifier tests: mỗi intent có positive examples và confusing/negative cases.
4. Policy tests: từng rule có ít nhất một state làm condition true.
5. Routing tests: từng outcome tới đúng handler; mọi block có zero actuator calls.
6. Confirmation tests: no execution before confirm, re-evaluate state, single use, expiry.
7. Monitor tests: 5 monitor rule có continue và stop scenarios.
8. E2E tests: UI/API bao phủ đủ 53 intent.
9. Determinism tests: cùng text, state snapshot và policy checksum cho cùng result.

## 9. Yêu cầu phi chức năng

- Đường nhanh phân loại intent trong Guardrail ≤ 25 ms p99.
- Gate evaluation ≤ 5 ms p99 sau khi policy đã load.
- Local demo khởi động được khi không có mạng; T3 nếu cần mạng phải có deterministic fallback.
- Một request không tạo quá một actuator execution.
- Log có correlation ID và policy checksum.
- Không log secret/system prompt.

## 10. Các phương án đã cân nhắc

| Phương án | Đánh giá |
|---|---|
| UI gọi thẳng policy/actuator | Loại: dễ bypass và không có trace thống nhất |
| Microservices | Không chọn: quá nặng cho demo local |
| Modular monolith | Chọn: đơn giản triển khai, vẫn giữ boundary |
| Hardcode rule trong code | Loại: lệch source of truth |
| Python `eval()` | Loại: không an toàn và khó validate |
| Closed AST evaluator | Chọn: hỗ trợ workbook nhưng chặn code execution |

## 11. Hệ quả của quyết định

- Demo có thể trình diễn thật đủ 53 intent thay vì slide hoặc subset.
- Policy workbook thay đổi không đòi hỏi sửa routing code nếu schema/grammar không đổi.
- Cần đầu tư parser, state schema, handler registry và test coverage ngay từ đầu.
- `CONFIRM` và monitor làm state machine phức tạp hơn nhưng bắt buộc để không diễn giải sai outcome hiện có.
- Kiến trúc vẫn là simulator; production integration cần PEP/capability, vehicle adapter và security review riêng.

## 12. Thứ tự triển khai

1. Policy loader, parser/evaluator và policy validation report.
2. State schema/store và policy engine gate/monitor.
3. Guardrail contract và classifier nội bộ đủ 53 intent.
4. Orchestrator, outcome router và trace.
5. Mock Actuator/Query Responder/Confirmation/Monitor.
6. ViVi UI và Intent Explorer.
7. Coverage, latency, negative-security và E2E test suite.

## 13. Yêu cầu và ràng buộc kiến trúc

### 13.1. Động lực chức năng

| ID | Driver |
|---|---|
| AD-01 | Nhận text và xử lý end-to-end qua ViVi Agent |
| AD-02 | Guardrail phân loại đủ 53 intent |
| AD-03 | Guardrail nạp và đánh giá đủ 109 rule |
| AD-04 | Chỉ trả bảy outcome workbook |
| AD-05 | `ALLOW` thực thi Mock Actuator; block không thực thi |
| AD-06 | `CONFIRM` re-evaluate state trước execution |
| AD-07 | `ANSWER`/`UNKNOWN` không đi qua actuator |
| AD-08 | Năm monitor rule được chạy trên active action |
| AD-09 | UI quan sát được toàn bộ trace và coverage |

### 13.2. Thuộc tính chất lượng

| Thuộc tính | Yêu cầu | Cách kiến trúc đáp ứng |
|---|---|---|
| Safety | Không chắc chắn thì không action | Fail-closed defaults, single execution boundary |
| Determinism | Cùng input/state/policy cho cùng kết quả | Immutable snapshot, policy checksum, deterministic evaluator |
| Auditability | Truy được lý do từng outcome | Rule ID, state version, stage events |
| Maintainability | Policy đổi không sửa business logic | Workbook loader + closed grammar |
| Testability | Test độc lập từng module | Pure evaluator, dependency injection, mock registry |
| Demo reliability | Chạy local, hạn chế network dependency | Modular monolith, in-memory/local storage, optional T3 |
| Performance | Phân loại/policy đủ nhanh | Warm-loaded policy, in-memory indexes |

### 13.3. Ràng buộc

- Một máy demo, một process backend, một người dùng chính.
- Text input; không có ASR.
- Workbook là input được kiểm soát nhưng không được tin cậy như code.
- State và actuator đều mô phỏng.
- Không database server, message broker hoặc distributed transaction trong v1.
- Không thay đổi tên intent hoặc rule ID trong runtime.
- Hệ thống phải chạy được khi không có mạng; mọi dependency online phải có fallback hoặc bị tắt rõ ràng.

## 14. Bối cảnh hệ thống

```text
┌──────────────────────┐
│ Người demo/reviewer │
└──────────┬───────────┘
           │ text command, state edits, confirmations
           ▼
┌─────────────────────────────────────────────────────────┐
│ ViGuard ViVi Agent Simulator                            │
│ Web UI + ViVi Agent + Guardrail + Mock Vehicle         │
└──────────┬──────────────────────────────┬───────────────┘
           │ reads                        │ optional call
           ▼                              ▼
┌──────────────────────┐       ┌────────────────────────┐
│ Driver_constraints  │       │ Constrained LLM (T3)  │
│ .xlsx, 109 rules     │       │ optional/fallback     │
└──────────────────────┘       └────────────────────────┘
```

Không có kết nối từ hệ thống tới xe, ECU hoặc actuator thật.

## 15. Logical Architecture

### 15.1. Module Boundaries

| Module | Input | Output | Không được làm |
|---|---|---|---|
| Web UI | User interaction/API responses | Commands/state edits/confirms | Gọi actuator hoặc evaluate rule trực tiếp |
| Guardrail Gateway | Text + request context | 7-outcome decision hoặc typed error | Gọi actuator hoặc giao text thẳng cho Agent |
| ViVi Agent | GuardrailDecision/error | User response + authorized simulation command | Tự phân loại, đọc constraint hoặc đổi outcome |
| Text Check | Normalized text | Pass/error metadata | Công bố outcome mới |
| Intent Classifier | Text | 53-intent result/internal failure | Đọc vehicle state |
| State Store | Validated updates | Immutable snapshot | Tin state từ utterance |
| Policy Loader | Workbook | Validated PolicySet | Bỏ qua row lỗi |
| Constraint Engine | Intent + snapshot | GuardrailDecision | Đọc raw utterance hoặc dùng `eval()` |
| Outcome Router | GuardrailDecision | Route result | Bỏ qua confirmation |
| Confirmation Manager | Pending + user decision | Execute/reject/re-prompt | Giữ live actuator permission |
| Mock Actuator Registry | Authorized simulated command | State/event changes | External side effects |
| Query Responder | Query intent + snapshot | Answer/unknown response | Gọi actuator |
| Monitor Engine | Active action + snapshot | Continue/stop decision | Tiếp tục khi evaluation lỗi |
| Trace Store | Typed events | Session trace | Lưu secret/system prompt |

### 15.2. Quy tắc phụ thuộc

```text
UI -> API -> Guardrail Gateway -> Intent Resolution (T1 -> T2 -> T3)
                              -> State Store (read-only snapshot)
                              -> Constraint Engine -> Validated PolicySet
                              -> GuardrailDecision
                              -> ViVi Agent -> Outcome Router
                                            -> Confirmation/Actuator/Responder

Monitor Coordinator -> Guardrail Monitor Evaluation -> GuardrailDecision
GuardrailDecision -> ViVi Agent Outcome Router -> Mock Actuator stop
```

Dependency chỉ đi theo chiều trên. UI và ViVi Agent không được gọi classifier/Constraint Engine trực tiếp. Mọi start/stop action đều đi qua Outcome Router; Mock Actuator không được import/call từ UI, Guardrail Gateway, classifier, Constraint Engine hoặc Monitor Coordinator.

## 16. Runtime Data Flow

### 16.1. Trình tự khi được cho phép

```text
User -> UI: submit text
UI -> API: POST /commands
API -> Guardrail: evaluate(text)
Guardrail -> Classifier: classify(text)
Classifier --> Guardrail: intent
Guardrail -> StateStore: snapshot()
StateStore --> Guardrail: state@version
Guardrail -> ConstraintEngine: evaluate_gate(intent, snapshot)
ConstraintEngine --> Guardrail: ALLOW + rule_id
Guardrail --> ViViAgent: decision
ViViAgent -> OutcomeRouter: route(decision)
OutcomeRouter -> MockActuator: execute(intent)
MockActuator --> OutcomeRouter: execution event
ViViAgent --> UI: success response + trace
```

### 16.2. Trình tự khi bị chặn

Luồng giống ALLOW tới GuardrailDecision. Outcome Router chọn Response Composer, không gọi Mock Actuator. Trace bắt buộc có `actuator_called=false`.

### 16.3. Trình tự khi cần xác nhận

```text
Guardrail -> ViViAgent: CONFIRM + rule + state_version
ViViAgent -> ConfirmationManager: create pending
ViViAgent --> UI: confirmation prompt
User -> UI: confirm
UI -> ConfirmationManager: confirm(id)
ConfirmationManager -> StateStore: fresh snapshot
ConfirmationManager -> Guardrail/ConstraintEngine: re-evaluate
alt block
  ConfirmationManager --> UI: block response
else allow or same confirmation rule
  ConfirmationManager -> OutcomeRouter: one-time execution
  OutcomeRouter -> MockActuator: execute
end
```

### 16.4. Trình tự theo dõi hành động

Sau execution, registry trả `starts_active_action=true` nếu intent có monitor rule. Monitor Engine đăng ký session. Mỗi state update hoặc tick tạo snapshot mới, đánh giá monitor rule và tiếp tục hoặc gọi `stop()` trên Mock Actuator.

## 17. Domain Model

### 17.1. Các thực thể cốt lõi

```text
CommandRequest
  request_id, session_id, text, created_at

ClassificationResult
  intent, tier, confidence, evidence, latency_ms

VehicleStateSnapshot
  state_version, captured_at, values

PolicyRule
  rule_id, intent, condition_ast, check_mode, outcome

GuardrailDecision
  request_id, intent, rule_id, check_mode, outcome,
  state_version, reason_code, latency_ms, policy_checksum

PendingConfirmation
  confirmation_id, request_id, intent, rule_id,
  created_at, expires_at, status

ExecutionEvent
  execution_id, request_id, intent, handler, status,
  state_before, state_after, created_at

ActiveAction
  action_id, request_id, intent, status, started_at,
  last_monitor_rule, last_state_version
```

### 17.2. Ràng buộc giá trị

- `intent` phải thuộc exact set 53 intent.
- `outcome` phải thuộc exact set 7 outcome.
- `rule_id` theo `R001`–`R109` và duy nhất.
- `state_version` tăng đơn điệu trong một process.
- `PendingConfirmation.status`: `PENDING`, `CONFIRMED`, `CANCELLED`, `EXPIRED`, `CONSUMED`.
- `ActiveAction.status`: `ACTIVE`, `STOPPED_BY_POLICY`, `COMPLETED`, `FAILED_SAFE`.

## 18. Guardrail Contract

### 18.1. Public Interface

```python
class Guardrail:
    def evaluate(self, text: str, request_context: RequestContext) -> GuardrailResult:
        ...

    def reevaluate(self, intent: str, state_snapshot: VehicleStateSnapshot) -> GuardrailResult:
        ...
```

`GuardrailResult` là tagged union:

- `GuardrailDecision` với đúng một trong bảy outcome; hoặc
- `GuardrailError` cho validation/classification/runtime error.

`GuardrailError` không phải outcome, không được route sang actuator và không được thống kê như policy decision.

### 18.2. Các giai đoạn nội bộ

1. Validate và normalize text.
2. Thực hiện Text Check.
3. Classify intent.
4. Capture state snapshot.
5. Evaluate gate constraints.
6. Emit GuardrailDecision và trace.

### 18.3. Khi không phân loại được

Nếu không ánh xạ đủ tin cậy vào 53 intent, Guardrail trả typed error `CLASSIFICATION_FAILED`. ViVi Agent phản hồi yêu cầu diễn đạt lại. Không có rule/outcome giả, không gọi actuator.

## 19. Thiết kế nạp và đánh giá policy

### 19.1. Vòng đời nạp policy

```text
read workbook -> validate headers/counts -> normalize rows
-> tokenize/parse conditions -> validate identifiers/functions
-> construct immutable PolicySet -> compute checksum
-> build indexes by (intent, check_mode) -> publish healthy status
```

PolicySet chỉ được publish sau khi toàn bộ validation pass. Reload thất bại giữ application ở fail-closed state; không trộn rule cũ và mới trong cùng checksum.

### 19.2. Ngữ pháp điều kiện đóng

```text
expression  := or_expr
or_expr     := and_expr (OR and_expr)*
and_expr    := not_expr (AND not_expr)*
not_expr    := NOT not_expr | comparison | '(' expression ')'
comparison  := operand comparator operand
             | operand IS [NOT] NONE
             | function_call comparator operand
operand     := identifier | number | string | boolean | NONE
comparator  := = | == | != | < | <= | > | >=
```

Parser normalize `=` thành equality token. Evaluator chỉ truy cập dictionary state và function registry; không cho attribute access, arbitrary indexing, lambda, import hoặc call ngoài whitelist.

### 19.3. Ngữ nghĩa đánh giá

- Lọc rules theo exact intent và `check_mode`.
- Evaluate trên cùng immutable snapshot.
- Một decision hợp lệ cần đúng một matched rule theo policy design.
- Zero match tạo `POLICY_NO_MATCH` error; multi-match tạo `POLICY_AMBIGUOUS` error.
- Error luôn fail closed.
- `monitor` rules không được dùng làm gate và ngược lại.

### 19.4. Function Registry

Function trong condition phải được đăng ký bằng tên, signature, deterministic behavior và test fixture. `kb_has_feature(feature_id)` đọc knowledge map mock; không gọi web hoặc LLM.

## 20. Vehicle State Architecture

### 20.1. Lược đồ trạng thái

Schema được khai báo tường minh gồm field name, type, enum/range, nullable và UI control. Loader đối chiếu mọi identifier trong condition với schema; identifier lạ làm policy invalid.

### 20.2. Quy tắc thay đổi trạng thái

- UI update được validate toàn bộ trước commit.
- Một mutation thành công tăng version đúng một lần.
- Mock Actuator mutation đi qua cùng State Store API như UI.
- Mỗi update phát `state_changed` cho Monitor Engine.
- Reset/preset cũng là mutation có trace.

### 20.3. Tính nhất quán

Gate evaluation dùng snapshot tại một thời điểm. Confirmation luôn lấy snapshot mới. Trong demo single-process không cần distributed lock; State Store serialize mutation và snapshot để tránh partial update.

## 21. Mock Execution Model

### 21.1. Handler Interface

```python
class MockActionHandler:
    intent: str
    def execute(self, command, state_store) -> ExecutionResult: ...
    def stop(self, active_action, state_store) -> StopResult: ...
```

### 21.2. Handler Categories

- **State mutation:** cửa, đèn, gương, mode, signal.
- **One-shot event:** mở notification center hoặc action khó biểu diễn bằng state.
- **Active action:** camp/pet/autopark/AAC/HDA khi cần monitor.
- **No handler:** state/knowledge query và mọi block outcome.

Registry validation chạy lúc startup và so sánh handler set với intent metadata. Intent cần action nhưng thiếu handler làm demo health degraded/fail launch gate.

## 22. API Specification

### 22.1. Câu lệnh

`POST /api/v1/commands`

Request:

```json
{
  "session_id": "demo-01",
  "text": "mở cửa xe"
}
```

Decision response:

```json
{
  "request_id": "req-001",
  "status": "COMPLETED",
  "intent": "open_door",
  "outcome": "BLOCK_UNSAFE",
  "message": "Không thể thực hiện vì điều kiện an toàn hiện tại chưa phù hợp.",
  "decision": {
    "rule_id": "R002",
    "check_mode": "gate",
    "state_version": 12,
    "policy_checksum": "sha256:..."
  },
  "execution": null,
  "latency_ms": 8.4
}
```

Classification error response không có `outcome`:

```json
{
  "request_id": "req-002",
  "status": "NEEDS_REPHRASE",
  "error": { "code": "CLASSIFICATION_FAILED" },
  "message": "ViVi chưa hiểu yêu cầu này, bạn vui lòng diễn đạt lại."
}
```

### 22.2. Trạng thái

- `GET /api/v1/state`
- `PATCH /api/v1/state` với optimistic `expected_version`
- `POST /api/v1/state/presets/{preset_id}`

Version mismatch trả `409 STATE_VERSION_CONFLICT`.

### 22.3. Xác nhận

- `POST /api/v1/confirmations/{id}/confirm`
- `POST /api/v1/confirmations/{id}/cancel`

Expired/consumed confirmation trả `409 CONFIRMATION_NOT_ACTIVE`.

### 22.4. Quan sát và kiểm tra

- `GET /api/v1/intents`
- `GET /api/v1/policy/status`
- `GET /api/v1/traces/{request_id}`
- `GET /api/v1/actions/active`
- `POST /api/v1/monitor/tick`

## 23. Error Model

| Error code | HTTP | User behavior | Actuator |
|---|---:|---|---|
| `INVALID_TEXT` | 400 | Sửa input | Không |
| `CLASSIFICATION_FAILED` | 200/422 theo API choice | Yêu cầu diễn đạt lại | Không |
| `POLICY_INVALID` | 503 | Demo không nhận command | Không |
| `POLICY_NO_MATCH` | 500 | Fail-safe message | Không |
| `POLICY_AMBIGUOUS` | 500 | Fail-safe message | Không |
| `STATE_VALIDATION_FAILED` | 400 | Sửa state | Không |
| `STATE_VERSION_CONFLICT` | 409 | Refresh/retry | Không |
| `CONFIRMATION_NOT_ACTIVE` | 409 | Tạo command mới | Không |
| `ACTUATOR_NOT_IMPLEMENTED` | 500 | Fail-safe message | Không |
| `ACTUATOR_FAILED` | 500 | Báo execution failure | Không giả success |
| `MONITOR_FAILED` | 500 | Dừng active action | Stop fail-safe |

## 24. Thiết kế bảo mật và an toàn

### 24.1. Ranh giới đe dọa

- User text là untrusted input.
- Workbook là configuration input: được quản lý nhưng vẫn phải parse an toàn.
- State edits là untrusted UI input.
- Optional LLM response không được có quyền gọi actuator.

### 24.2. Biện pháp kiểm soát

- Closed grammar; không `eval()`.
- Strict schema/type/length limits cho API.
- Whitelist 53 intent, 7 outcome, identifiers và functions.
- Single actuator boundary qua Outcome Router.
- Confirmation expiry và replay protection trong process.
- No secrets trong client bundle/log.
- CORS chỉ local origin trong demo.
- External network disabled by default.

### 24.3. Giới hạn tuyên bố an toàn

Kiến trúc chứng minh software tuân theo workbook và state mock. Nó không chứng minh constraint đúng với xe thật, không chống developer cố ý bypass ở cấp production và không thay thế safety case/OEM validation.

## 25. Observability

### 25.1. Các giai đoạn truy vết

`received -> text_checked -> classified -> state_captured -> constraint_evaluated -> outcome_routed -> confirmation/execution/query -> monitor -> completed`

### 25.2. Chỉ số đo lường

- request count theo intent/outcome;
- classification tier/latency;
- constraint evaluation latency;
- block/allow/confirm/query rates;
- actuator call count và block-path violations;
- active action/monitor stop count;
- policy health, checksum, intent/rule coverage;
- error count theo typed error code.

### 25.3. Điểm cuối kiểm tra tình trạng

- `/health/live`: process sống.
- `/health/ready`: policy valid, state store ready, handler coverage valid.
- `/api/v1/policy/status`: chi tiết 53/109/104/5 và checksum.

## 26. Performance và Capacity

Demo target là single user, request tuần tự hoặc concurrency thấp. Không cần horizontal scaling. Policy được load/parse một lần và index trong memory.

| Stage | Budget |
|---|---:|
| Text normalization + T1 regex/template | ≤5 ms p99 |
| T2 lightweight classifier | ≤20 ms p99 |
| Constraint evaluation | ≤5 ms p99 |
| Mock Actuator | ≤5 ms p99 |
| T3 SLM | Đo riêng, không nằm trong fast-path SLO |

Benchmark ghi CPU/device, sample size, warm-up và p50/p95/p99/max. Không dùng average làm tiêu chí ship. Báo cáo bắt buộc có tỷ lệ request được resolve ở T1/T2/T3, SLM call rate và end-to-end latency theo từng route.

### 26.1. Thiết kế tối ưu độ trễ

- Workbook được đọc, normalize và parse đúng một lần khi startup.
- Condition AST được compile/cache trong immutable `PolicySet`.
- Rules được index theo `(intent, check_mode)`; không quét 109 rule theo request.
- Regex/templates, T2 vectorizer/model và T3 SLM được warm-load trước khi health `ready`.
- T1/T2/T3 short-circuit; không speculative-run cả ba tầng.
- Vehicle State nằm trong memory và snapshot không thực hiện I/O ngoài process.
- Response message dùng template; không gọi SLM lần hai để diễn giải outcome.
- Accuracy gate có ưu tiên cao hơn tier coverage: không nới threshold chỉ để giảm SLM call rate.

## 27. Persistence và Lifecycle

### 27.1. Phiên bản đầu tiên

- Policy: workbook trên disk, read-only.
- State: memory, tùy chọn seed từ JSON.
- Trace: memory hoặc JSONL local theo session.
- Active actions/confirmations: memory, mất khi restart.

Restart phải hủy mọi pending confirmation và active action; không khôi phục action như đang chạy.

## 28. Deployment Topology

```text
Developer/Demo machine
  ├── Backend process
  │     ├── API
  │     ├── ViVi Agent + Guardrail
  │     ├── in-memory state/trace
  │     └── Driver_constraints.xlsx (read-only)
  └── Browser
        └── ViVi Web UI
```

Startup order:

1. Load configuration.
2. Load/validate policy.
3. Validate state schema và function registry.
4. Validate intent/classifier/handler coverage.
5. Initialize state presets.
6. Expose ready health và UI.

Nếu bước 2–4 fail, UI vẫn có thể hiển thị diagnostics nhưng command execution bị khóa.

## 29. Testing Architecture

### 29.1. Kiểm thử đơn vị

- tokenizer/parser/AST validation;
- each operator/function;
- outcome router;
- confirmation state transitions;
- state validation/versioning;
- response templates.

### 29.2. Kiểm thử hợp đồng và tích hợp

- workbook -> PolicySet 109/109;
- Guardrail -> seven-outcome contract;
- Outcome Router -> actuator/query/confirmation;
- state update -> monitor tick;
- API schema/error model.

### 29.3. Kiểm thử đầu-cuối

- ít nhất một scenario cho mỗi 53 intent;
- allow/block/confirm/not-voice/answer/unknown;
- 5 monitor rules;
- text chứa fake state;
- classifier failure không có outcome/actuator;
- policy invalid startup diagnostics.

### 29.4. Kiểm thử bảo mật và trường hợp âm

- malicious condition strings bị parser từ chối;
- prompt-like text không có khả năng gọi tool trực tiếp;
- block path actuator spy luôn zero;
- confirmation replay/expiry;
- malformed state payloads.

## 30. Trade-offs và Alternatives

### 30.1. Modular Monolith so với Microservices

Chọn modular monolith vì deployment local, scale thấp và cần tốc độ triển khai. Module boundaries vẫn rõ để có thể tách sau. Microservices tăng network failure, packaging và observability cost mà không tạo giá trị cho pilot.

### 30.2. Policy khai báo trong workbook so với viết cứng trong mã

Chọn workbook-driven để giữ policy source of truth và audit bằng rule ID. Đổi lại cần loader/parser/validation nghiêm ngặt.

### 30.3. Closed AST so với `eval()`

Chọn closed AST vì deterministic, inspectable và hạn chế code execution. Chi phí là phải duy trì grammar/function whitelist.

### 30.4. Mô phỏng đủ 53 ý định so với tập đại diện

Chọn full coverage theo yêu cầu sản phẩm. Handler có thể tối giản, nhưng không được thiếu intent. Chi phí tăng ở mapping, sample utterances và tests.

## 31. Rủi ro kiến trúc

| Rủi ro | Tác động | Mitigation |
|---|---|---|
| Classifier catalog lệch workbook | Intent không có policy | Startup coverage validation |
| Workbook condition overlap/gap | Decision không xác định | Exhaustive/static checks + fail closed |
| Handler semantics không phản ánh action | Demo gây hiểu nhầm | Explicit mock behavior catalog |
| State schema thiếu field | Policy runtime error | Load-time identifier validation |
| Optional LLM làm demo phụ thuộc mạng | Demo gián đoạn | Offline fallback và feature flag |
| UI che mất technical trace | Không audit được | Decision/trace panels bắt buộc |

## 32. Architecture Definition of Done

- Module interfaces và dependency rules được hiện thực đúng.
- Guardrail public contract chỉ có bảy outcome workbook; error là typed error riêng.
- Loader xác minh 53 intent, 109 rule, 104 gate, 5 monitor.
- Mọi condition parse bằng closed AST.
- State snapshot/version và re-evaluation hoạt động.
- Outcome Router là execution boundary duy nhất.
- Handler coverage đủ action/UI intent; query không có handler.
- Confirmation và monitor state machines pass test.
- API, error model, trace và health endpoints được triển khai.
- E2E coverage đủ 53 intent và tất cả outcome.
- Deployment local chạy offline theo demo contract.
