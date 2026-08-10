# DOC-01 — Viết Agent integration guide và demo runbook

**Trạng thái:** in_progress
**Sprint:** sprint-3  
**Code area:** docs/agent  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục DOC-01)

> Documentation evidence: `AGENT_INTEGRATION_GUIDE.md` và `DEMO_RUNBOOK.md`. Task chưa completed vì public adapter cho `confirm`, `cancel`, `simulation_control` và ACK chưa có trong checkout.

**Ưu tiên:** P0  
**Phụ thuộc:** SCN-01, SCN-02, SCN-03, OPS-01

**Mô tả:** Tài liệu hóa cách Guardrail/UI teams tích hợp Agent và cách chạy ba scenario từ phía Agent/Vehicle.

**Công việc chi tiết:**

- Startup/config/model prerequisites.
- Guardrail/UI contracts và sample payloads.
- Mock versus real integration.
- Reset/preset/scenario steps.
- Expected Agent/Vehicle events.
- Troubleshooting và degraded modes.
- Claim boundary.

**Đầu ra:** Agent Integration Guide và Demo Runbook.

**Acceptance criteria:**

- Thành viên team khác chạy được Agent bằng contract docs.
- Runbook không yêu cầu sửa code giữa scenarios.
- Phân biệt rõ Agent evidence với Guardrail/UI evidence.

