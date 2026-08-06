# INT-02 — Chạy integration với UI thật

**Trạng thái:** completed  
**Sprint:** sprint-2  
**Code area:** tests/integration  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục INT-02)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

