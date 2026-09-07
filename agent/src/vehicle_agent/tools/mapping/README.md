# Tool Mapper

The mapper is the fail-closed boundary between a model's validated tool call
and a canonical policy intent. It accepts the closed `ActionProposal`
contract, revalidates the call against the TOOL-01 registry, orders
canonical arguments as `action`, `target`, `value`, and computes the
contract-compatible proposal digest. It emits a typed event containing
`source_tool` and `canonical_intent`.

## Coverage (MAP-02)

`DEFAULT_MAPPING_RULES` maps all **78 valid `domain_tools.v1.json`
combinations** onto all **53 approved intents** in `intent_manifest.v1.json`.
Five domain-tool groups intentionally map several combinations to the same
intent, because the registry's `target`/`value` becomes a normalized
parameter on a single intent rather than a distinct intent per combination:

| Intent | Combinations | Normalized via |
| --- | --- | --- |
| `ad_steeringwheel` | `control_cabin.adjust.steering_wheel.{forward,backward,up,down}` | `value` (direction) |
| `ad_driverseat_angle` | `control_cabin.adjust.driver_seat_angle.{forward,backward,up,down}` | `value` (direction) |
| `ad_driverseat_pos` | `control_cabin.adjust.driver_seat_position.{forward,backward,up,down}` | `value` (direction) |
| `open_window` | `control_cabin.open.{driver_window,front_passenger_window,rear_left_window,rear_right_window}` | `target` (window) |
| `explain_feature` | `explain_vehicle_feature.explain.<14 features>` | `target` (feature) |

The remaining 48 intents are each reachable through exactly one combination.
No mapper logic change was needed for this: `map_proposal` already builds
`CanonicalAction.normalized_arguments` straight from the registry-validated
call, not from the matched `MappingRule`, so several rules pointing at the
same intent with different `target`/`value` "just work".

Valid registry combinations without an exact reviewed mapping fail with
`UNSUPPORTED_TOOL_MAPPING`; there is no nearest-intent or target fallback.
Duplicate, invalid, catalog-inconsistent, or **incomplete** (an intent with
zero reviewed mappings) rule sets fail readiness when the runtime package is
imported (`MappingReadinessError`, e.g. `INCOMPLETE_MAPPING_COVERAGE`).

`build_coverage_report(rules, manifest)` is a non-raising companion for
authoring/CI: unlike the constructor (which fails closed on the first
defect), it walks a candidate rule set once and returns every missing,
duplicate, and ambiguous mapping ID it finds. `tests/tools/test_tool_mapper.py`
asserts the report on `DEFAULT_MAPPING_RULES` is empty/complete.

## `map_call(ValidatedToolCall, ...)` seam — deferred, not implemented

MAP-02's task spec conditions adding a `map_call(ValidatedToolCall,
proposal_metadata=...)` entry point on it eliminating real duplicate
validation for an existing consumer, without allowing that consumer to
bypass the `ActionProposal` trust boundary or proposal-digest binding. As of
this change, `AgentOrchestrator` is the only caller of the mapper and it
calls `map_proposal(action_proposal)` directly — there is no code path that
already produces a `ValidatedToolCall` before reaching the mapper. Adding the
seam now would be a speculative API with no consumer, which the task spec
explicitly rules out. Revisit if/when an actual caller needs it.
