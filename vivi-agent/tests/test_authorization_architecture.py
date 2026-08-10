from __future__ import annotations

import ast
from pathlib import Path

from vivi_agent.authorization import ActionAuthorizer
from vivi_agent.integrations.viguard import ViGuardClient


CORE_ROOTS = (
    "confirmation",
    "model_providers",
    "orchestrator",
    "queries",
    "responses",
    "tools",
    "vehicle",
    "workflows",
)


def test_core_agent_does_not_import_viguard_or_legacy_guardrail_packages():
    root = Path(__file__).parents[1] / "src" / "vivi_agent"
    forbidden = ("integrations.viguard", "contracts.guardrail", "adapters.guardrail")
    findings = []
    for area in CORE_ROOTS:
        for path in (root / area).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(item in alias.name for item in forbidden):
                            findings.append(f"{path}:{alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if any(item in module for item in forbidden):
                        findings.append(f"{path}:{module}")
    assert findings == []


def test_viguard_client_structurally_implements_agent_authorizer_port():
    assert hasattr(ViGuardClient, "evaluate")
    assert hasattr(ActionAuthorizer, "evaluate")


def test_legacy_paths_are_thin_compatibility_shims_only():
    root = Path(__file__).parents[1] / "src" / "vivi_agent"
    paths = (
        root / "contracts" / "guardrail" / "v1" / "contract.py",
        root / "contracts" / "guardrail" / "v1" / "mock_server.py",
        root / "adapters" / "guardrail" / "client.py",
        root / "adapters" / "monitor" / "adapter.py",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) <= 4
        assert "compatibility import" in source
