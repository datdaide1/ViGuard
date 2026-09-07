"""IntentResolver — the classifier the Guardrail uses.

Decision (docs/DECISIONS.md): T2 = TF-IDF + LinearSVC
is **primary**; T1 (keyword) is demoted out of the resolution path (the
T1→T2 cascade scored *below* T2 alone). T3 SLM stays deferred (D5).

Abstain: default ``min_score=-0.5`` — near-full accuracy on the frozen set
(87.4% vs 88.3% no-abstain) while rejecting the most out-of-scope inputs
(strongly-negative top score). Tune via ``T2Config``; see T2_DECISION.md §3.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .tfidf import UNKNOWN, T2Config, TfidfIntentClassifier

_DEFAULT_MODEL = Path(__file__).resolve().parent / "model_tfidf.pkl"
_GUARDRAIL_ABSTAIN = T2Config(min_score=-0.5, min_margin=0.0)


@dataclass(frozen=True)
class IntentResult:
    intent: str            # a catalog intent, or UNKNOWN ("INTENT_UNKNOWN")
    tier: str              # "T2" | "T2_ABSTAIN"
    score: float
    margin: float

    @property
    def resolved(self) -> bool:
        return self.intent != UNKNOWN


class IntentResolver:
    def __init__(
        self,
        model_path: str | Path = _DEFAULT_MODEL,
        *,
        config: T2Config | None = None,
    ) -> None:
        self._t2 = TfidfIntentClassifier.load(model_path, config or _GUARDRAIL_ABSTAIN)

    def resolve(self, utterance: str) -> IntentResult:
        if not utterance or not utterance.strip():
            return IntentResult(UNKNOWN, "T2_ABSTAIN", 0.0, 0.0)
        label, score, margin = self._t2.predict_raw(utterance)
        chosen = self._t2.predict(utterance)  # applies the abstain rule
        return IntentResult(chosen, "T2" if chosen != UNKNOWN else "T2_ABSTAIN", score, margin)
