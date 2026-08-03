# HERO-02 — Hoàn thiện HDA và AAC active behaviors

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** src/vivi_agent/behaviors/hero  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục HERO-02)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** ACTV-01, MON-ADP-01, INT-01

**Mô tả:** Hoàn thiện start/active/continue/stop lifecycle cho `activate_hda` và `activate_aac`.

**Công việc chi tiết:**

- ActiveAction creation.
- Progress/status events.
- HDA monitor-stop handling.
- AAC Stop&Go behavior không tự suy luận policy.
- Stop/fail grounded responses.
- UI fixtures và E2E.

**Đầu ra:** HDA/AAC hero behaviors.

**Acceptance criteria:**

- HDA dừng đúng khi Guardrail monitor yêu cầu.
- Agent không tự đặt monitor threshold.
- UI nhận đủ status để phân biệt policy và execution lifecycle.

