"""Trained intent classifiers (T2 candidates).

Per docs/guardrail-integration/no-cv note: trained on the golden pool,
evaluated ONLY on the frozen independent test set.
"""

from .tfidf import TfidfIntentClassifier

__all__ = ["TfidfIntentClassifier"]
