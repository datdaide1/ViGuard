# Decisions

The choices that shaped the design, with the reasoning. Not reopened without a
new reason.

## Architecture

**D1 — Two separate services, one HTTP contract.** The guardrail
(`guardrail/`) and the agent (`agent/`) are independent, not a monorepo library.
*Why:* the guardrail is the safety-critical half; keeping it swappable behind a
versioned contract means it can be replaced or upgraded without a coordinated
change in the agent, and either side can be reasoned about on its own. The
tool→intent map and the digest function are **copied** into both sides, with a
conformance test that fails if they drift.

**D-authz — The agent owns a stable authorization port.** `ActionAuthorizer` /
`ConfirmationAuthorizer` / `MonitorAuthorizer` are the seam. Aegis-specific HTTP,
wire schema and mock live only under `agent/.../integrations/aegis`; core agent
code never imports them. *Why:* a wire-version change is then localized to the
integration boundary, and another authorization service can implement the same
ports. (Was ADR-001.)

**D2 — The guardrail returns structured facts; the agent verbalizes.** `ANSWER`
carries `answer = {grounded, facts}` read from vehicle state (e.g.
`{"speed": 0}`). The agent turns that into a sentence. *Why:* the guardrail
stays a policy component with no natural-language surface; grounding lives on one
side.

## Policy

**D3 — One source of truth for the 109 rules: the policy workbook.** Parse the
`condition` column directly (`guardrail/policy/constraints.csv`, byte-equal to
the labelled dataset's `rules.json`). An earlier hand-authored YAML re-encoding
covered only 47/109 rules and mis-encoded several (wrong intent, wrong enum
case, wrong boolean shape) and was dropped rather than salvaged.

**D4 — One `VehicleState` schema, names and enums from the workbook.** `speed`
not `speed_kmh`; lowercase `day` / `night`; `door_lock_state` (a string) not
`doors_locked` (a bool). *Why:* the condition strings reference these identifiers
literally; any divergence is an evaluation bug.

**`speed < 3` means "fully stationary".** Every rule that gates on `speed < 3`
means the vehicle is not moving; 1–2 km/h creep is not a safe state for a
door/trunk/seat action. The evaluator normalizes `speed < 3` → `speed == 0`, and
the labelled dataset is labelled under the same rule.

## Classifier

**T2 — TF-IDF, not embeddings.** `char2-5 + word1-2` n-grams + LinearSVC,
no-abstain, as the primary text→intent classifier. On an independent frozen test
set: **88.3%** vs a PhoBERT-embedding + LinearSVC baseline at **79.2%** and a
keyword baseline at **53.4%**. *Why:* a general similarity model blurs exactly
the distinctions that matter here (đèn pha ↔ đèn cốt, xi-nhan trái ↔ phải); char
n-grams catch the distinguishing token directly. It is also lighter
(scikit-learn only) and ~7–50× faster. Abstain is kept in code (`T2Config`) but
off by default — it costs ~5 points of accuracy. See `docs/METRICS.md`.

Note: this classifier is on the **gateway** path (free text → intent). The
agent-authorization path does not use it — the agent sends a structured tool
call and both sides run the same deterministic map.

## HTTP layer

**D5-http — stdlib `http.server`, no framework.** Zero third-party dependency for
the service. One process, `127.0.0.1:<port>`, `py -3 -m guardrail.service`.

**Digest** is a sha256 over the canonical projection `{arguments,
contract_version, proposal_id, session_id, source_turn_id, tool}` —
`sort_keys`, `separators=(",",":")`, `ensure_ascii=False`, `allow_nan=False`.
Copied verbatim on both sides and locked against the shared `examples.json`.

**Confirmation** is single-use and session-bound: a confirm request from a
different session than the one that raised the `CONFIRM` is rejected without
consuming the token. Re-evaluation always reads a fresh state snapshot.

**Monitor "keep running"** is expressed on the wire as `ALLOW` + a synthetic
request-bound permit, because contract v1 has no dedicated monitor-continue
signal (the agent's monitor adapter treats anything other than `ALLOW` as a
stop). A candidate for a v1.1 contract change.

## Deferred

- **UI** — its own phase.
- **T3 (a small language model tier)** — the deterministic path is enough for the
  demo; revisit if the text→intent numbers need it.
- **`turnon_LKA`** — the agent's tool map reaches it but the workbook has no rule
  for it, so the service returns a typed error (never `ALLOW`). Needs a workbook
  rule or removal from the map.
