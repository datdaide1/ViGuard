# VEH-02 — Xây Vehicle State Machine và event store

**Trạng thái:** done  
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/vehicle/state  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục VEH-02)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

