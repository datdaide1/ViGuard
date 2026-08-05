# RSP-01 — Xây Grounded Response Composer

**Trạng thái:** completed  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/responses  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục RSP-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** ORC-01, QRY-01, BEH-01

**Mô tả:** Chuyển typed Guardrail/execution facts thành response plan và câu trả lời tiếng Việt. Provider model đang được chọn có thể verbalize nhưng deterministic templates luôn là fallback.

**Công việc chi tiết:**

- Response plan schema.
- Templates cho allow, block unsafe, block unavailable, confirm, not voice actionable, answer, unknown và errors.
- Relevant-state formatting.
- Approved recovery suggestions.
- Execution failure/uncertain messages.
- Persona constraints và length limits.

**Đầu ra:** Response Composer và Vietnamese catalog.

**Acceptance criteria:**

- Không invent state, policy reason hoặc execution success.
- Mọi public outcome/error có deterministic fallback.
- `ALLOW` nhưng execution failed không tạo success message.

