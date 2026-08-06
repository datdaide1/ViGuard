# CNF-01 — Tích hợp confirmation lifecycle

**Trạng thái:** completed  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/confirmation  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục CNF-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

