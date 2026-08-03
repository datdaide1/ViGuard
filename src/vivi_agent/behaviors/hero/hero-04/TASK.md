# HERO-04 — Hoàn thiện confirmation behavior

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** src/vivi_agent/behaviors/hero  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục HERO-04)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** CNF-01, INT-01, INT-02

**Mô tả:** Chọn `open_window` hoặc `open_sunroof` để trình diễn pending confirmation, fresh-state re-evaluation, expiry và replay rejection.

**Công việc chi tiết:**

- Pending event payload.
- Confirm/cancel/expiry handling.
- State-change-before-confirm fixture.
- Permit issuance/consumption sau re-evaluation.
- Replay negative test.

**Đầu ra:** Confirmation hero behavior.

**Acceptance criteria:**

- Chưa confirm không gọi handler.
- Stale decision không được dùng.
- Replay gọi handler zero lần.

