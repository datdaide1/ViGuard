# PERF-01 — Benchmark Agent/Vehicle latency và stability

**Trạng thái:** planned  
**Sprint:** sprint-3  
**Code area:** tests/performance  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục PERF-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** INT-01, INT-02, EVAL-01

**Mô tả:** Đo riêng phần Agent/Vehicle và end-to-end integration trên máy demo; không nhận metric Guardrail nội bộ làm metric của team Agent.

**Công việc chi tiết:**

- Model warm-up và tool selection latency.
- Guardrail round-trip từ phía Agent.
- Permit verification và handler latency.
- End-to-end Agent turn latency.
- p50/p95/p99/max.
- Repeated scenarios, memory growth và timeout behavior.

**Đầu ra:** Agent Performance/Stability Report.

**Acceptance criteria:**

- Report ghi provider, exact model ID, network environment, sample size và warm-up.
- Không claim số chưa đo.
- Timeout không gây side effect hoặc treo turn vô hạn.

