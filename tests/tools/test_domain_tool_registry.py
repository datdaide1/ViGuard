from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.vivi_agent import RUNTIME_TOOL_REGISTRY
from src.vivi_agent.catalog.manifest import ALLOWED_DOMAIN_TOOLS
from src.vivi_agent.tools.registry import (
    APPROVED_TOOL_NAMES,
    REGISTRY_PATH,
    ClarificationRequest,
    ToolCallValidationError,
    ValidatedToolCall,
    load_registry,
    registry_checksum,
)


class DomainToolRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(Path(REGISTRY_PATH).read_text(encoding="utf-8"))
        cls.registry = load_registry()

    def write_registry(self, raw: dict[str, object]) -> Path:
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False)
        with handle:
            json.dump(raw, handle, ensure_ascii=False)
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        return Path(handle.name)

    def resigned(self, raw: dict[str, object]) -> dict[str, object]:
        raw["checksum"] = registry_checksum(raw)
        return raw

    def test_checked_in_registry_is_versioned_and_loaded_at_startup(self) -> None:
        self.assertEqual(self.registry.registry_version, "1.0.0")
        self.assertEqual(self.registry.checksum, self.raw["checksum"])
        self.assertEqual(RUNTIME_TOOL_REGISTRY.checksum, self.registry.checksum)
        self.assertEqual(set(self.registry.names), ALLOWED_DOMAIN_TOOLS)
        self.assertEqual(set(self.registry.names), APPROVED_TOOL_NAMES)
        self.assertEqual(len(self.registry.names), 10)

    def test_model_sees_only_registered_closed_json_schemas(self) -> None:
        schemas = self.registry.model_tools()
        self.assertEqual({item["name"] for item in schemas}, set(self.registry.names))
        for schema in schemas:
            parameters = schema["parameters"]
            self.assertEqual(set(parameters), {"oneOf"})
            self.assertTrue(parameters["oneOf"])
            for variant in parameters["oneOf"]:
                self.assertFalse(variant["additionalProperties"])
                self.assertEqual(
                    set(variant["properties"]) - {"action", "target", "value"}, set()
                )
                self.assertIn("action", variant["required"])
                self.assertIn("target", variant["required"])
                self.assertTrue(variant["properties"]["action"]["const"])
                self.assertTrue(variant["properties"]["target"]["enum"])
            serialized = json.dumps(schema).lower()
            for forbidden in ("state", "outcome", "rule_id", "permit"):
                self.assertNotIn(f'"{forbidden}"', serialized)

    def test_schema_preserves_signature_combinations_without_cross_product(self) -> None:
        schemas = {item["name"]: item for item in self.registry.model_tools()}
        access_variants = schemas["control_access"]["parameters"]["oneOf"]
        lock_variant = next(
            item for item in access_variants if item["properties"]["action"]["const"] == "lock"
        )
        self.assertEqual(lock_variant["properties"]["target"]["enum"], ["all_doors"])
        self.assertNotIn("value", lock_variant["properties"])

        drive_variant = schemas["set_drive_mode"]["parameters"]["oneOf"][0]
        self.assertEqual(drive_variant["required"], ["action", "target", "value"])
        self.assertEqual(drive_variant["properties"]["value"]["enum"], ["eco", "normal", "sport"])

    def test_valid_arguments_are_immutable_and_ready_for_mapping(self) -> None:
        result = self.registry.validate_call(
            "control_access", {"action": "open", "target": "driver_door"}
        )
        self.assertIsInstance(result, ValidatedToolCall)
        self.assertEqual(dict(result.arguments), {"action": "open", "target": "driver_door"})
        with self.assertRaises(TypeError):
            result.arguments["target"] = "trunk"  # type: ignore[index]

        drive_mode = self.registry.validate_call(
            "set_drive_mode", {"action": "set", "target": "drive_mode", "value": "sport"}
        )
        self.assertIsInstance(drive_mode, ValidatedToolCall)

    def test_missing_parameters_return_structured_clarification(self) -> None:
        missing_action = self.registry.validate_call("control_access", {})
        self.assertIsInstance(missing_action, ClarificationRequest)
        self.assertEqual(missing_action.to_dict()["missing_parameters"], ["action"])

        missing_target = self.registry.validate_call("control_access", {"action": "open"})
        self.assertIsInstance(missing_target, ClarificationRequest)
        self.assertIn("driver_door", missing_target.allowed_values["target"])

        missing_value = self.registry.validate_call(
            "set_drive_mode", {"action": "set", "target": "drive_mode"}
        )
        self.assertIsInstance(missing_value, ClarificationRequest)
        self.assertEqual(missing_value.missing_parameters, ("value",))
        self.assertEqual(missing_value.allowed_values["value"], ("eco", "normal", "sport"))

    def test_unknown_tool_and_invalid_combinations_fail_before_guardrail(self) -> None:
        cases = (
            ("unknown_tool", {"action": "open", "target": "driver_door"}, "UNKNOWN_TOOL"),
            ("control_access", {"action": "launch", "target": "driver_door"}, "INVALID_ACTION"),
            ("control_access", {"action": "lock", "target": "trunk"}, "INVALID_TARGET"),
            ("set_drive_mode", {"action": "set", "target": "drive_mode", "value": "off_road"}, "INVALID_VALUE"),
            ("control_access", {"action": "open", "target": "trunk", "value": "now"}, "UNEXPECTED_VALUE"),
        )
        for name, arguments, code in cases:
            with self.subTest(code=code), self.assertRaises(ToolCallValidationError) as raised:
                self.registry.validate_call(name, arguments)
            self.assertEqual(raised.exception.code, code)

    def test_additional_and_guardrail_owned_fields_are_rejected(self) -> None:
        for field in ("state", "outcome", "rule", "rule_id", "permit"):
            arguments = {"action": "open", "target": "driver_door", field: "model-value"}
            with self.subTest(field=field), self.assertRaises(ToolCallValidationError) as raised:
                self.registry.validate_call("control_access", arguments)
            self.assertEqual(raised.exception.code, "FORBIDDEN_ARGUMENT")

        with self.assertRaises(ToolCallValidationError) as raised:
            self.registry.validate_call(
                "control_access", {"action": "open", "target": "driver_door", "reason": "please"}
            )
        self.assertEqual(raised.exception.code, "ADDITIONAL_PROPERTY")

    def test_checksum_tampering_and_registry_shape_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.raw)
        tampered["tools"][0]["description"] = "tampered"
        with self.assertRaises(ToolCallValidationError) as checksum_error:
            load_registry(self.write_registry(tampered))
        self.assertEqual(checksum_error.exception.code, "REGISTRY_CHECKSUM_MISMATCH")

        duplicate = copy.deepcopy(self.raw)
        duplicate["tools"].append(copy.deepcopy(duplicate["tools"][0]))
        with self.assertRaises(ToolCallValidationError) as duplicate_error:
            load_registry(self.write_registry(self.resigned(duplicate)))
        self.assertEqual(duplicate_error.exception.code, "INVALID_REGISTRY")

        missing = copy.deepcopy(self.raw)
        missing["tools"].pop()
        with self.assertRaises(ToolCallValidationError) as coverage_error:
            load_registry(self.write_registry(self.resigned(missing)))
        self.assertEqual(coverage_error.exception.code, "TOOL_COVERAGE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
