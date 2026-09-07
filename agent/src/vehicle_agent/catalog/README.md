# Aegis runtime intent catalog

`intent_manifest.v1.json` is the closed Agent-side inventory for the 53 policy
intents approved in `the policy workbook`. It contains routing and behavior
metadata only; Guardrail conditions and outcomes must never be copied here.

Importing `vehicle_agent` loads the manifest during application startup:

```python
from src.vehicle_agent import RUNTIME_INTENT_MANIFEST
```

`load_manifest()` raises `CatalogReadinessError` and sets `readiness=False` for
an unreadable file, checksum/version mismatch, missing/extra/duplicate intent,
query/action drift, refusal drift, or monitor-capability drift. Callers must
treat that exception as a failed readiness check and must not start execution.
The validator also rejects unknown domain tools and behavior categories that are
incompatible with the entry's action/query/refusal kind.

The checksum covers every root field except `checksum` itself using sorted-key,
compact UTF-8 JSON followed by SHA-256. Sample utterances are evaluation/UI
fixtures; they are not classifier training data or safety policy.
