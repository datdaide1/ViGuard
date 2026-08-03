# EVT-01 — Xây Agent/Vehicle typed event pipeline

**Trạng thái:** planned  
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/events  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục EVT-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** CON-02, ORC-01, VEH-02, EXEC-01

**Mô tả:** Phát typed events cho UI/observability mà không duplicate Guardrail internal trace.

**Công việc chi tiết:**

- Turn/proposal/decision/execution/state/active-action/response events.
- Ordering và correlation.
- Append-only agent-side event store.
- Redaction.
- Polling/streaming adapter theo UI contract.
- Event fixtures và replay test.

**Đầu ra:** Agent Event Pipeline và event endpoint/stream.

**Acceptance criteria:**

- UI mock tái dựng được complete vertical slice.
- Block path có explicit no-execution evidence.
- Event replay không tái thực thi action.

