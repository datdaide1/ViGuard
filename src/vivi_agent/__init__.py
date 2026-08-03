"""ViVi Agent package.

Importing the runtime package is the startup boundary for shared configuration.
The approved intent manifest is therefore loaded fail-closed here, before any
orchestrator, contract adapter, or vehicle executor can be imported through the
package.
"""

from .catalog import IntentManifest, load_manifest

RUNTIME_INTENT_MANIFEST: IntentManifest = load_manifest()

__all__ = ["RUNTIME_INTENT_MANIFEST"]
