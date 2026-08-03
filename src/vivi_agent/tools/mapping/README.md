# Tool Mapper

MAP-01 implements the deterministic vertical-slice mapping:

`control_access(action=open, target=driver_door) -> open_door`

The mapper accepts the closed `ActionProposal` contract, revalidates the call
against the TOOL-01 registry, orders canonical arguments as `action`, `target`,
`value`, and computes the contract-compatible proposal digest. It emits a typed
event containing `source_tool` and `canonical_intent`.

Valid registry combinations without an exact reviewed mapping fail with
`UNSUPPORTED_TOOL_MAPPING`; there is no nearest-intent or target fallback.
Duplicate, invalid, or catalog-inconsistent rules fail readiness when the
runtime package is imported. Full catalog coverage is deferred to MAP-02.
