# EXEC-01 — Xây Vehicle Tool Gateway và permit verifier

**Trạng thái:** planned  
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/vehicle/execution  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục EXEC-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01, VEH-02

**Mô tả:** Tạo execution boundary duy nhất của team Agent. Gateway chỉ nhận canonical proposal cùng permit Guardrail và từ chối mọi đường không hợp lệ.

**Công việc chi tiết:**

- Validate permit schema/version.
- Verify proposal digest, intent, expiry và single-use status.
- Permit store lifecycle.
- Chặn substitution/replay.
- Execution status namespace riêng.
- Actuator spy và boundary tests.

**Đầu ra:** Vehicle Tool Gateway và Permit Verifier.

**Acceptance criteria:**

- Handler chỉ được gọi từ gateway.
- Block/confirm/error/invalid permit có handler call count bằng 0.
- Replayed/substituted permit bị từ chối.

