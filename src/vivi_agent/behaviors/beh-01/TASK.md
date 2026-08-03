# BEH-01 — Khai báo behavior catalog đủ 47 action/UI intent

**Trạng thái:** planned  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/behaviors  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục BEH-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-02, EXEC-03

**Mô tả:** Ánh xạ 47 action/UI intent sang handler, parameters, state mutation/event, active-action flag và response facts. Catalog không chứa policy condition/outcome.

**Công việc chi tiết:**

- Behavior cho access, lights, cabin, modes, transmission, ADAS và UI.
- `deactivate_esc` là explicit refusal, không action handler.
- State effects và visual event metadata.
- Active-action metadata cho monitored intents.
- Startup coverage validator.
- Generated basic behavior tests.

**Đầu ra:** Behavior Catalog và coverage report 47/47.

**Acceptance criteria:**

- 47/47 action/UI intent có behavior/refusal.
- Không query intent nào có actuator behavior.
- Mọi executable behavior tạo observable state/event.

