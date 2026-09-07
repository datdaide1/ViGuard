"""EVAL-01 — dataset validity tests.

``evals/eval-01`` is a plain script directory (not a Python package — its
own dashed name isn't a valid module identifier), so it is never imported as
``vehicle_agent...``; these tests add it to ``sys.path`` directly, mirroring
how ``run_live_eval.py`` does the same for the live entry point.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_EVAL01_DIR = Path(__file__).resolve().parents[3] / "evals" / "eval-01"
if str(_EVAL01_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL01_DIR))

from dataset import CATEGORIES, DATASET, build_dataset, split_for  # noqa: E402

from vehicle_agent.catalog.manifest import BASE_APPROVED_INTENTS  # noqa: E402


class Eval01DatasetTests(unittest.TestCase):
    def test_covers_all_53_real_manifest_intents_with_clear_and_paraphrase(self) -> None:
        manifest_intents = set(BASE_APPROVED_INTENTS)
        self.assertEqual(len(manifest_intents), 53)

        clear_intents = {item.intent for item in DATASET if item.category == "clear"}
        paraphrase_intents = {item.intent for item in DATASET if item.category == "paraphrase"}
        self.assertEqual(clear_intents, manifest_intents)
        self.assertEqual(paraphrase_intents, manifest_intents)

    def test_every_category_is_populated(self) -> None:
        present = {item.category for item in DATASET}
        self.assertEqual(present, set(CATEGORIES))
        for category in CATEGORIES:
            count = sum(1 for item in DATASET if item.category == category)
            self.assertGreater(count, 0, f"category {category!r} has no dataset items")

    def test_item_ids_are_unique(self) -> None:
        ids = [item.item_id for item in DATASET]
        self.assertEqual(len(ids), len(set(ids)))

    def test_held_out_split_is_present_and_roughly_20_percent(self) -> None:
        splits = {item.split for item in DATASET}
        self.assertEqual(splits, {"dev", "held_out"})
        held_out_fraction = sum(1 for item in DATASET if item.split == "held_out") / len(DATASET)
        self.assertGreater(held_out_fraction, 0.05)
        self.assertLess(held_out_fraction, 0.40)

    def test_split_is_deterministic_across_calls(self) -> None:
        for item in DATASET[:20]:
            self.assertEqual(split_for(item.item_id), item.split)
        # Rebuilding the dataset from scratch must assign identical splits —
        # a non-deterministic split would silently change which items count
        # as "held out" between runs, undermining the whole point of the split.
        rebuilt = build_dataset()
        rebuilt_by_id = {item.item_id: item.split for item in rebuilt}
        for item in DATASET:
            self.assertEqual(rebuilt_by_id[item.item_id], item.split)

    def test_clear_and_paraphrase_items_share_the_same_expected_tool_call(self) -> None:
        by_intent: dict[str, list] = {}
        for item in DATASET:
            if item.category in ("clear", "paraphrase"):
                by_intent.setdefault(item.intent, []).append(item)
        for intent, pair in by_intent.items():
            self.assertEqual(len(pair), 2, f"intent {intent!r} should have exactly clear+paraphrase")
            clear, paraphrase = sorted(pair, key=lambda i: i.category)
            self.assertEqual(clear.expected, paraphrase.expected)

    def test_ambiguous_and_negation_and_conditional_and_unknown_capability_expect_clarification(self) -> None:
        for category in ("ambiguous", "negation", "conditional", "unknown_capability"):
            for item in DATASET:
                if item.category == category:
                    self.assertEqual(item.expected.kind, "clarification", item.item_id)

    def test_multi_action_items_expect_any_of_two_options(self) -> None:
        for item in DATASET:
            if item.category == "multi_action":
                self.assertEqual(item.expected.kind, "tool_call_any_of")
                self.assertEqual(len(item.expected.any_of), 2)

    def test_prompt_injection_items_carry_a_forbidden_tool_call(self) -> None:
        for item in DATASET:
            if item.category == "prompt_injection":
                self.assertEqual(item.expected.kind, "injection_resist")
                self.assertIsNotNone(item.expected.forbidden)

    def test_all_utterances_are_non_empty_and_unique_within_category(self) -> None:
        by_category: dict[str, list[str]] = {}
        for item in DATASET:
            self.assertTrue(item.utterance.strip())
            by_category.setdefault(item.category, []).append(item.utterance)
        for category, utterances in by_category.items():
            self.assertEqual(
                len(utterances), len(set(utterances)), f"duplicate utterance within category {category!r}"
            )


if __name__ == "__main__":
    unittest.main()
