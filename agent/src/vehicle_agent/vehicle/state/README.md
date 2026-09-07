# Vehicle State Model v1

`VehicleState` is the simulator-owned, immutable state boundary. It groups power,
motion, transmission, access, lighting, cabin, ADAS, modes, environment, UI and
active actions. Construction rejects invalid combinations; it does not silently
normalize them. This prevents Guardrail and UI consumers from observing a state
different from the caller's intended write.

`to_guardrail_snapshot()` exports the current PIP fields required by
`the policy workbook` and Guardrail state queries, plus `schema_version`,
`state_version` and UTC `timestamp`. The projection contains no policy outcome or
threshold. `door_lock_state` is a derived field: it is `Locked` only when the exact
four-door inventory is present and every door is locked. Motion phase is also
derived-constrained: positive speed requires `MOVING`, while zero requires
`STOPPED`.

Every PIP field carries per-snapshot `StateFieldProvenance`: source, observation
time and availability. A retained value whose provenance is unavailable is stale
diagnostic data, not an authorization fact; Guardrail export fails closed instead
of substituting a default. `rain_sensor` is explicitly nullable because the policy
workbook has a branch for an unknown sensor reading. Preset values are marked with
source `PRESET` and cannot be confused with simulator/operator observations.

Numeric values such as demo speed and seat position are synthetic
simulator state. They are not claimed as the production vehicle specifications. Policy thresholds
remain owned by Aegis's versioned policy parameters.

Presets are deterministic initial conditions. `get_preset()` requires the caller
to supply the state version and timestamp. Applying presets, incrementing versions,
atomic transitions and event persistence remain in `VEH-02`.

The model intentionally allows cabin/accessory power while charging. No current
policy rule uses `powered_on` or `charging`, and the simulator plan includes a
Charging preset; a mutual-exclusion invariant would therefore be unsupported.
