# Agent Performance/Stability Report (PERF-01)

**Task:** PERF-01 — Benchmark Agent/Vehicle latency và stability
**Sprint:** Sprint 3
**Code area:** `tests/performance/perf-01`
**Status:** Local (offline) pipeline measured and reported below. Live model
warm-up/tool-selection latency is **explicitly out of scope for this run** —
see §5.

---

## 0. What this report is and isn't

Per this project's own principle (never claim a number that wasn't
measured): this report only contains numbers this harness actually produced,
run right before this report was written, on this machine, with the exact
command in §6. Where something wasn't measured, it's marked "not measured"
rather than estimated.

**Scope boundary.** This benchmark exercises the real `AgentOrchestrator` →
`GuardrailClientAdapter` (real HTTP, real contract validation) →
`VehicleToolGateway` (real permit verification, real handler dispatch) code
path. It does **not** call a real model provider — a deterministic
in-process `MockModelRouter` stands in for the LLM (see
[`benchmark.py`](benchmark.py) module docstring). This was a deliberate,
PM-approved scoping decision for this run (avoid spending live
`GEMINI_API_KEY` quota / depending on network availability for the P0
latency numbers that don't need it) — not a claim that model latency is
irrelevant. §5 covers what's still outstanding.

---

## 1. Environment

| | |
|---|---|
| Python | 3.11.7 |
| Platform | Windows-10-10.0.26200-SP0 |
| Processor | Intel64 Family 6 Model 141 Stepping 1, GenuineIntel |
| Network environment | **Loopback only** (`127.0.0.1`) to an in-process mock Guardrail HTTP server (`vivi_agent.contracts.guardrail.v1.mock_server`). Zero third-party network calls anywhere in this run. |
| Model provider | **None** — deterministic in-process `MockModelRouter`. `provider="mock"`, `model_id="deterministic-test-router-v1"`. Not a real model; see §5. |
| Guardrail | Mock fixture server (contract-shape-accurate, policy-free) — the same server INT-01 uses. Not the real Guardrail service. |
| Run date | 2026-08-07 |
| Warm-up | No explicit warm-up phase was run separately from the measured samples (see §4.1 for why — the data itself doesn't show a monotonic warm-up trend worth excluding). |

---

## 2. Latency results

All 6 latency dimensions below are measured against the **real production
code path** (real HTTP round-trip, real permit verification, real handler
dispatch) — only the model call is mocked. `sample_size` is the exact number
of iterations; all values in milliseconds.

### 2.1 Guardrail round-trip (Agent-side, `GuardrailClientAdapter.evaluate()`)

| sample_size | min | p50 | p95 | p99 | max | mean |
|---:|---:|---:|---:|---:|---:|---:|
| 300 | 1.784 | 13.347 | 18.583 | 21.265 | 29.246 | 11.676 |

### 2.2 Permit verification + handler latency (`VehicleToolGateway.execute()`)

| sample_size | min | p50 | p95 | p99 | max | mean |
|---:|---:|---:|---:|---:|---:|---:|
| 300 | 0.164 | 0.559 | 1.384 | 1.476 | 1.604 | 0.628 |

### 2.3 End-to-end Agent turn latency — ALLOW path (`AgentOrchestrator.handle_message()`)

Full `RECEIVED → RESOLVING → PROPOSED → AUTHORIZING → EXECUTING → COMPLETED` turn.

| sample_size | min | p50 | p95 | p99 | max | mean |
|---:|---:|---:|---:|---:|---:|---:|
| 300 | 1.954 | 6.838 | 20.365 | 29.170 | 33.246 | 10.226 |

### 2.4 End-to-end Agent turn latency — BLOCK path

Full `RECEIVED → RESOLVING → PROPOSED → AUTHORIZING → BLOCKED` turn (no execution stage — included for contrast, not a TASK.md-required dimension).

| sample_size | min | p50 | p95 | p99 | max | mean |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 2.159 | 5.551 | 18.850 | 25.702 | 28.191 | 8.772 |

### 2.5 Model warm-up / tool-selection latency

**Not measured in this run.** See §5.

---

## 3. Stability

### 3.1 Repeated scenarios

500 consecutive ALLOW turns run back-to-back through one long-lived
`AgentOrchestrator` instance without error (`handler_call_count: 500`, zero
failures). No crashes, no unbounded latency drift observed across the run
(§2.3's p95/p99/max come from this same style of repeated-run sampling).

### 3.2 Memory growth

Traced Python heap (`tracemalloc`, GC forced at each checkpoint) over 500
repeated ALLOW turns, sampled every 50 turns:

| iteration | traced current (KB) | traced peak (KB) |
|---:|---:|---:|
| 50 | 325.9 | 405.8 |
| 100 | 492.9 | 572.6 |
| 150 | 657.0 | 734.1 |
| 200 | 816.1 | 893.2 |
| 250 | 970.9 | 1051.0 |
| 300 | 1131.0 | 1211.0 |
| 350 | 1291.1 | 1371.8 |
| 400 | 1450.5 | 1526.8 |
| 450 | 1609.7 | 1690.6 |
| 500 | 1788.7 | 1849.3 |

**Finding: linear, unbounded growth — ~2.9 MB per 1,000 turns** (measured:
1,462.8 KB growth over 450 turns between the first and last checkpoint →
2,925.6 KB/1,000-turn rate). This is **not GC noise** (each checkpoint forces
`gc.collect()` first) and **not the permit store** (this harness clears it
every iteration to work around the mock fixture's fixed `permit_id` — see
§4.2 — so it can't be the cause here).

**Root cause, identified by reading the code (not guessed):**
[`VehicleEventStore`](../../../src/vivi_agent/vehicle/state/events.py)
(used internally by `VehicleStateMachine`, which `make_open_door_handler`
wraps) appends one `StateChangedEvent` — including a full `VehicleState`
snapshot — per successful transition, and **by explicit design retains every
event for the lifetime of the machine**:

> "The store retains all events for the lifetime of the machine (no
> truncation in VEH-02 scope; truncation/replay is a SIM-01 concern)."
> — `events.py` module docstring

This is documented, intentional behavior, not a bug — but it means a
long-running vehicle session with no periodic reset **will** grow memory
without bound, at roughly the rate measured here. That reset/truncation
policy is explicitly deferred to a different ticket (**OPS-01** — "Xây
Agent/Vehicle reset và degraded mode" — currently `planned` in the tracker).
**Recommendation: OPS-01 should treat `VehicleEventStore` unbounded growth
as one of its concrete inputs**, not just an abstract "add a reset
endpoint" — the growth rate here gives it a real number to design a
retention/truncation policy against.

**Secondary observation (not exercised numerically here — this harness
clears it every iteration, see §4.2):** `PermitStore._consumed_permits` in
[`verifier.py`](../../../src/vivi_agent/vehicle/execution/verifier.py) is a
plain `set[str]` with a `.clear()` method but no TTL or automatic eviction.
In production, every real proposal gets a unique `permit_id`, so this set
also grows unboundedly over a session's lifetime unless something calls
`.clear()`. Flagging alongside the event-store finding for the same OPS-01
follow-up, since it wasn't independently measured this round.

### 3.3 Timeout behavior

Two probes, both against an unreachable Guardrail (`http://127.0.0.1:1`,
`timeout_seconds=0.2`):

| probe | error_code | elapsed | handler calls | side effect? |
|---|---|---:|---:|---|
| Direct client (`GuardrailClientAdapter.evaluate()`) | `GUARDRAIL_UNAVAILABLE` | 204.4 ms | 0 | none |
| Full turn (`AgentOrchestrator.handle_message()`) | `ORCHESTRATION_DEPENDENCY_ERROR` (turn status: `failed`) | 216.4 ms | 0 | none |

**Result: acceptance criterion met.** Both probes return in bounded time
close to the configured 0.2 s timeout (no hang — verified against a 10×
slack bound in `test_perf01_benchmark.py`, which passes), and the actuator
handler is called **zero** times in both cases — a Guardrail timeout does
not reach the vehicle. State-changing evaluation is not retried (matches
INT-01's `test_error_timeout_and_degraded_scenarios`), so this is one
attempt at the configured timeout, not `timeout × retries`.

One design note observed while wiring this: `AgentOrchestrator`'s generic
exception handler deliberately collapses the real `GuardrailAdapterError`
(which does carry a specific `retryable` flag, `False` in this case) into a
generic `ORCHESTRATION_DEPENDENCY_ERROR` with `retryable` always unset at
the turn level — by design, per the code comment ("Guardrail transport
failures ... are deliberately collapsed without leaking internals"). Not a
defect; noted here only because it means turn-level `retryable` cannot be
used to distinguish transport timeouts from other dependency failures — a
caller that needs that distinction has to go through Guardrail-side
diagnostics/logs, not the turn result.

---

## 4. Methodology notes

### 4.1 On the bimodal guardrail round-trip latency

Raw samples cluster into two bands roughly ~2–4 ms and ~13–18 ms rather than
a single smooth distribution (visible in the gap between `min` 1.8 ms and
`p50` 13.3 ms in §2.1, and confirmed by inspecting raw samples directly — no
monotonic first-N-calls-slower/faster trend, i.e. not a warm-up effect).
**Hypothesis, not fact:** `GuardrailClientAdapter._post()` opens a new
`urllib.request.urlopen()` connection per call with no keep-alive/connection
pooling; the two-band pattern is consistent with a known Windows
loopback-TCP artifact (new-connection setup interacting with
`ThreadingHTTPServer`'s per-connection thread spin-up and/or
Nagle/delayed-ACK), but this run did not isolate the exact mechanism. **Do
not treat the p95/p99 numbers in §2.1/§2.3 as representative of Linux or a
real (non-loopback) network** — re-measuring on the actual target deployment
OS/network is a prerequisite before using these numbers for a release gate
or SLO.

### 4.2 Why the permit store is cleared every iteration

The mock Guardrail server's ALLOW fixture (`examples.json`) always mints the
same `permit_id: "permit-001"`. Real proposals get unique permit IDs; this
is a property of the test fixture, not of the real Guardrail. Without
clearing `gateway.store` between iterations, every iteration after the
first would short-circuit on `ReplayAttackError` (correctly — that's the
anti-replay guarantee working as designed) rather than measuring real
permit-verification + handler latency each time. This is called out
explicitly in [`benchmark.py`](benchmark.py) at each call site.

### 4.3 Fixed clock for permit verification

The fixture's ALLOW permit has a static validity window
(`2026-08-03T10:00:00Z`–`10:00:02Z`). `VehicleToolGateway.execute()` is
called with `current_time=FIXED_TIME` (`2026-08-03T10:00:01Z`) via a
`FixedClockExecutor` adapter — the same pattern INT-01's `SpyExecutor` uses
— so measurements reflect real code cost, not `PERMIT_EXPIRED` failures
caused by the run date (2026-08-07) being after the fixture's static expiry.

---

## 5. Not measured (explicitly out of scope for this run)

| Item | Status | Why |
|---|---|---|
| Gemini model warm-up / tool-selection latency | Not measured | PM decision for this run: measure the local pipeline first (no live-quota cost), defer live Gemini timing to a follow-up. `GEMINI_API_KEY` is present in `.env` and confirmed working (EVAL-01, commit `629b25f`) — the follow-up can reuse `evals/eval-01/runner.py`'s existing `latency_ms`-per-outcome tracking directly. |
| OpenAI model warm-up / tool-selection latency | Not measured | No `OPENAI_API_KEY` configured in this environment (same blocker EVAL-01 documents). |
| Real (non-mock) Guardrail service latency | Not measured | Only the contract-shape mock server was available; this measures the Agent-side adapter/orchestrator overhead, not the real Guardrail's own processing time. |
| Non-loopback network latency | Not measured | Everything here ran on `127.0.0.1`; see §4.1's caveat before generalizing to a real network path. |
| Concurrent/multi-session load | Not measured | This run is single-threaded, one session at a time. `AgentOrchestrator._session_locks` serializes per-`session_id` by design; concurrent-session throughput was not benchmarked. |

---

## 6. Reproduction

```bash
py -3 tests/performance/perf-01/run_benchmark.py \
  --out tests/performance/perf-01/results/local_run.json
```

Offline pytest coverage (small-N, verifies harness logic incl. the timeout
zero-side-effect assertion) is part of the normal suite:

```bash
py -3 -m pytest tests/performance/perf-01/test_perf01_benchmark.py -v
```

Raw JSON for the numbers in this report:
[`results/local_run.json`](results/local_run.json).

---

## 7. Acceptance criteria

- ✅ **Report ghi provider, exact model ID, network environment, sample size và warm-up** — §1/§2 (provider explicitly "none/mock" with the real values deferred to §5; warm-up methodology explained in §1 and §4.1).
- ✅ **Không claim số chưa đo** — §5 lists every dimension not measured, by name, with the specific reason; no number is reported for any of them.
- ✅ **Timeout không gây side effect hoặc treo turn vô hạn** — §3.3, both a direct-client and a full-orchestrator probe, both bounded time and zero handler calls, both covered by a passing automated test (`test_turn_timeout_zero_handler_side_effects_bounded_time`).
