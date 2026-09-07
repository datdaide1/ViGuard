"""Offline P1-CACHE microbenchmark for immutable model configuration reuse.

The benchmark performs no provider or Guardrail network calls. It compares the
previous per-call behavior (build an adapter and its tool schema) with the new
router/adapter cache while still cloning request payload schemas defensively.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from vehicle_agent import RUNTIME_TOOL_REGISTRY
from vehicle_agent.model_providers import GeminiAdapter, OpenAIAdapter


def _unused_transport(payload: Mapping[str, Any], timeout_seconds: float) -> dict[str, Any]:
    if payload.get("model") == "benchmark-openai":
        return {"choices": [{"message": {"content": "Cần làm rõ."}}]}
    return {"candidates": [{"content": {"parts": [{"text": "Cần làm rõ."}]}}]}


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
        "scope": "offline public adapter proposal path with deterministic in-process transport",
        "iterations": iterations,
        "providers": {},
    }
    for provider in ("openai", "gemini"):
        adapter_type = OpenAIAdapter if provider == "openai" else GeminiAdapter

        def new_adapter():
            return adapter_type(
                model_id=f"benchmark-{provider}",
                api_key="benchmark-only",
                registry=RUNTIME_TOOL_REGISTRY,
                transport=_unused_transport,
                config_checksum="sha256:benchmark",
            )

        cached_adapter = new_adapter()

        baseline = _measure(
            lambda: new_adapter().propose_tool(messages),
            iterations,
        )
        cached = _measure(lambda: cached_adapter.propose_tool(messages), iterations)
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
