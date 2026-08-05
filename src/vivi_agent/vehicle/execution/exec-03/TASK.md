# EXEC-03 — Xây generic handler framework

**Trạng thái:** review  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/vehicle/execution  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục EXEC-03)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

