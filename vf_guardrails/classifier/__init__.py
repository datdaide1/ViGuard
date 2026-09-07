"""Trained intent classifiers (T2 candidates).

Per docs/guardrail-integration/no-cv note: trained on the golden pool,
evaluated ONLY on the frozen independent test set.
"""

from .intent import IntentResolver, IntentResult
from .tfidf import UNKNOWN, T2Config, TfidfIntentClassifier

__all__ = ["IntentResolver", "IntentResult", "TfidfIntentClassifier", "T2Config", "UNKNOWN"]
