# E2E-01 — Khóa vertical slice `open_door`

**Trạng thái:** planned  
**Sprint:** sprint-1  
**Code area:** tests/e2e/vertical_slice  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục E2E-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

