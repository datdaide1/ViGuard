# QRY-01 — Xây Query Responder đủ 6/6

**Trạng thái:** planned  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/queries  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục QRY-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** MAP-02, VEH-02, CON-01

**Mô tả:** Trả lời năm state query và một knowledge query dựa trên typed data do Guardrail/state/knowledge provider cung cấp. Không dùng kiến thức tự do của model làm source of truth.

**Công việc chi tiết:**

- Speed, battery, gear, door lock và AVH responders.
- `explain_feature` knowledge-provider adapter.
- Grounded facts/source metadata.
- `ANSWER/UNKNOWN` handling.
- Vietnamese deterministic templates.
- Zero-actuator assertions.

**Đầu ra:** Query Responder Registry.

**Acceptance criteria:**

- Coverage 6/6.
- Missing data trả unknown, không đoán.
- Query path gọi handler zero lần.

