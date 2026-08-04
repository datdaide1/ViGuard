# GRD-ADP-01 — Xây Guardrail Client Adapter và mock server

**Trạng thái:** review
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/adapters/guardrail  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục GRD-ADP-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01

**Mô tả:** Tạo adapter duy nhất để gọi Guardrail thật và một contract-compatible mock để team Agent phát triển độc lập. Mock chỉ mô phỏng contract, không được dùng làm bằng chứng policy correctness.

**Công việc chi tiết:**

- Client timeout/retry policy cho read-only request.
- Không tự retry state-changing authorization khi trạng thái response không rõ.
- Validate response schema/version.
- Mock fixtures allow/block/confirm/query/error.
- Config switch mock/real rõ ràng.
- Event metadata ghi provider `MOCK` hoặc `REAL`.

**Đầu ra:** Guardrail Client Adapter và mock server.

**Acceptance criteria:**

- Mock và real adapter dùng cùng public interface.
- Demo/release mode hiển thị rõ nếu đang dùng mock Guardrail.
- Invalid Guardrail response không thể tới Vehicle Tool Gateway.

**Implementation evidence:**

- `src/vivi_agent/adapters/guardrail/client.py`
- `src/vivi_agent/adapters/guardrail/__init__.py`
- `src/vivi_agent/contracts/guardrail/v1/mock_server.py`
- `tests/adapters/guardrail/test_guardrail_adapter.py`

