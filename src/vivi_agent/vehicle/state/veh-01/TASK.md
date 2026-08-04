# VEH-01 — Định nghĩa Vehicle State Model và invariants

**Trạng thái:** review
**Sprint:** sprint-1  
**Code area:** src/vivi_agent/vehicle/state  
**Nguồn:** specs/agent/VIVI_IMPLEMENTATION_PLAN.md (mục VEH-01)

> Đây là task specification, chưa phải implementation. Khi triển khai, cập nhật tracker chung và giữ acceptance criteria trong file này làm release gate.

**Ưu tiên:** P0  
**Phụ thuộc:** CAT-01, CON-01

**Mô tả:** Định nghĩa state model mà Vehicle Simulator sở hữu và expose snapshot cho Guardrail/UI theo contract. Chỉ dùng field cần cho behavior/Guardrail integration; không tự phát minh ngưỡng VF8.

**Công việc chi tiết:**

- Nhóm state theo power, motion, gear, access, lights, cabin, ADAS, modes, environment, UI và active actions.
- Type, enum, nullability và source/provenance.
- Invariants như `gear=P → speed=0`, cửa mở không thể locked, power off dừng ADAS action.
- Phân biệt source fields và derived fields.
- Default state và preset schema.
- Contract export snapshot/version cho Guardrail.

**Đầu ra:** Vehicle State Model và invariant specification.

**Acceptance criteria:**

- State model cung cấp mọi field Guardrail contract yêu cầu.
- Không field numeric nào được claim là thông số VF8 nếu thiếu nguồn.
- Invalid state combination bị từ chối hoặc normalized theo rule được tài liệu hóa.

## Implementation evidence

- Immutable grouped state model and typed enums: `src/vivi_agent/vehicle/state/model.py`.
- Cross-domain invariant validation and closed Guardrail PIP projection: `src/vivi_agent/vehicle/state/model.py`.
- Deterministic default/preset schema: `src/vivi_agent/vehicle/state/presets.py`.
- Source/derived-field and scope documentation: `src/vivi_agent/vehicle/state/README.md`.
- Invariant, projection, immutability and preset tests: `tests/vehicle/state/test_vehicle_state.py`.
- Current policy-field coverage checked against `Driver_constraints.xlsx`; unavailable
  fields fail closed through per-field provenance instead of using preset defaults.

Invalid combinations are rejected rather than silently normalized. Transition
atomicity, version increments, event storage and preset application remain in
`VEH-02`. All repository tests pass locally; the task remains `review` pending
PM review.

