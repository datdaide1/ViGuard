# MON-ADP-01 — Tích hợp Guardrail Monitor

**Trạng thái:** planned  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/adapters/monitor  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục MON-ADP-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** CON-01, GRD-ADP-01, ACTV-01, EXEC-01

**Mô tả:** Phía Agent subscribe state changes/manual tick, gọi Guardrail monitor evaluation và dừng active action qua Vehicle Tool Gateway khi Guardrail trả stop/block/error.

**Công việc chi tiết:**

- State-change subscription.
- Monitor request adapter.
- Continue/stop/error routing.
- Stop authorization contract với Guardrail.
- Fail-safe stop khi monitor response invalid/timeout theo contract đã duyệt.
- Monitor events và metrics.

**Đầu ra:** Monitor Integration Adapter.

**Acceptance criteria:**

- Năm monitor intents có integration path.
- Stop đi qua registered gateway/handler, không mutate state trực tiếp.
- Monitor error không để action tiếp tục im lặng.

