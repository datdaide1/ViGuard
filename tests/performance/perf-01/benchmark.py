"""PERF-01 — local Agent/Vehicle latency & stability benchmark harness.

Measures, against the *real* production code paths (real HTTP guardrail
round-trip over loopback, real ``VehicleToolGateway`` permit verification +
handler dispatch, real ``AgentOrchestrator`` turn sequencing):

  - Guardrail round-trip latency (Agent-side, over HTTP to a local mock server)
  - Permit verification + handler latency
  - End-to-end Agent turn latency
  - Memory growth over repeated turns
  - Timeout fail-closed behavior (bounded time, zero handler side effects)

Scope boundary (see AGENT_PERFORMANCE_REPORT.md for the full explanation):
model warm-up and tool-selection latency are NOT measured here. This harness
uses a deterministic, in-process ``MockModelRouter`` (same pattern as
INT-01's integration tests) instead of a real model provider — measuring a
mock router's call latency would not be a real number and this project's
own principle is to never report a number that wasn't actually measured.
Live model latency is a separate, explicitly out-of-scope follow-up (see the
report's "Not measured" section) because it requires spending real
GEMINI_API_KEY quota, which was intentionally deferred out of this run.

Nothing in this module performs network I/O to a third party — the only
socket traffic is loopback HTTP to the in-process mock guardrail server
started by ``LocalPerfHarness``.
"""

from __future__ import annotations

import copy
import gc
import math
import os
import sys
import threading
import time
import tracemalloc
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src"))
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
for _path in (SRC_PATH, ROOT_PATH):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from vivi_agent.adapters.guardrail import (
    GuardrailAdapterError,
    GuardrailClientAdapter,
    GuardrailClientConfig,
    GuardrailProvider,
)
from vivi_agent.catalog import load_manifest
from vivi_agent.contracts.guardrail.v1.contract import proposal_digest
from vivi_agent.contracts.guardrail.v1.mock_server import create_server
from vivi_agent.model_providers import ModelActionProposal, ProviderMetadata, TurnBinding
from vivi_agent.orchestrator import (
    AgentOrchestrator,
    CancellationToken,
    TurnRequest,
    TurnStatus,
)
from vivi_agent.tools.mapping import load_default_mapper
from vivi_agent.tools.registry import load_registry
from vivi_agent.vehicle.execution import VehicleToolGateway, make_open_door_handler
from vivi_agent.vehicle.state import VehicleStateMachine

EXAMPLES = __import__("json").loads(
    Path(SRC_PATH, "vivi_agent/integrations/viguard/wire/examples.json").read_text(encoding="utf-8")
)

# Deliberately labelled "mock" — this is not a real model provider and its
# latency numbers must never be reported as model latency (see module docstring).
MOCK_MODEL_METADATA = ProviderMetadata("mock", "deterministic-test-router-v1", "sha256:mock", 0)
# Must fall inside the mock ALLOW fixture's permit validity window
# (issued_at 2026-08-03T10:00:00Z .. expires_at 2026-08-03T10:00:02Z, see
# examples.json) — same fixed clock INT-01 uses, for the same reason: the
# fixture's timestamps are static test data, not tied to wall-clock "today".
FIXED_TIME = datetime(2026, 8, 3, 10, 0, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Percentile / summary statistics (stdlib only — no numpy dependency in this repo)
#
# evals/eval-01/scoring.py has its own linear-interpolation percentile
# (`_latency_stats`/nested `_percentile`) computing the same core formula.
# Deliberately NOT imported from here: it's a private (`_`-prefixed) nested
# closure, not independently callable; it's on a 0-1 `p` scale vs. this
# module's 0-100 `pct`; it returns p50/p95 only (no p99/min/max, which this
# harness needs); and importing it would pull eval-01-specific dependencies
# into a perf-01 benchmark. A shared stats module would remove the
# duplication properly, but every existing per-ticket folder in this repo
# (int-01, eval-01, eval-02, perf-01, ...) is self-contained with no shared
# test-utils module today — introducing one is an architecture change this
# review pass intentionally left out-of-scope rather than doing silently.
# --------------------------------------------------------------------------


def percentile(sorted_samples: list[float], pct: float) -> float:
    """Linear-interpolation percentile (matches numpy's default 'linear' method)."""
    if not sorted_samples:
        raise ValueError("cannot compute a percentile of an empty sample set")
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    k = (len(sorted_samples) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_samples[int(k)]
    d0 = sorted_samples[int(f)] * (c - k)
    d1 = sorted_samples[int(c)] * (k - f)
    return d0 + d1


@dataclass(frozen=True)
class LatencySummary:
    sample_size: int
    min_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "sample_size": self.sample_size,
            "min_ms": round(self.min_ms, 3),
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "mean_ms": round(self.mean_ms, 3),
        }


def summarize(samples_ms: list[float]) -> LatencySummary:
    if not samples_ms:
        raise ValueError("cannot summarize an empty sample set")
    ordered = sorted(samples_ms)
    return LatencySummary(
        sample_size=len(ordered),
        min_ms=ordered[0],
        p50_ms=percentile(ordered, 50),
        p95_ms=percentile(ordered, 95),
        p99_ms=percentile(ordered, 99),
        max_ms=ordered[-1],
        mean_ms=sum(ordered) / len(ordered),
    )


# --------------------------------------------------------------------------
# Deterministic model router (see module docstring — not a real provider)
# --------------------------------------------------------------------------


class MockModelRouter:
    """Deterministic in-process router — same shape as INT-01's test double.

    No network I/O, no model inference. Used so the Guardrail/Vehicle/
    Orchestrator latency measured here isolates *this codebase's* overhead
    from third-party model provider latency, which this harness explicitly
    does not measure (see module docstring).
    """

    def __init__(self, outcome: str = "allow") -> None:
        self._outcome = outcome

    def propose_tool(self, messages: list[dict[str, str]], binding: TurnBinding) -> ModelActionProposal:
        proposal = ModelActionProposal.action(
            "control_access", {"action": "open", "target": "driver_door"}, MOCK_MODEL_METADATA
        )
        binding.record_proposal(proposal)
        return proposal

    def compose_response(self, facts: Mapping[str, Any], turn: TurnBinding) -> ModelActionProposal:
        return ModelActionProposal.response("Phản hồi thông tin xe.", MOCK_MODEL_METADATA)


class FixedClockExecutor:
    """Adapts ``VehicleToolGateway`` to the Orchestrator's ``ActionExecutor``
    protocol (``execute(proposal, decision, cancellation)``, no
    ``current_time`` parameter) while pinning permit verification to
    ``FIXED_TIME`` — same pattern as INT-01's ``SpyExecutor``. Without this,
    the gateway's default ``current_time=None`` resolves to real wall-clock
    time, which is always past the mock fixture's static 2026-08-03 permit
    expiry, and every ALLOW turn would fail with PERMIT_EXPIRED regardless
    of how fast the pipeline actually ran.
    """

    def __init__(self, gateway: VehicleToolGateway) -> None:
        self.gateway = gateway

    def execute(self, proposal: Mapping[str, Any], decision: Mapping[str, Any], cancellation: Any) -> Any:
        return self.gateway.execute(proposal, decision, cancellation, current_time=FIXED_TIME)


class ActuatorSpy:
    """Counts handler invocations — proves zero side effects on BLOCK/timeout paths.

    Also records each call's proposal (matching INT-01's ``ActuatorSpy``,
    ``tests/integration/int-01/test_int01.py``) so this copy doesn't
    silently diverge from the pattern it's documented as following.
    """

    def __init__(self, target_handler: Any) -> None:
        self.target_handler = target_handler
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    def __call__(self, proposal: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        self.calls.append(proposal)
        return self.target_handler(proposal)


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------


@dataclass
class TimeoutProbeResult:
    error_code: str
    execution_allowed: bool
    retryable: bool
    elapsed_ms: float
    configured_timeout_seconds: float
    handler_call_count: int
    turn_status: str | None = None


class LocalPerfHarness:
    """Owns the mock guardrail HTTP server and wires one Agent/Vehicle stack.

    All network traffic is loopback HTTP to the in-process mock server
    started here — no third-party calls happen anywhere in this class.
    """

    def __init__(self) -> None:
        self.server = create_server()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        try:
            # Load before starting the server thread: if this raises (real
            # file I/O — a missing/locked/malformed catalog or registry
            # file), there is no live serve_forever() thread left dangling
            # with nothing able to join() it (unittest's tearDown never
            # runs when setUp doesn't complete).
            self.mapper = load_default_mapper(load_registry(), load_manifest())
        except Exception:
            self.server.server_close()
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def __enter__(self) -> "LocalPerfHarness":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- fresh per-iteration wiring -------------------------------------

    def new_client(self, timeout_seconds: float = 2.0) -> GuardrailClientAdapter:
        return GuardrailClientAdapter(
            GuardrailClientConfig(
                base_url=self.base_url,
                provider=GuardrailProvider.REAL,
                timeout_seconds=timeout_seconds,
                read_only_retries=1,
                retry_backoff_seconds=0.01,
            )
        )

    def new_gateway(self) -> tuple[VehicleToolGateway, ActuatorSpy]:
        spy = ActuatorSpy(make_open_door_handler(VehicleStateMachine()))
        gateway = VehicleToolGateway()
        gateway.registry.register("open_door", spy)
        gateway.registry.register("control_access", spy)
        return gateway, spy

    def new_orchestrator(
        self, client: GuardrailClientAdapter, gateway: VehicleToolGateway, outcome: str = "allow"
    ) -> AgentOrchestrator:
        return AgentOrchestrator(
            model_router=MockModelRouter(outcome),
            mapper=self.mapper,
            guardrail=client,
            executor=FixedClockExecutor(gateway),
            # Same uuid4().hex id-generation cost as production's own default
            # id_factory (orchestrator.py) — only the outcome tag is added,
            # which the mock server's fixture router requires (see
            # mock_server.py's "block"/"confirm"/"answer" substring match).
            # Using a cheaper generator here would measure e2e turn latency
            # against a synthetically faster ID step than production pays.
            id_factory=lambda prefix: f"prop-{outcome}-{prefix}-{uuid.uuid4().hex}",
        )

    # -- Pass A: guardrail round-trip only -------------------------------

    def measure_guardrail_round_trip(self, iterations: int) -> list[float]:
        client = self.new_client()
        samples: list[float] = []
        for i in range(iterations):
            proposal = copy.deepcopy(EXAMPLES["action_proposal"])
            proposal["proposal_id"] = f"perf-rt-{i}"
            start = time.perf_counter()
            result = client.evaluate(proposal)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            assert result["outcome"] == "ALLOW"
            samples.append(elapsed_ms)
        return samples

    # -- Pass B: permit verification + handler latency --------------------

    def measure_permit_and_handler(self, iterations: int) -> list[float]:
        client = self.new_client()
        gateway, spy = self.new_gateway()
        samples: list[float] = []
        for i in range(iterations):
            proposal = copy.deepcopy(EXAMPLES["action_proposal"])
            proposal["proposal_id"] = f"perf-permit-{i}"
            decision = client.evaluate(proposal)
            assert decision["outcome"] == "ALLOW"
            # The mock guardrail's ALLOW fixture always mints the same
            # permit_id (see AGENT_PERFORMANCE_REPORT.md methodology note),
            # so the store must be cleared between iterations to measure
            # fresh permit-verification + handler latency each time instead
            # of a short-circuited ReplayAttackError after iteration 1.
            gateway.store.clear()
            start = time.perf_counter()
            execution = gateway.execute(proposal, decision, None, current_time=FIXED_TIME)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            assert execution.success, execution.to_dict()
            samples.append(elapsed_ms)
        assert spy.call_count == iterations
        return samples

    # -- Pass C: end-to-end Agent turn latency -----------------------------

    def measure_e2e_turn(self, iterations: int, outcome: str = "allow") -> list[float]:
        client = self.new_client()
        gateway, spy = self.new_gateway()
        orchestrator = self.new_orchestrator(client, gateway, outcome)
        samples: list[float] = []
        for i in range(iterations):
            if outcome == "allow":
                gateway.store.clear()
            request = TurnRequest(
                session_id=f"perf-session-{outcome}",
                turn_id=f"perf-turn-{outcome}-{i}",
                request_id=f"perf-req-{outcome}-{i}",
                message="Mở cửa xe ghế lái",
            )
            start = time.perf_counter()
            result = orchestrator.handle_message(request)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if outcome == "allow":
                assert result.status == TurnStatus.COMPLETED, result
            samples.append(elapsed_ms)
        return samples

    # -- Pass D: memory growth over repeated turns -------------------------

    def measure_memory_growth(self, iterations: int, checkpoint_every: int = 50) -> dict[str, Any]:
        if checkpoint_every < 1:
            raise ValueError(f"checkpoint_every must be >= 1, got {checkpoint_every}")
        client = self.new_client()
        gateway, spy = self.new_gateway()
        orchestrator = self.new_orchestrator(client, gateway, "allow")

        gc.collect()
        tracemalloc.start()
        checkpoints: list[dict[str, Any]] = []
        try:
            for i in range(1, iterations + 1):
                gateway.store.clear()
                request = TurnRequest(
                    session_id="perf-session-memory",
                    turn_id=f"perf-mem-turn-{i}",
                    request_id=f"perf-mem-req-{i}",
                    message="Mở cửa xe ghế lái",
                )
                result = orchestrator.handle_message(request)
                assert result.status == TurnStatus.COMPLETED, result
                if i % checkpoint_every == 0 or i == iterations:
                    gc.collect()
                    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
                    checkpoints.append(
                        {
                            "iteration": i,
                            "traced_current_kb": round(current_bytes / 1024, 1),
                            "traced_peak_kb": round(peak_bytes / 1024, 1),
                        }
                    )
        finally:
            tracemalloc.stop()

        first_kb = checkpoints[0]["traced_current_kb"] if checkpoints else 0.0
        last_kb = checkpoints[-1]["traced_current_kb"] if checkpoints else 0.0
        growth_kb = last_kb - first_kb
        measured_turns = (checkpoints[-1]["iteration"] - checkpoints[0]["iteration"]) if len(checkpoints) >= 2 else 0
        growth_per_1000_turns_kb = (growth_kb / measured_turns) * 1000 if measured_turns > 0 else 0.0
        return {
            "iterations": iterations,
            "checkpoint_every": checkpoint_every,
            "checkpoints": checkpoints,
            "growth_kb_first_to_last_checkpoint": round(growth_kb, 1),
            "growth_kb_per_1000_turns": round(growth_per_1000_turns_kb, 1),
            "handler_call_count": spy.call_count,
        }

    # -- Pass E: timeout fail-closed behavior ------------------------------

    def measure_guardrail_client_timeout(self, timeout_seconds: float = 0.2) -> TimeoutProbeResult:
        """Direct client-level timeout: unreachable port, single attempt, fail closed."""
        client = GuardrailClientAdapter(
            GuardrailClientConfig(
                base_url="http://127.0.0.1:1",  # reserved/unreachable port
                provider=GuardrailProvider.REAL,
                timeout_seconds=timeout_seconds,
                read_only_retries=1,
                retry_backoff_seconds=0.01,
            )
        )
        proposal = copy.deepcopy(EXAMPLES["action_proposal"])
        start = time.perf_counter()
        try:
            client.evaluate(proposal)
            raise AssertionError("expected GuardrailAdapterError on unreachable guardrail")
        except GuardrailAdapterError as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return TimeoutProbeResult(
                error_code=exc.code,
                execution_allowed=exc.execution_allowed,
                retryable=exc.retryable,
                elapsed_ms=round(elapsed_ms, 1),
                configured_timeout_seconds=timeout_seconds,
                handler_call_count=0,
            )

    def measure_turn_timeout_zero_side_effects(self, timeout_seconds: float = 0.2) -> TimeoutProbeResult:
        """Full-turn timeout: unreachable guardrail wired into the real Orchestrator.

        Proves the acceptance criterion directly: the turn completes in
        bounded time (no infinite hang) and the actuator handler is called
        zero times (no side effect) when Guardrail is unreachable.
        """
        client = GuardrailClientAdapter(
            GuardrailClientConfig(
                base_url="http://127.0.0.1:1",
                provider=GuardrailProvider.REAL,
                timeout_seconds=timeout_seconds,
                read_only_retries=1,
                retry_backoff_seconds=0.01,
            )
        )
        gateway, spy = self.new_gateway()
        orchestrator = self.new_orchestrator(client, gateway, "allow")
        request = TurnRequest(
            session_id="perf-session-timeout",
            turn_id="perf-turn-timeout-001",
            request_id="perf-req-timeout-001",
            message="Mở cửa xe ghế lái",
        )
        start = time.perf_counter()
        result = orchestrator.handle_message(request, CancellationToken())
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return TimeoutProbeResult(
            error_code=result.error.code if result.error else "NONE",
            execution_allowed=False,
            retryable=result.error.retryable if result.error else False,
            elapsed_ms=round(elapsed_ms, 1),
            configured_timeout_seconds=timeout_seconds,
            handler_call_count=spy.call_count,
            turn_status=result.status.value,
        )
