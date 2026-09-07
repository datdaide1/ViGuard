"""Latency benchmark for the Guardrail pipeline (PRD §15 targets).

Measures, on the frozen test set utterances, warm:
  - IntentResolver (T2 TF-IDF) alone
  - PolicyEngine alone (given the resolved intent + a default state)
  - full Guardrail.process round-trip

Usage:  py -3 vf_guardrails/evals/run_benchmark.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "vf_guardrails"))

from classifier import IntentResolver  # noqa: E402
from guardrail import Guardrail  # noqa: E402
from policy import PolicyEngine, RuleSet, VehicleState  # noqa: E402

_FROZEN = _REPO / "vf_guardrails/evals/data/frozen_testset.jsonl"


def _p(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))]


def _bench(label: str, fn, inputs, target: str) -> None:
    for x in inputs[:50]:  # warm
        fn(x)
    ts = []
    for x in inputs:
        t0 = time.perf_counter()
        fn(x)
        ts.append((time.perf_counter() - t0) * 1000.0)
    print(f"  {label:28s} p50 {_p(ts, .5):6.3f}  p95 {_p(ts, .95):6.3f}  "
          f"p99 {_p(ts, .99):6.3f}  mean {statistics.mean(ts):6.3f} ms   (target: {target})")


def main() -> int:
    utts = [json.loads(l)["utterance"] for l in _FROZEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    resolver = IntentResolver()
    engine = PolicyEngine(RuleSet.load())
    guard = Guardrail(resolver, engine)
    state = VehicleState(speed=0, gear="P")

    print(f"Guardrail latency — {len(utts)} frozen utterances, warm\n")
    _bench("IntentResolver (T2 TF-IDF)", resolver.resolve, utts, "T2 ≤20 ms p99")
    intents = [resolver.resolve(u).intent for u in utts]
    valid = [i for i in intents if i in engine.ruleset.intents]
    _bench("PolicyEngine (gate)", lambda i: engine.evaluate(i, state), valid, "gate ≤5 ms p99")
    _bench("Guardrail.process (e2e)", lambda u: guard.process(u, state), utts, "fast-path ≤25 ms p99")

    _bench_http()
    return 0


def _bench_http() -> None:
    """HTTP round-trip for the Phase 2' service endpoints (loopback, warm)."""
    import threading
    import urllib.request

    from service.http import create_server  # noqa: PLC0415

    srv = create_server(port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def _post(path: str, payload: dict) -> None:
        req = urllib.request.Request(
            base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=2).read()

    action = {
        "contract_version": "1.0.0", "proposal_id": "bench", "session_id": "bench",
        "source_turn_id": "bench", "tool": "control_access",
        "arguments": {"action": "open", "target": "driver_door"},
        "model_provider": "openai", "model_id": "gpt-5-mini",
    }
    monitor = {
        "contract_version": "1.0.0", "request_id": "bench-m",
        "active_action_id": "a", "intent": "activate_hda",
    }
    query = {
        "contract_version": "1.0.0", "request_id": "bench-q", "tool": "query_vehicle_state",
        "arguments": {"action": "get", "target": "current_speed"},
    }

    print("\nHTTP round-trip (stdlib http.server, loopback)\n")
    try:
        _bench("POST /v1/evaluate/action", lambda _: _post("/v1/evaluate/action", action),
               list(range(300)), "e2e ≤25 ms p99")
        _bench("POST /v1/evaluate/query", lambda _: _post("/v1/evaluate/query", query),
               list(range(300)), "read-only")
        _bench("POST /v1/monitor/evaluate", lambda _: _post("/v1/monitor/evaluate", monitor),
               list(range(300)), "monitor tick")
    finally:
        srv.shutdown()
        srv.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
