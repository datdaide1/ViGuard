# INT-01 — Chạy integration với Guardrail thật

**Trạng thái:** planned  
**Sprint:** sprint-2  
**Code area:** tests/integration  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục INT-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** GRD-ADP-01, COV-01, CNF-01, MON-ADP-01

**Mô tả:** Thay mock bằng Guardrail implementation của team khác và chạy contract/integration suite. Mọi mismatch phải được xử lý tại adapter hoặc thống nhất contract, không vá bằng business logic trong handler.

**Công việc chi tiết:**

- Contract version handshake.
- Allow/block/query/confirm/monitor scenarios.
- Permit/digest compatibility.
- State snapshot/version compatibility.
- Error/timeout/degraded scenarios.
- Joint trace correlation.

**Đầu ra:** Guardrail Integration Report.

**Acceptance criteria:**

- Agent chạy được mọi public outcome của Guardrail.
- Block/error path gọi handler zero lần.
- Mock và real Guardrail cùng pass consumer tests.

