#!/usr/bin/env python3
"""PERF-01 — full-size local benchmark run.

Produces the actual measured numbers behind AGENT_PERFORMANCE_REPORT.md.
Kept as a manual script rather than part of the pytest suite — same
convention as EVAL-01's run_live_eval.py — so a deliberately larger sample
size is a visible, chosen action rather than something `pytest` runs by
default on every CI invocation. Unlike run_live_eval.py, this script makes
zero third-party network calls: all traffic is loopback HTTP to the
in-process mock guardrail server (see benchmark.py's module docstring for
what is and is not measured here).

Usage (from repo root)::

    py -3 tests/performance/perf-01/run_benchmark.py --out tests/performance/perf-01/results/local_run.json
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark import LocalPerfHarness, summarize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guardrail-rt-n", type=int, default=300)
    parser.add_argument("--permit-handler-n", type=int, default=300)
    parser.add_argument("--e2e-allow-n", type=int, default=300)
    parser.add_argument("--e2e-block-n", type=int, default=100)
    parser.add_argument("--memory-n", type=int, default=500)
    parser.add_argument("--memory-checkpoint-every", type=int, default=50)
    parser.add_argument("--timeout-probe-seconds", type=float, default=0.2)
    parser.add_argument("--out", required=True, help="Path to write raw JSON results")
    args = parser.parse_args()

    started_at = time.time()
    harness = LocalPerfHarness()
    try:
        print(f"[1/6] guardrail round-trip x{args.guardrail_rt_n}", file=sys.stderr)
        guardrail_rt = harness.measure_guardrail_round_trip(args.guardrail_rt_n)

        print(f"[2/6] permit verification + handler x{args.permit_handler_n}", file=sys.stderr)
        permit_handler = harness.measure_permit_and_handler(args.permit_handler_n)

        print(f"[3/6] end-to-end turn latency (ALLOW) x{args.e2e_allow_n}", file=sys.stderr)
        e2e_allow = harness.measure_e2e_turn(args.e2e_allow_n, outcome="allow")

        print(f"[4/6] end-to-end turn latency (BLOCK) x{args.e2e_block_n}", file=sys.stderr)
        e2e_block = harness.measure_e2e_turn(args.e2e_block_n, outcome="block")

        print(f"[5/6] memory growth over {args.memory_n} repeated turns", file=sys.stderr)
        memory = harness.measure_memory_growth(args.memory_n, checkpoint_every=args.memory_checkpoint_every)

        print("[6/6] timeout fail-closed probes", file=sys.stderr)
        client_timeout = harness.measure_guardrail_client_timeout(args.timeout_probe_seconds)
        turn_timeout = harness.measure_turn_timeout_zero_side_effects(args.timeout_probe_seconds)
    finally:
        harness.close()

    elapsed_s = time.time() - started_at

    result_payload = {
        "meta": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "network_environment": "loopback (127.0.0.1) to in-process mock guardrail HTTP server — no third-party network calls",
            "model_provider": "none — deterministic in-process MockModelRouter (see benchmark.py docstring); model warm-up / tool-selection latency NOT measured in this run",
            "total_wall_clock_seconds": round(elapsed_s, 1),
        },
        "guardrail_round_trip_ms": summarize(guardrail_rt).to_dict(),
        "permit_verification_and_handler_ms": summarize(permit_handler).to_dict(),
        "e2e_turn_latency_allow_ms": summarize(e2e_allow).to_dict(),
        "e2e_turn_latency_block_ms": summarize(e2e_block).to_dict(),
        "memory_growth": memory,
        "timeout_behavior": {
            "guardrail_client_direct": {
                "error_code": client_timeout.error_code,
                "execution_allowed": client_timeout.execution_allowed,
                "retryable": client_timeout.retryable,
                "elapsed_ms": client_timeout.elapsed_ms,
                "configured_timeout_seconds": client_timeout.configured_timeout_seconds,
                "handler_call_count": client_timeout.handler_call_count,
            },
            "full_turn_via_orchestrator": {
                "error_code": turn_timeout.error_code,
                "turn_status": turn_timeout.turn_status,
                "elapsed_ms": turn_timeout.elapsed_ms,
                "configured_timeout_seconds": turn_timeout.configured_timeout_seconds,
                "handler_call_count": turn_timeout.handler_call_count,
            },
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote results to {out_path}", file=sys.stderr)
    print(json.dumps(result_payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
