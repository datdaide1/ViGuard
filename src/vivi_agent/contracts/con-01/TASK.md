# CON-01 — Khóa Guardrail–Agent contract

**Trạng thái:** review  
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/contracts  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục CON-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** Không

**Mô tả:** Định nghĩa exact request/response/event contract giữa Agent và Guardrail. Contract phải phân biệt intent classification, action authorization, confirmation và monitor evaluation; không gộp policy outcome với execution status.

**Công việc chi tiết:**

- Định nghĩa schema cho `ActionProposal`.
- Định nghĩa schema cho `GuardrailDecision` và typed error.
- Chốt bảy outcome và quy tắc outcome nào có permit.
- Định nghĩa proposal digest, permit fields, expiry và single-use semantics.
- Định nghĩa confirmation và monitor request/response.
- Tạo version field cho contract.
- Tạo sample payload cho allow, ba block outcomes, confirm, answer, unknown và error.
- Tạo consumer contract tests chạy được với mock server.

**Đầu ra:** Guardrail–Agent API schema, examples và consumer tests.

**Acceptance criteria:**

- Agent reject response thiếu `intent/outcome/rule_id/state_version` khi các field đó bắt buộc.
- Block/error/confirm-pending response không thể chứa usable permit.
- Contract version mismatch tạo typed integration error và zero execution.

## Implementation evidence

- Versioned schema: `src/vivi_agent/contracts/guardrail/v1/guardrail-agent.schema.json`.
- Outcome/request/response fixtures: `src/vivi_agent/contracts/guardrail/v1/examples.json`.
- Fail-closed validator and digest reference: `src/vivi_agent/contracts/guardrail/v1/contract.py`.
- Deterministic HTTP protocol mock: `src/vivi_agent/contracts/guardrail/v1/mock_server.py`.
- Consumer suite: `tests/contracts/guardrail/test_consumer_contract.py`.

Agent-side acceptance tests pass locally. Status remains `review` until the Guardrail team approves `G-EXT-01`, `G-EXT-03`, and the shared portion of `G-EXT-04`; this task does not claim that external approval.

