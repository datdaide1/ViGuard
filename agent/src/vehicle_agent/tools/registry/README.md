# Domain Tool Registry v1

This package is the only model-facing tool inventory for the Aegis Agent pilot.
It exposes ten coarse domain tools instead of one function per canonical
intent. `domain_tools.v1.json` owns the versioned action/target/value
vocabulary; `registry.py` validates its checksum at startup and produces closed
JSON Schemas as provider-neutral function declarations. MOD-01 owns the thin
serialization layer that wraps those declarations for OpenAI or Gemini.

Model output is untrusted. Call `RUNTIME_TOOL_REGISTRY.validate_call(...)`
before building or sending a Guardrail proposal. The result is either an
immutable `ValidatedToolCall`, a structured `ClarificationRequest` for a
missing parameter, or a typed `ToolCallValidationError`. Unknown tools,
unsupported combinations, additional properties, and model-supplied `state`,
`outcome`, `rule`, `rule_id`, or `permit` fields fail before the Guardrail call.

The registry describes model selection only. It contains no vehicle state,
policy condition, Guardrail outcome, permit, or tool-to-intent mapping. MAP-01
owns deterministic mapping from a validated domain call to a canonical intent.
