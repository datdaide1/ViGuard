# CON-02 — Khóa Agent–UI contract

**Trạng thái:** planned  
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/contracts  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục CON-02)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

