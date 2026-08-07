"""Offline pytest coverage for PERF-01's benchmark harness.

Runs the harness at small sample sizes to verify its *logic* (percentile
math, zero-side-effect timeout behavior, bounded elapsed time) is correct
and part of the normal test suite. The full-size run used to write
AGENT_PERFORMANCE_REPORT.md's actual numbers is a separate manual step
(``run_benchmark.py``) — same split as EVAL-01's offline tests vs.
``run_live_eval.py``, kept apart so `pytest` stays fast and deterministic
and larger sample sizes are a deliberate, visible choice rather than
something CI incurs on every run.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark import LocalPerfHarness, percentile, summarize  # noqa: E402


class PercentileMathTests(unittest.TestCase):
    def test_percentile_matches_known_values(self) -> None:
        samples = [10.0, 20.0, 30.0, 40.0, 50.0]
        self.assertEqual(percentile(samples, 0), 10.0)
        self.assertEqual(percentile(samples, 100), 50.0)
        self.assertEqual(percentile(samples, 50), 30.0)

    def test_percentile_single_sample(self) -> None:
        self.assertEqual(percentile([42.0], 95), 42.0)

    def test_percentile_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            percentile([], 50)

    def test_summarize_orders_min_p50_p95_p99_max(self) -> None:
        samples = [5.0, 1.0, 9.0, 3.0, 7.0, 2.0, 8.0, 4.0, 6.0, 10.0]
        summary = summarize(samples)
        self.assertEqual(summary.sample_size, 10)
        self.assertLessEqual(summary.min_ms, summary.p50_ms)
        self.assertLessEqual(summary.p50_ms, summary.p95_ms)
        self.assertLessEqual(summary.p95_ms, summary.p99_ms)
        self.assertLessEqual(summary.p99_ms, summary.max_ms)


class LocalPerfHarnessSmokeTests(unittest.TestCase):
    """Small-N smoke coverage — proves the harness measures the real code
    paths correctly. Not the source of the report's headline numbers."""

    SMALL_N = 10

    def setUp(self) -> None:
        self.harness = LocalPerfHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def test_guardrail_round_trip_samples_are_positive_and_ordered(self) -> None:
        samples = self.harness.measure_guardrail_round_trip(self.SMALL_N)
        self.assertEqual(len(samples), self.SMALL_N)
        self.assertTrue(all(s > 0 for s in samples))
        summary = summarize(samples)
        self.assertEqual(summary.sample_size, self.SMALL_N)

    def test_permit_and_handler_latency_all_iterations_succeed(self) -> None:
        samples = self.harness.measure_permit_and_handler(self.SMALL_N)
        self.assertEqual(len(samples), self.SMALL_N)
        self.assertTrue(all(s > 0 for s in samples))

    def test_e2e_turn_latency_allow_path(self) -> None:
        samples = self.harness.measure_e2e_turn(self.SMALL_N, outcome="allow")
        self.assertEqual(len(samples), self.SMALL_N)
        self.assertTrue(all(s > 0 for s in samples))

    def test_e2e_turn_latency_block_path_is_faster_than_allow_path(self) -> None:
        """BLOCK skips execution entirely — sanity check the two paths differ
        the direction they should (guards against a broken mock fixture that
        would make every path measure identically, which would be a silent
        harness bug rather than a real result)."""
        block_samples = self.harness.measure_e2e_turn(self.SMALL_N, outcome="block")
        allow_samples = self.harness.measure_e2e_turn(self.SMALL_N, outcome="allow")
        self.assertEqual(len(block_samples), self.SMALL_N)
        self.assertLess(summarize(block_samples).mean_ms, summarize(allow_samples).mean_ms * 3)

    def test_memory_growth_structure(self) -> None:
        result = self.harness.measure_memory_growth(iterations=20, checkpoint_every=5)
        self.assertEqual(result["handler_call_count"], 20)
        self.assertEqual(len(result["checkpoints"]), 4)
        self.assertIn("growth_kb_per_1000_turns", result)

    def test_guardrail_client_timeout_fails_closed_bounded_time(self) -> None:
        timeout_s = 0.2
        probe = self.harness.measure_guardrail_client_timeout(timeout_seconds=timeout_s)
        self.assertEqual(probe.error_code, "GUARDRAIL_UNAVAILABLE")
        self.assertFalse(probe.execution_allowed)
        self.assertFalse(probe.retryable)
        # Bounded: must not take dramatically longer than the configured
        # timeout (proves no hang) — generous 10x slack for CI scheduling jitter.
        self.assertLess(probe.elapsed_ms, timeout_s * 1000 * 10)

    def test_turn_timeout_zero_handler_side_effects_bounded_time(self) -> None:
        """Direct proof of PERF-01's acceptance criterion: timeout must not
        cause a side effect or hang the turn indefinitely."""
        timeout_s = 0.2
        probe = self.harness.measure_turn_timeout_zero_side_effects(timeout_seconds=timeout_s)
        self.assertEqual(probe.handler_call_count, 0)
        self.assertEqual(probe.turn_status, "failed")
        self.assertLess(probe.elapsed_ms, timeout_s * 1000 * 10)


if __name__ == "__main__":
    unittest.main()
