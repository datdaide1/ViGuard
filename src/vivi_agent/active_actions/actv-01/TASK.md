# ACTV-01 — Xây Active Action Registry

**Trạng thái:** planned  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/active_actions  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục ACTV-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

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

