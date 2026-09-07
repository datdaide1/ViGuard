"""Phase 2' — conformance of the copied tool->intent table against the Agent's.

P2-D1: the Guardrail maps ``(tool, action, target, value) -> intent`` with the
*same* table the Agent uses, but D1 forbids importing Agent code in production,
so the table is copied into ``vf_guardrails/service/tool_map.py``. This test is
the drift alarm: it imports the Agent's real ``DEFAULT_MAPPING_RULES`` and
compares row-by-row. If the Agent's table changes and ours does not (or vice
versa), this goes red.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_REPO = _ROOT.parent
sys.path.insert(0, str(_ROOT))

from policy import RuleSet  # noqa: E402
from service.tool_map import (  # noqa: E402
    DEFAULT_MAPPING_RULES,
    DEFAULT_MAPPER,
    ToolMapper,
    ToolMapReadinessError,
    ToolMappingError,
)

_AGENT_SRC = _REPO / "vivi-agent" / "src"
_agent_rules = None
if _AGENT_SRC.is_dir():  # vivi-agent path set up by tests/conftest.py
    try:
        from vivi_agent.tools.mapping.mapper import (  # noqa: E402
            DEFAULT_MAPPING_RULES as _AGENT_DEFAULT_MAPPING_RULES,
        )

        _agent_rules = _AGENT_DEFAULT_MAPPING_RULES
    except Exception:  # pragma: no cover - agent package not resolvable here
        _agent_rules = None

_needs_agent = pytest.mark.skipif(
    _agent_rules is None, reason="vivi-agent package not importable in this environment"
)

_EXAMPLES = json.loads(
    (
        _REPO
        / "vivi-agent/src/vivi_agent/integrations/viguard/wire/examples.json"
    ).read_text(encoding="utf-8")
)


def _tuple(rule) -> tuple[str, str, str, str, str | None]:
    return (rule.tool_name, rule.action, rule.target, rule.intent, rule.value)


# ---------------------------------------------------------------- conformance
@_needs_agent
def test_copied_table_matches_agent_explicit_rows_exactly():
    agent_explicit = {
        _tuple(r) for r in _agent_rules if r.tool_name != "control_vehicle_capability"
    }
    ours = {_tuple(r) for r in DEFAULT_MAPPING_RULES}
    assert ours == agent_explicit, {
        "missing_from_ours": sorted(agent_explicit - ours),
        "extra_in_ours": sorted(ours - agent_explicit),
    }


@_needs_agent
def test_no_control_vehicle_capability_rows_are_in_scope():
    # The 69 candidate rows are Agent-only; none has a workbook policy.
    assert all(r.tool_name != "control_vehicle_capability" for r in DEFAULT_MAPPING_RULES)


def test_table_has_the_79_explicit_rows():
    assert len(DEFAULT_MAPPING_RULES) == 79


# ------------------------------------------------------------ workbook coverage
def test_every_workbook_intent_is_reachable():
    workbook = set(RuleSet.load().intents)
    mapped = DEFAULT_MAPPER.intents
    assert workbook - mapped == set(), sorted(workbook - mapped)


def test_turnon_lka_maps_but_has_no_workbook_rule():
    # Known gap carried over from the Agent table: the service will fail closed
    # (typed error) on this intent, never ALLOW. Documented, not silently fixed.
    assert "turnon_LKA" in DEFAULT_MAPPER.intents
    assert "turnon_LKA" not in RuleSet.load().intents


# --------------------------------------------------------------- resolve() API
def test_resolve_matches_the_sample_action_proposal():
    proposal = _EXAMPLES["action_proposal"]
    assert DEFAULT_MAPPER.resolve(proposal["tool"], proposal["arguments"]) == "open_door"


def test_resolve_uses_value_when_present():
    assert (
        DEFAULT_MAPPER.resolve("set_drive_mode", {"action": "set", "target": "drive_mode", "value": "eco"})
        == "switch_drivemode_eco"
    )
    assert (
        DEFAULT_MAPPER.resolve("set_drive_mode", {"action": "set", "target": "drive_mode", "value": "sport"})
        == "switch_drivemode_sport"
    )


def test_resolve_fails_closed_on_unknown_tuple():
    with pytest.raises(ToolMappingError) as exc:
        DEFAULT_MAPPER.resolve("control_access", {"action": "open", "target": "passenger_door"})
    assert exc.value.code == "UNSUPPORTED_TOOL_MAPPING"
    assert exc.value.execution_allowed is False


def test_resolve_fails_closed_on_incomplete_call():
    with pytest.raises(ToolMappingError) as exc:
        DEFAULT_MAPPER.resolve("control_access", {"action": "open"})
    assert exc.value.code == "INCOMPLETE_TOOL_CALL"


def test_resolve_rejects_wrong_value_for_valued_row():
    # `value` is part of the key: a mismatched value is not a mapping.
    with pytest.raises(ToolMappingError):
        DEFAULT_MAPPER.resolve(
            "set_drive_mode", {"action": "set", "target": "drive_mode", "value": "race"}
        )


# --------------------------------------------------------------- fail-closed load
def test_duplicate_key_is_rejected_at_construction():
    from service.tool_map import MappingRule

    dup = DEFAULT_MAPPING_RULES + (
        MappingRule("control_access", "open", "driver_door", "open_trunk"),
    )
    with pytest.raises(ToolMapReadinessError):
        ToolMapper(dup)
