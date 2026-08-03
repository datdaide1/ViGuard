# COV-01 — Xây Agent capability coverage gate

**Trạng thái:** planned  
**Sprint:** sprint-2  
**Code area:** tests/coverage  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục COV-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-02, BEH-01, QRY-01, ACTV-01

**Mô tả:** Tạo machine-checkable release gate riêng cho Agent; không duplicate policy correctness tests của team Guardrail.

**Công việc chi tiết:**

- Tool mapping 53/53.
- Behavior/refusal 47/47.
- Query responder 6/6.
- Active/monitor integration coverage.
- Tool schema/intent/behavior consistency.
- Missing/duplicate/ambiguous report.
- Agent readiness dependency.

**Đầu ra:** Agent Coverage Report và CI gate.

**Acceptance criteria:**

- Thiếu bất kỳ intent mapping/behavior/responder nào làm readiness fail.
- Report chỉ ra exact ID thiếu.
- Không claim 109-rule correctness; chỉ consume Guardrail policy status.

