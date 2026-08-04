# EXEC-02 — Xây handler `open_door`

**Trạng thái:** done  
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/vehicle/execution  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục EXEC-02)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

