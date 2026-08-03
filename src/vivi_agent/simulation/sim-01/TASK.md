# SIM-01 — Xây Simulation Control API và presets

**Trạng thái:** planned  
**Sprint:** sprint-2  
**Code area:** src/vivi_agent/simulation  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục SIM-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** VEH-02, MON-ADP-01, CON-02

**Mô tả:** Cung cấp operator controls để UI team tạo state chạy/dừng/môi trường cho demo. Đây không phải Agent tool và không đi qua model.

**Công việc chi tiết:**

- Controls cho power, gear, speed state, rain, light, obstacle và driver attention.
- Presets Parked, Driving, Highway/HDA, Charging và Camp.
- Actor `OPERATOR` và distinct event type.
- Invariant validation.
- State-change/monitor triggering.
- Reset endpoint và deterministic seeds.

**Đầu ra:** Simulation Control API và preset catalog.

**Acceptance criteria:**

- Model không nhìn thấy operator controls trong tool registry.
- Operator event không bị ghi thành Agent execution.
- Presets tạo state lặp lại và kích hoạt monitor đúng.

