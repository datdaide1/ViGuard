"""ViVi Agent package.

Importing the runtime package is the startup boundary for shared configuration.
The approved intent manifest is therefore loaded fail-closed here, before any
orchestrator, contract adapter, or vehicle executor can be imported through the
package.
"""

from .catalog import IntentManifest, load_manifest
from .tools.mapping import ToolMapper, load_default_mapper
from .tools.registry import ToolRegistry, load_registry

RUNTIME_INTENT_MANIFEST: IntentManifest = load_manifest()
RUNTIME_TOOL_REGISTRY: ToolRegistry = load_registry()
RUNTIME_TOOL_MAPPER: ToolMapper = load_default_mapper(
    RUNTIME_TOOL_REGISTRY, RUNTIME_INTENT_MANIFEST
)

__all__ = ["RUNTIME_INTENT_MANIFEST", "RUNTIME_TOOL_MAPPER", "RUNTIME_TOOL_REGISTRY"]
