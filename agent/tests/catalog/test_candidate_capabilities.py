from __future__ import annotations

import pytest

from vehicle_agent import RUNTIME_INTENT_MANIFEST, RUNTIME_TOOL_MAPPER, RUNTIME_TOOL_REGISTRY
from vehicle_agent.behaviors import ACTION_BEHAVIOR_CONFIGS
from vehicle_agent.catalog.candidate import (
    CANDIDATE_ACTION_INTENTS,
    CANDIDATE_CAPABILITIES,
    CANDIDATE_INTENTS,
    CANDIDATE_QUERY_INTENTS,
)
from vehicle_agent.queries import QUERY_RESPONDER_REGISTRY
from vehicle_agent.tools.registry import ToolCallValidationError


def test_excel_candidate_inventory_has_exact_complete_runtime_coverage():
    assert len(CANDIDATE_CAPABILITIES) == 70
    assert len(CANDIDATE_INTENTS) == 70
    manifest_ids = {item.intent for item in RUNTIME_INTENT_MANIFEST.intents}
    mapped_ids = {item.intent for item in RUNTIME_TOOL_MAPPER.rules}
    behavior_ids = {item.intent_id for item in ACTION_BEHAVIOR_CONFIGS}

    assert CANDIDATE_INTENTS <= manifest_ids
    assert CANDIDATE_INTENTS <= mapped_ids
    assert CANDIDATE_ACTION_INTENTS <= behavior_ids
    assert CANDIDATE_QUERY_INTENTS <= QUERY_RESPONDER_REGISTRY.registered_intents()


def test_parameterized_candidate_accepts_free_text_value_and_maps_exact_intent():
    call = RUNTIME_TOOL_REGISTRY.validate_call(
        "control_vehicle_capability",
        {"action": "set", "target": "set_navigation_destination", "value": "Hồ Gươm"},
    )
    assert call.arguments["value"] == "Hồ Gươm"

    proposal = {
        "contract_version": "1.0.0",
        "proposal_id": "proposal-candidate-1",
        "session_id": "session-candidate-1",
        "source_turn_id": "turn-candidate-1",
        "tool": "control_vehicle_capability",
        "arguments": dict(call.arguments),
        "model_provider": "gemini",
        "model_id": "gemini-test",
    }
    mapped = RUNTIME_TOOL_MAPPER.map_proposal(proposal)
    assert mapped.canonical_action.intent == "set_navigation_destination"
    assert mapped.canonical_action.normalized_arguments["value"] == "Hồ Gươm"


def test_candidate_catalog_contains_no_policy_metadata():
    for item in CANDIDATE_CAPABILITIES:
        assert not hasattr(item, "condition")
        assert not hasattr(item, "outcome")
        assert not hasattr(item, "rule_id")


def test_parameterized_candidate_rejects_oversized_free_text():
    with pytest.raises(ToolCallValidationError) as raised:
        RUNTIME_TOOL_REGISTRY.validate_call(
            "control_vehicle_capability",
            {"action": "set", "target": "set_navigation_destination", "value": "x" * 513},
        )
    assert raised.value.code == "INVALID_VALUE"


def test_candidate_tool_schema_exposes_vietnamese_capability_glossary():
    schema = RUNTIME_TOOL_REGISTRY.by_name("control_vehicle_capability").model_schema()
    assert "set_navigation_destination = Thiết lập điểm đến dẫn đường." in schema["description"]


def test_lka_activation_uses_the_existing_driver_assistance_domain_tool():
    call = RUNTIME_TOOL_REGISTRY.validate_call(
        "control_driver_assistance",
        {"action": "activate", "target": "lane_keeping_assist"},
    )
    assert call.arguments["action"] == "activate"
    rule = next(rule for rule in RUNTIME_TOOL_MAPPER.rules if rule.intent == "turnon_LKA")
    assert rule.tool_name == "control_driver_assistance"
