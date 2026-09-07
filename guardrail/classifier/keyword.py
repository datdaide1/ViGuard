"""T1 — keyword intent classifier (Aho-Corasick, no training).

An intent matches only when the query contains **both** an action keyword and an
entity keyword for it; ties break toward the longest total match. No semantic
fallback — an unmatched query returns ``INTENT_UNKNOWN``.

Kept as the untrained baseline: T2 (TF-IDF, ``classifier/tfidf.py``) is the
primary classifier. T1's job here is to show, on the independent frozen test
set, that the frozen set is a valid measure (T1 scores it the same as the
golden pool). See ``docs/METRICS.md``.
"""
from __future__ import annotations

import json
import os

import ahocorasick

UNKNOWN = "INTENT_UNKNOWN"


class IntentClassifier:
    def __init__(self, keywords_path: str) -> None:
        self.keywords_path = keywords_path
        self.automaton = ahocorasick.Automaton()
        self.intents_config: dict = {}
        self._load_keywords()

    def _load_keywords(self) -> None:
        if not os.path.exists(self.keywords_path):
            raise FileNotFoundError(f"Keywords config file not found: {self.keywords_path}")
        with open(self.keywords_path, encoding="utf-8") as fh:
            self.intents_config = json.load(fh)

        for intent_name, data in self.intents_config.items():
            for kw_type, words in (("action", data.get("actions", [])), ("entity", data.get("entities", []))):
                for raw in words:
                    word = raw.strip().lower()
                    if not word:
                        continue
                    if word in self.automaton:
                        self.automaton.get(word).append((kw_type, word, intent_name))
                    else:
                        self.automaton.add_word(word, [(kw_type, word, intent_name)])
        self.automaton.make_automaton()

    def classify(self, query: str) -> str:
        if not query:
            return UNKNOWN

        by_intent: dict[str, dict[str, list[str]]] = {}
        for _end, payloads in self.automaton.iter(query.strip().lower()):
            for kw_type, kw, intent in payloads:
                by_intent.setdefault(intent, {"action": [], "entity": []})[kw_type].append(kw)

        scored = [
            (intent, sum(len(w) for w in m["action"]) + sum(len(w) for w in m["entity"]))
            for intent, m in by_intent.items()
            if m["action"] and m["entity"]
        ]
        if not scored:
            return UNKNOWN
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[0][0]
