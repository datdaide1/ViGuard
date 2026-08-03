# HERO-03 — Hoàn thiện Autopark và Camp mode behaviors

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** src/vivi_agent/behaviors/hero  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục HERO-03)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** ACTV-01, MON-ADP-01, SIM-01

**Mô tả:** Hoàn thiện action kéo dài/compound state cho `activate_autopark` và `activate_campmode`.

**Công việc chi tiết:**

- Start/progress/stop/fail events.
- Compound state transitions.
- Presets đủ/thiếu điều kiện.
- Monitor stop integration.
- Recovery facts và reset behavior.

**Đầu ra:** Autopark/Camp mode hero behaviors.

**Acceptance criteria:**

- Block không tạo progress giả.
- Stop/fail cleanup active action.
- Reset không giữ compound state không hợp lệ.

