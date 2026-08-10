"""Offline P1-CACHE microbenchmark for immutable model configuration reuse.

The benchmark performs no provider or Guardrail network calls. It compares the
previous per-call behavior (build an adapter and its tool schema) with the new
router/adapter cache while still cloning request payload schemas defensively.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from vivi_agent import RUNTIME_TOOL_REGISTRY
from vivi_agent.model_providers import ModelProviderConfig, ModelProviderRouter


def _unused_transport(payload: object, timeout_seconds: float) -> dict[str, Any]:
    raise AssertionError("P1-CACHE benchmark must not invoke a provider transport")


def _measure(operation: Callable[[], object], iterations: int) -> dict[str, float | int]:
    started = time.perf_counter()
    for _ in range(iterations):
        operation()
    elapsed = time.perf_counter() - started
    return {
        "iterations": iterations,
        "total_ms": round(elapsed * 1_000, 3),
        "us_per_call": round(elapsed * 1_000_000 / iterations, 3),
    }


def run(iterations: int = 2_000) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    messages = [{"role": "user", "content": "Mở cửa ghế lái"}]
    results: dict[str, Any] = {
        "scope": "offline adapter construction and immutable tool-schema payload generation",
        "iterations": iterations,
        "providers": {},
    }
    for provider in ("openai", "gemini"):
        config = ModelProviderConfig(
            provider=provider,
            openai_api_key="benchmark-only" if provider == "openai" else "",
            gemini_api_key="benchmark-only" if provider == "gemini" else "",
        )
        router = ModelProviderRouter(config, RUNTIME_TOOL_REGISTRY, {provider: _unused_transport})
        cached_adapter = router._adapter(provider)

        baseline = _measure(
            lambda: router._build_adapter(provider)._proposal_payload(messages),
            iterations,
        )
        cached = _measure(lambda: cached_adapter._proposal_payload(messages), iterations)
        baseline_us = float(baseline["us_per_call"])
        cached_us = float(cached["us_per_call"])
        results["providers"][provider] = {
            "rebuild_adapter_and_schema": baseline,
            "cached_adapter_and_schema_clone": cached,
            "speedup": round(baseline_us / cached_us, 3) if cached_us else None,
        }
    return results


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
