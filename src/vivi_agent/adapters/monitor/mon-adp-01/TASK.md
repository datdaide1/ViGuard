# MON-ADP-01 — Tích hợp Guardrail Monitor

**Trạng thái:** completed  
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

> ⚠️ **Xem [DEFERRED_FOLLOWUPS.md](./DEFERRED_FOLLOWUPS.md)** — 2 gap chưa xử lý:
> stop hiện chưa thật sự đi qua VehicleToolGateway (chỉ update registry nội bộ), và
> adapter chưa được wire vào orchestrator/bootstrap nên chưa chạy trong production.
> Tạm ignore, quay lại sau khi hoàn tất build agent.

