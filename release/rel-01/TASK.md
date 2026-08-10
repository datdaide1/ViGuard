# REL-01 — Chạy Agent-only release gate

**Trạng thái:** completed — Agent gate pass; external demo readiness reported separately
**Sprint:** sprint-3  
**Code area:** release  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục REL-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** Tất cả task P0

**Mô tả:** Đóng băng Agent/Vehicle build khi toàn bộ coverage, safety và integration gates đạt. Team Agent không sign off correctness nội dung policy hoặc UI visual quality ngoài contract.

**Công việc chi tiết:**

- Unit/contract/integration/E2E tests.
- Agent coverage 53/47/6.
- Guardrail/UI real integration tests.
- Adversarial suite.
- Performance/stability benchmark.
- Ba scenario rehearsal sau clean reset.
- Known limitations và release evidence.

**Đầu ra:** Agent Release Report và frozen demo build.

**Acceptance criteria:**

- Mapping 53/53.
- Behavior/refusal 47/47.
- Query responder 6/6.
- Năm monitor integration paths.
- Zero unauthorized/block-path handler call.
- Ba scenarios pass với Guardrail/UI implementations thật.
- Agent không claim policy/UI tasks thuộc ownership của mình đã hoàn thành thay team khác.

## Cách chạy

```powershell
$env:PYTHONPATH='.;src'
python release/rel-01/run_release_gate.py --external-evidence path/to/external-evidence.json
```

Runner dùng `pytest --import-mode=importlib` vì suite có hai module contract cùng
basename và package scenario `e2e-01`; import mode mặc định không collect được
toàn bộ suite trên Windows.

Gate ghi `release-result.json` và `AGENT_RELEASE_REPORT.md`. Mã thoát `0` khi
toàn bộ Agent suite đạt và worktree được freeze sạch. Sáu evidence ngoài team
chỉ quyết định `integrated_demo_status`, không block `agent_release_status`.
Nếu được cung cấp, external evidence phải trỏ tới artifact thực và khóa nội
dung bằng SHA-256; thiếu evidence được báo rõ, không bị hiểu thành sign-off.

