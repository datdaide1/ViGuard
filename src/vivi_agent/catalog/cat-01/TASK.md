# CAT-01 — Xây runtime intent/behavior manifest

**Trạng thái:** review
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/catalog  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục CAT-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01

**Mô tả:** Tạo manifest Agent-side cho exact 53 intent hiện tại, loại intent, domain tool, behavior category, query/action flag, parameter requirements và monitor capability. Manifest không chứa condition hoặc outcome policy.

**Công việc chi tiết:**

- Trích exact set 53 intent từ artifact đã duyệt.
- Phân loại 47 action/UI và 6 query.
- Đánh dấu `deactivate_esc` là explicit refusal behavior.
- Đánh dấu các intent có monitor rule dựa trên metadata do Guardrail cung cấp.
- Định nghĩa sample utterances chỉ phục vụ Agent evaluation/UI fixtures.
- Tính manifest checksum và validate khi startup.

**Đầu ra:** Intent/behavior manifest và coverage validator.

**Acceptance criteria:**

- Manifest có đúng 53 intent duy nhất.
- Không chứa dynamics intent ngoài catalog.
- Manifest thiếu hoặc thừa intent làm Agent readiness fail.

## Implementation evidence

- Versioned 53-intent manifest: `src/vivi_agent/catalog/intent_manifest.v1.json`.
- Immutable loader, checksum, and fail-closed readiness validator: `src/vivi_agent/catalog/manifest.py`.
- Startup usage and ownership boundary: `src/vivi_agent/catalog/README.md`.
- Coverage/tamper tests: `tests/catalog/test_intent_manifest.py`.

The intent inventory and five monitor rule IDs were checked against the approved
`Driver_constraints.xlsx` workbook. No Guardrail condition or outcome policy is
stored in the manifest. Agent-side acceptance and regression tests pass locally;
the task remains `review` pending PM review.

