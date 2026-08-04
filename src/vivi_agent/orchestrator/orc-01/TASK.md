# ORC-01 — Xây ViVi Agent Orchestrator nền tảng

**Trạng thái:** review
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/orchestrator  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục ORC-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

