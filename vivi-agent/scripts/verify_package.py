"""Verify that the portable ViVi Agent package is internally complete."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
REQUIRED_FILES = (
    "README.md",
    "pyproject.toml",
    ".env.example",
    "docs/ARCHITECTURE.md",
    "docs/INTEGRATION.md",
    "docs/OPERATIONS.md",
    "docs/PACKAGE_REPORT.md",
    "docs/AI_CONTEXT.md",
    "src/vivi_agent/catalog/intent_manifest.v1.json",
    "src/vivi_agent/tools/registry/domain_tools.v1.json",
)


def verify_package() -> dict[str, int | bool]:
    """Return package metrics, raising when a portability invariant fails."""

    missing = [item for item in REQUIRED_FILES if not (PACKAGE_ROOT / item).is_file()]
    if missing:
        raise RuntimeError(f"Missing required package files: {missing}")

    sys.path.insert(0, str(SRC_ROOT))
    from vivi_agent.behaviors.catalog import ACTION_BEHAVIOR_CONFIGS
    from vivi_agent.behaviors.refusal import REFUSAL_CATALOG
    from vivi_agent.catalog import load_manifest
    from vivi_agent.coverage import assert_agent_readiness
    from vivi_agent.queries.registry import QUERY_RESPONDER_REGISTRY
    from vivi_agent.tools.mapping import DEFAULT_MAPPING_RULES
    from vivi_agent.tools.registry import load_registry

    manifest = load_manifest()
    report = assert_agent_readiness(manifest=manifest)
    metrics: dict[str, int | bool] = {
        "passed": report.passed,
        "intents": len(manifest.intents),
        "tools": len(load_registry().tools),
        "mappings": len(DEFAULT_MAPPING_RULES),
        "action_handlers": len(ACTION_BEHAVIOR_CONFIGS),
        "query_handlers": len(QUERY_RESPONDER_REGISTRY.registered_intents()),
        "refusal_handlers": len(REFUSAL_CATALOG),
    }
    expected = {
        "intents": 123,
        "tools": 11,
        "mappings": 148,
        "action_handlers": 112,
        "query_handlers": 10,
        "refusal_handlers": 1,
    }
    drift = {key: (metrics[key], value) for key, value in expected.items() if metrics[key] != value}
    if drift:
        raise RuntimeError(f"Frozen package inventory drifted: {drift}")
    return metrics


if __name__ == "__main__":
    print(json.dumps(verify_package(), ensure_ascii=False, indent=2))
