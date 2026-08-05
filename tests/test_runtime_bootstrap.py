"""Tests for the vivi_agent package bootstrap seam (build_runtime).

Covers the Sourcery review request on `src/vivi_agent/__init__.py`: tests and
CLIs should be able to obtain an isolated (manifest, registry, mapper) triple
without monkeypatching the module-level RUNTIME_* singletons.
"""

from __future__ import annotations

import vivi_agent
from vivi_agent import Runtime, build_runtime
from vivi_agent.catalog.manifest import MANIFEST_PATH
from vivi_agent.tools.registry.registry import REGISTRY_PATH


def test_build_runtime_returns_isolated_triple():
    runtime = build_runtime()

    assert isinstance(runtime, Runtime)
    # Isolated objects, not the module-level singletons...
    assert runtime.intent_manifest is not vivi_agent.RUNTIME_INTENT_MANIFEST
    assert runtime.tool_registry is not vivi_agent.RUNTIME_TOOL_REGISTRY
    # ...but built from the same packaged catalog by default.
    assert runtime.intent_manifest.checksum == vivi_agent.RUNTIME_INTENT_MANIFEST.checksum
    assert runtime.tool_registry.checksum == vivi_agent.RUNTIME_TOOL_REGISTRY.checksum


def test_build_runtime_accepts_explicit_path_overrides():
    runtime = build_runtime(manifest_path=MANIFEST_PATH, registry_path=REGISTRY_PATH)

    assert runtime.intent_manifest.checksum == vivi_agent.RUNTIME_INTENT_MANIFEST.checksum
    assert runtime.tool_registry.checksum == vivi_agent.RUNTIME_TOOL_REGISTRY.checksum


def test_build_runtime_honors_environment_variable_overrides(monkeypatch):
    monkeypatch.setenv("VIVI_AGENT_INTENT_MANIFEST_PATH", str(MANIFEST_PATH))
    monkeypatch.setenv("VIVI_AGENT_TOOL_REGISTRY_PATH", str(REGISTRY_PATH))

    runtime = build_runtime()

    assert runtime.intent_manifest.checksum == vivi_agent.RUNTIME_INTENT_MANIFEST.checksum
    assert runtime.tool_registry.checksum == vivi_agent.RUNTIME_TOOL_REGISTRY.checksum


def test_build_runtime_explicit_argument_wins_over_environment_variable(monkeypatch, tmp_path):
    bogus_path = tmp_path / "does_not_exist.json"
    monkeypatch.setenv("VIVI_AGENT_INTENT_MANIFEST_PATH", str(bogus_path))

    # Explicit argument must take precedence over the environment variable,
    # so a broken/irrelevant env var can't shadow a caller's explicit choice.
    runtime = build_runtime(manifest_path=MANIFEST_PATH)

    assert runtime.intent_manifest.checksum == vivi_agent.RUNTIME_INTENT_MANIFEST.checksum
