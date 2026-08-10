# P1-WORKFLOW — Compound predefined workflows

**Trạng thái:** completed
**Sprint:** backlog  
**Code area:** backlog/p1  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục P1-WORKFLOW)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Mức:** P1

**Điều kiện bắt đầu:** Single-action safety gates đã đạt

Task này thuộc backlog có thể cắt và không nằm trong release gate P0 hiện tại.

## Phạm vi đã triển khai

- Registry đóng gồm các workflow được review trước; model chỉ chọn `workflow_id`, không tự tạo step.
- Hai workflow ban đầu: `park_and_secure` và `prepare_camp_mode`.
- Tối đa 8 bước và chỉ chấp nhận domain tool state-changing đã đăng ký.
- Agent workflow engine điều phối step tuần tự qua một generic injected step-execution port.
- Engine không import hoặc hiểu UI, Guardrail, permit, policy outcome, vehicle handler hay transport.
- Generic step failure hoặc cancellation dừng workflow ngay; bước Agent tiếp theo không được gọi.
- Không rollback ngầm những bước đã hoàn tất.

## Acceptance criteria

- OpenAI và Gemini nhận cùng closed workflow-selection schema và normalize về cùng provider-neutral proposal.
- Workflow/model ID không tồn tại hoặc arguments mở rộng fail trước khi gọi step runner.
- Definition lỗi, query/explanation step hoặc workflow quá giới hạn fail ở startup.
- Step runner trả typed `WorkflowStepResult`; shape khác fail closed.
- Terminal success chỉ được trả sau khi tất cả step result đều thành công.
- Regression tests chứng minh generic failure/cancel dừng trước bước tiếp theo.

