from __future__ import annotations

import unittest

from src.vivi_agent import RUNTIME_TOOL_MAPPER
from src.vivi_agent.catalog import load_manifest
from src.vivi_agent.tools.mapping import (
    MappingReadinessError,
    MappingRule,
    ToolMapper,
    UnsupportedToolMappingError,
)
from src.vivi_agent.tools.registry import load_registry


def proposal(arguments: dict[str, str] | None = None, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_version": "1.0.0",
        "proposal_id": "prop-001",
        "session_id": "session-001",
        "source_turn_id": "turn-001",
        "tool": "control_access",
        "arguments": arguments or {"action": "open", "target": "driver_door"},
        "model_provider": "openai",
        "model_id": "gpt-5-mini",
    }
    payload.update(overrides)
    return payload


class ToolMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mapper = ToolMapper(load_registry(), load_manifest())

    def test_runtime_loads_one_reviewed_vertical_slice_mapping(self) -> None:
        self.assertEqual(len(RUNTIME_TOOL_MAPPER.rules), 1)
        self.assertEqual(RUNTIME_TOOL_MAPPER.rules[0].intent, "open_door")

    def test_valid_call_maps_to_one_canonical_intent_and_event(self) -> None:
        result = self.mapper.map_proposal(proposal())
        self.assertEqual(result.canonical_action.intent, "open_door")
        self.assertEqual(result.canonical_action.behavior_id, "access_mutation")
        self.assertEqual(
            dict(result.canonical_action.normalized_arguments),
            {"action": "open", "target": "driver_door"},
        )
        self.assertEqual(result.event.source_tool, "control_access")
        self.assertEqual(result.event.canonical_intent, "open_door")
        self.assertEqual(result.event.proposal_digest, result.proposal_digest)
        with self.assertRaises(TypeError):
            result.canonical_action.normalized_arguments["target"] = "trunk"  # type: ignore[index]

    def test_canonical_proposal_has_stable_digest(self) -> None:
        first = self.mapper.map_proposal(
            proposal({"target": "driver_door", "action": "open"})
        )
        second = self.mapper.map_proposal(
            proposal(
                {"action": "open", "target": "driver_door"},
                model_provider="gemini",
                model_id="gemini-model",
            )
        )
        self.assertEqual(first.proposal_digest, second.proposal_digest)
        self.assertRegex(first.proposal_digest, r"^sha256:[0-9a-f]{64}$")

    def test_supported_registry_call_without_reviewed_mapping_does_not_fallback(self) -> None:
        with self.assertRaises(UnsupportedToolMappingError) as raised:
            self.mapper.map_proposal(proposal({"action": "open", "target": "trunk"}))
        self.assertEqual(raised.exception.code, "UNSUPPORTED_TOOL_MAPPING")
        self.assertFalse(raised.exception.execution_allowed)

    def test_invalid_and_incomplete_calls_are_blocked_before_mapping(self) -> None:
        cases = (
            (proposal({"action": "lock", "target": "driver_door"}), "INVALID_TARGET"),
            (proposal({"action": "open"}), "INCOMPLETE_TOOL_CALL"),
        )
        for payload, code in cases:
            with self.subTest(code=code), self.assertRaises(ValueError) as raised:
                self.mapper.map_proposal(payload)
            self.assertEqual(raised.exception.code, code)  # type: ignore[attr-defined]

    def test_malformed_proposal_identity_is_rejected_before_digest(self) -> None:
        cases = (
            ("proposal_id", 123),
            ("session_id", ""),
            ("source_turn_id", None),
        )
        for field, value in cases:
            with self.subTest(field=field), self.assertRaises(
                UnsupportedToolMappingError
            ) as raised:
                self.mapper.map_proposal(proposal(**{field: value}))
            self.assertEqual(raised.exception.code, "INVALID_ACTION_PROPOSAL")
            self.assertFalse(raised.exception.execution_allowed)

    def test_startup_validator_rejects_ambiguous_or_inconsistent_rules(self) -> None:
        valid = MappingRule("control_access", "open", "driver_door", "open_door")
        with self.assertRaises(MappingReadinessError) as duplicate:
            ToolMapper(load_registry(), load_manifest(), (valid, valid))
        self.assertEqual(duplicate.exception.code, "AMBIGUOUS_MAPPING")

        wrong_domain = MappingRule(
            "control_access", "open", "driver_door", "turnon_highbeam"
        )
        with self.assertRaises(MappingReadinessError) as mismatch:
            ToolMapper(load_registry(), load_manifest(), (wrong_domain,))
        self.assertEqual(mismatch.exception.code, "MAPPING_DOMAIN_MISMATCH")


if __name__ == "__main__":
    unittest.main()
