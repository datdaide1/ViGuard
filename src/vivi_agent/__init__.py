"""ViVi Agent package.

Importing the runtime package is the startup boundary for shared configuration.
The approved intent manifest is therefore loaded fail-closed here, before any
orchestrator, contract adapter, or vehicle executor can be imported through the
package.

Tests and CLIs that need to exercise the agent against an alternative
manifest/registry (e.g. a fixture catalog) should call :func:`build_runtime`
to obtain an isolated set of singletons, instead of monkeypatching the
``RUNTIME_*`` module globals below. ``build_runtime`` also honors the
``VIVI_AGENT_INTENT_MANIFEST_PATH`` / ``VIVI_AGENT_TOOL_REGISTRY_PATH``
environment variables so a deployment can point at a different catalog
without code changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

from .catalog import IntentManifest, load_manifest
from .catalog.manifest import MANIFEST_PATH
from .tools.mapping import ToolMapper, load_default_mapper
from .tools.registry import ToolRegistry, load_registry
from .tools.registry.registry import REGISTRY_PATH

_MANIFEST_PATH_ENV = "VIVI_AGENT_INTENT_MANIFEST_PATH"
_REGISTRY_PATH_ENV = "VIVI_AGENT_TOOL_REGISTRY_PATH"


class Runtime(NamedTuple):
    """An isolated (manifest, registry, mapper) triple."""

    intent_manifest: IntentManifest
    tool_registry: ToolRegistry
    tool_mapper: ToolMapper


def build_runtime(
    *,
    manifest_path: Path | str | None = None,
    registry_path: Path | str | None = None,
) -> Runtime:
    """Load and validate a fail-closed (manifest, registry, mapper) triple.

    Resolution order for each path is: the explicit argument, then the
    corresponding environment variable, then the packaged default. This is
    the supported seam for swapping in alternative manifests/registries —
    prefer it over monkeypatching ``RUNTIME_INTENT_MANIFEST`` and friends.
    """
    resolved_manifest_path = (
        manifest_path or os.environ.get(_MANIFEST_PATH_ENV) or MANIFEST_PATH
    )
    resolved_registry_path = (
        registry_path or os.environ.get(_REGISTRY_PATH_ENV) or REGISTRY_PATH
    )

    manifest = load_manifest(resolved_manifest_path)
    registry = load_registry(resolved_registry_path)
    mapper = load_default_mapper(registry, manifest)
    return Runtime(intent_manifest=manifest, tool_registry=registry, tool_mapper=mapper)


_runtime = build_runtime()

RUNTIME_INTENT_MANIFEST: IntentManifest = _runtime.intent_manifest
RUNTIME_TOOL_REGISTRY: ToolRegistry = _runtime.tool_registry
RUNTIME_TOOL_MAPPER: ToolMapper = _runtime.tool_mapper

__all__ = [
    "RUNTIME_INTENT_MANIFEST",
    "RUNTIME_TOOL_MAPPER",
    "RUNTIME_TOOL_REGISTRY",
    "Runtime",
    "build_runtime",
]
