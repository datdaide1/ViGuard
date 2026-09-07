# History

How the codebase got to where it is, in one page. The git log has the detail.

## The agent (built first)

A standalone tool-calling agent for a reference electric vehicle: closed tool
catalog, provider-neutral model routing, an immutable versioned vehicle state
machine, deterministic-first routing with an LLM fallback for parameter
extraction, and a set of integration contracts. From the start it carried a
mock guardrail speaking a v1 wire contract, so the real guardrail could be
dropped in later without changing agent code.

## The guardrail (four phases)

1. **Decision core.** Built the constraint engine from the policy workbook — a
   closed condition evaluator, a fail-closed 109-rule loader, the `VehicleState`
   schema, and `PolicyEngine`. Reached 100% on the labelled dataset. An earlier
   hand-authored rule YAML was found to be a lossy re-encoding (47/109, several
   mis-encoded) and dropped. Chose the intent classifier: TF-IDF over a PhoBERT
   embedding baseline, measured on an independently generated frozen test set.

2. **HTTP contract layer.** Wrapped the engine in a stdlib HTTP service for the
   agent-authorization path: deterministic `(tool, action, target, value) →
   intent` (a verbatim copy of the agent's map, conformance-tested), the shared
   engine, and a schema-exact decision with a digest-bound single-use permit
   only on `ALLOW`.

3. **CONFIRM + monitor.** Single-use, session-bound, time-boxed confirmations
   that re-evaluate against a fresh state snapshot; the five monitor rules with
   fail-safe-stop semantics.

4. **Fact-shaping + trace + demo.** `ANSWER` returns structured facts the agent
   verbalizes; a per-request trace (stage events + latency + policy checksum);
   `run_demo.py` walking every outcome end-to-end through the real agent and the
   real service; an automated coverage report.

Result: ~1000 agent tests and ~80 guardrail tests, in one `pytest` run.

## What's next

Scaling: multiple agents, multiple vehicle profiles, and a UI. That's a separate
phase — this repo is the single-vehicle pipeline it builds on.
