"""Shape the ``answer={grounded, facts}`` block for ANSWER / UNKNOWN outcomes.

D2: the Guardrail returns **structured facts** read from the owned vehicle state;
the Agent verbalizes them into Vietnamese (it already has
``queries/state_queries.py`` + ``queries/knowledge.py`` for that). So the facts
here are deliberately minimal -- the canonical workbook field name and its value,
nothing pre-formatted.

  - state queries  -> ``{"<field>": <value>}``          (value is None when UNKNOWN)
  - explain_feature -> ``{"feature": <id>, "kb_has_feature": <bool>}``
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from policy import VehicleState

from .tool_map import EXPLAIN_FEATURE_TARGETS

# query intent -> the canonical VehicleState field it answers about
QUERY_FIELD: dict[str, str] = {
    "get_current_speed": "speed",
    "get_battery_pct": "battery_pct",
    "get_gear": "gear",
    "get_door_lock_status": "door_lock_state",
    "get_avh_status": "avh",
}


def kb_has_feature(arguments: Mapping[str, Any] | None) -> bool:
    """Does the workbook knowledge base cover the feature this proposal names?"""

    target = (arguments or {}).get("target")
    return isinstance(target, str) and target in EXPLAIN_FEATURE_TARGETS


def request_params_for(intent: str, arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extra ``request_params`` the engine needs for this intent, if any."""

    if intent == "explain_feature":
        return {"kb_has_feature": kb_has_feature(arguments)}
    return {}


def shape_answer(
    intent: str,
    outcome: str | None,
    state: VehicleState,
    arguments: Mapping[str, Any] | None,
    relevant_state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build the wire ``answer`` block, or None if the outcome carries no answer.

    ANSWER  -> ``{"grounded": true,  "facts": {...}}``
    UNKNOWN -> ``{"grounded": false, "facts": {...}}``  (facts show what was asked)
    """

    if outcome not in ("ANSWER", "UNKNOWN"):
        return None
    grounded = outcome == "ANSWER"

    if intent in QUERY_FIELD:
        field = QUERY_FIELD[intent]
        return {"grounded": grounded, "facts": {field: getattr(state, field, None)}}

    if intent == "explain_feature":
        target = (arguments or {}).get("target")
        return {
            "grounded": grounded,
            "facts": {"feature": target, "kb_has_feature": grounded},
        }

    # Any other ANSWER/UNKNOWN intent: fall back to the engine's relevant_state.
    return {"grounded": grounded, "facts": dict(relevant_state)}
