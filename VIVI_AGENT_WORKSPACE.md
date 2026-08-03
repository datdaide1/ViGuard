# ViVi Agent implementation workspace

Workspace này chuyển kế hoạch Agent-only thành scaffold theo code boundary để chuẩn bị triển khai. Hiện tại chỉ có thư mục và `TASK.md`; chưa có runtime code, test code, dataset hay integration implementation.

## Quy ước

- Nguồn yêu cầu chuẩn: `specs/agent/VIVI_IMPLEMENTATION_PLAN.md`.
- Tracker chung: `VIVI_AGENT_TASK_TRACKER.yaml`.
- Mỗi task nằm trong folder feature/code tương lai của chính nó.
- Chỉ đổi trạng thái tracker khi có evidence tương ứng.
- Guardrail và UI là external dependencies; scaffold này không claim implementation của hai team đó.
- P1/P2 nằm trong `backlog/` và không thuộc release gate P0.

## Phân vùng

- `src/vivi_agent/`: runtime feature boundaries của Agent/Vehicle.
- `tests/`: contract, integration, E2E, coverage và performance tasks.
- `evals/`: model-selection và adversarial evaluation tasks.
- `docs/agent/`: integration guide/runbook task.
- `release/`: release-gate task.
- `backlog/`: các task P1/P2 có thể cắt.

## Trạng thái scaffold

- Tổng số task: 48.
- P0: 39.
- External gates: 6.
- Hoàn thành: 0.

## Tracker semantics

- `depends_on` chỉ chứa task ID nội bộ và luôn là YAML array.
- `external_gate_ids` chứa dependency do team Guardrail hoặc UI sở hữu.
- `start_condition` mô tả điều kiện để cân nhắc task backlog, không phải dependency đã schedule.
- `REL-01` phụ thuộc tường minh vào các P0 task còn lại và không tự phụ thuộc chính nó.
