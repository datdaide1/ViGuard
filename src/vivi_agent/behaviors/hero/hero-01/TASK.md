# HERO-01 — Hoàn thiện `open_door` behavior

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** src/vivi_agent/behaviors/hero  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục HERO-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** INT-01, INT-02

**Mô tả:** Nâng `open_door` thành reference behavior cho state-aware action, fake-state attack và allow/block contrast.

**Công việc chi tiết:**

- Complete behavior facts/events.
- Relevant state và recovery metadata.
- Allow/block fixtures.
- Fake-state utterance fixture.
- Deterministic reset.
- E2E với Guardrail/UI thật.

**Đầu ra:** Reference `open_door` hero behavior.

**Acceptance criteria:**

- Same intent cho behavior khác đúng decision từ Guardrail.
- Agent không tin state trong model/user text.
- Block path có zero permit consumption/handler call.

