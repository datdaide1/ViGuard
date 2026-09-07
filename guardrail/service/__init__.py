"""the HTTP layer — HTTP contract layer for the Agent authorization path (CON-01).

The Agent's LLM has already chosen a ``tool`` + ``arguments``; it sends a closed
``ActionProposal`` (no intent, no text). This service:

  1. maps ``(tool, action, target, value) -> intent`` deterministically, with the
     *same* table the Agent uses (``tool_map``, conformance-tested), then
  2. evaluates the shared ``PolicyEngine`` against the Guardrail-owned vehicle
     state (``state_store``), then
  3. returns a schema-exact ``GuardrailDecision`` / ``GuardrailError``, with a
     digest-bound single-use ``ActionPermit`` only on ``ALLOW`` (``envelope``).

The Phase 1 TF-IDF classifier is NOT on this path — it serves the Gateway /
Simulator path (text -> intent). See docs/DECISIONS.md.
"""
