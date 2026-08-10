from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("p1_cache_benchmark", Path(__file__).with_name("benchmark.py"))
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
run = _MODULE.run


def test_benchmark_reports_both_provider_paths_without_network_calls():
    result = run(iterations=2)

    assert result["iterations"] == 2
    assert set(result["providers"]) == {"openai", "gemini"}
    for measurements in result["providers"].values():
        assert measurements["rebuild_adapter_and_schema"]["iterations"] == 2
        assert measurements["cached_adapter_and_schema_clone"]["iterations"] == 2
        assert measurements["speedup"] > 0


def test_benchmark_rejects_non_positive_iterations():
    with pytest.raises(ValueError, match="positive"):
        run(iterations=0)
