# SCN-03 — Scenario “Guardrail bảo vệ khi action đang chạy”

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** tests/e2e/scenarios  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục SCN-03)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** HERO-02, SIM-01

**Mô tả:** Đóng gói HDA active action bị monitor dừng sau operator state change.

**Đầu ra:** HDA preset sequence, expected events và E2E.

**Acceptance criteria:**

- Operator action có provenance riêng.
- State change trigger Guardrail monitor call.
- Agent dừng action qua gateway và phát stop response/event.

