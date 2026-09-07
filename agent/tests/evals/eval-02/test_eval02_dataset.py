from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_EVAL02_DIR = Path(__file__).resolve().parents[3] / "evals" / "eval-02"
_SPEC = importlib.util.spec_from_file_location("aegis_eval02_dataset", _EVAL02_DIR / "dataset.py")
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
DATASET = _MODULE.DATASET

from vehicle_agent import RUNTIME_TOOL_MAPPER, RUNTIME_TOOL_REGISTRY  # noqa: E402
from vehicle_agent.catalog.candidate import CANDIDATE_INTENTS  # noqa: E402


def _proposal(item):
    return {
        "contract_version": "1.0.0",
        "proposal_id": f"proposal-{item.intent}",
        "session_id": "eval-02",
        "source_turn_id": item.item_id,
        "tool": item.tool,
        "arguments": dict(item.arguments),
        "model_provider": "eval",
        "model_id": "dataset-validator",
    }


def test_eval02_has_one_case_for_every_candidate_intent():
    assert len(DATASET) == 70
    assert {item.intent for item in DATASET} == CANDIDATE_INTENTS
    assert len({item.item_id for item in DATASET}) == 70


def test_eval02_expected_calls_validate_and_map_to_exact_intent():
    for item in DATASET:
        validated = RUNTIME_TOOL_REGISTRY.validate_call(item.tool, item.arguments)
        assert dict(validated.arguments) == dict(item.arguments)
        mapped = RUNTIME_TOOL_MAPPER.map_proposal(_proposal(item))
        assert mapped.canonical_action.intent == item.intent


def test_eval02_parameterized_cases_have_non_placeholder_values():
    for item in DATASET:
        if item.arguments["action"] == "set":
            assert item.arguments["value"]
            assert item.arguments["value"] != "*"
