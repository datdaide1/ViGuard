"""Trained intent classifier for the text->intent (gateway) path.

Trained on the labelled pool, evaluated only on the frozen independent test set
(no cross-validation on the labelled pool — near-duplicate rows leak). See
docs/METRICS.md.
"""

from .intent import IntentResolver, IntentResult
from .tfidf import UNKNOWN, T2Config, TfidfIntentClassifier

__all__ = ["IntentResolver", "IntentResult", "TfidfIntentClassifier", "T2Config", "UNKNOWN"]
