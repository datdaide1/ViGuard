# OPS-01 — Xây Agent/Vehicle reset và degraded mode

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** src/vivi_agent/operations  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục OPS-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** SIM-01, ACTV-01, ORC-01

**Mô tả:** Bảo đảm Agent/Vehicle runtime reset sạch, phát hiện Guardrail/UI/model unavailable và không giả success.

**Công việc chi tiết:**

- Clear turns/proposals/permits/confirmations/active actions.
- Reset Vehicle State và presets.
- Model unavailable fallback.
- Guardrail unavailable fail-closed response.
- UI disconnect/reconnect event semantics.
- Health/readiness dependency status.

**Đầu ra:** Reset/degraded-mode APIs và tests.

**Acceptance criteria:**

- Reset không giữ usable permit hoặc active action.
- Guardrail unavailable thực thi zero action.
- UI reconnect không replay side effect.

