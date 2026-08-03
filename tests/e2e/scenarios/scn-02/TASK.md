# SCN-02 — Scenario “Confirmation không phải giấy phép vĩnh viễn”

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** tests/e2e/scenarios  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục SCN-02)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** HERO-04

**Mô tả:** Đóng gói scenario state an toàn lúc tạo confirmation nhưng thay đổi trước confirm.

**Đầu ra:** Preset sequence, expected events và E2E.

**Acceptance criteria:**

- Agent gọi Guardrail re-evaluation.
- Permit/decision cũ không được tái sử dụng.
- Action bị block khi state mới không phù hợp.

