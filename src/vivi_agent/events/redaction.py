"""Redaction utilities for sanitizing public Agent UI payloads."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any

# Forbidden key markers aligned with Agent UI v1 contract
_FORBIDDEN_KEY_MARKERS = frozenset(
    {
        "authorization",
        "apikey",
        "xapikey",
        "accesstoken",
        "refreshtoken",
        "secret",
        "clientsecret",
        "password",
        "systemprompt",
        "developerprompt",
        "hiddenreasoning",
        "chainofthought",
        "providerthought",
        "permit",
        "permitid",
        "internaltrace",
        "guardrailtrace",
        "rawtrace",
    }
)


def is_forbidden_key(raw_key: str) -> bool:
    """Check if a dictionary key matches any forbidden marker."""
    normalized_key = re.sub(r"[^a-z0-9]", "", str(raw_key).lower())
    return any(marker in normalized_key for marker in _FORBIDDEN_KEY_MARKERS)


def redact_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy of payload with all private and forbidden fields removed.
    
    Ensures the resulting event dict is safe for public emission and passes
    validate_public_payload without PRIVATE_FIELD_EXPOSED errors.
    """
    return _redact_value(copy.deepcopy(dict(payload)))


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            if is_forbidden_key(str(k)):
                continue
            sanitized[k] = _redact_value(v)
        return sanitized
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact_value(item) for item in value]
    return value
