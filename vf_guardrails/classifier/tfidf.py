"""TF-IDF + linear SVM intent classifier (T2 candidate).

Lightweight (scikit-learn only, no torch / no model download), trains in
seconds, sub-millisecond inference. Character n-grams carry most of the signal
for noisy/dialectal Vietnamese; word n-grams add a little.

Abstain rule (PRD FR-03: "chỉ trả intent khi confidence đạt threshold và margin
so với nhãn thứ hai đạt yêu cầu"): predict INTENT_UNKNOWN unless the top
decision-function score clears ``min_score`` AND beats the 2nd-best by
``min_margin``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

UNKNOWN = "INTENT_UNKNOWN"


@dataclass
class T2Config:
    min_score: float = 0.0
    min_margin: float = 0.0


class TfidfIntentClassifier:
    def __init__(
        self,
        config: T2Config | None = None,
        *,
        estimator: str = "svc",          # "svc" | "logreg"
        char_ngram: tuple[int, int] = (3, 5),
        word_ngram: tuple[int, int] | None = (1, 2),
    ) -> None:
        self.config = config or T2Config()
        self.estimator = estimator
        self.char_ngram = char_ngram
        self.word_ngram = word_ngram
        self._pipe: Pipeline | None = None
        self._labels: np.ndarray | None = None

    def fit(self, utterances: list[str], labels: list[str]) -> "TfidfIntentClassifier":
        parts = [
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=self.char_ngram,
                                     lowercase=True, min_df=2, sublinear_tf=True)),
        ]
        if self.word_ngram is not None:
            parts.append(
                ("word", TfidfVectorizer(analyzer="word", ngram_range=self.word_ngram,
                                         lowercase=True, min_df=2, sublinear_tf=True))
            )
        features = FeatureUnion(parts)
        if self.estimator == "logreg":
            clf = LogisticRegression(C=4.0, class_weight="balanced", max_iter=2000)
        else:
            clf = LinearSVC(C=1.0, class_weight="balanced")
        self._pipe = Pipeline([("features", features), ("clf", clf)])
        self._pipe.fit(utterances, labels)
        self._labels = self._pipe.named_steps["clf"].classes_
        return self

    def _scores(self, utterance: str) -> np.ndarray:
        assert self._pipe is not None, "classifier not fitted"
        clf = self._pipe.named_steps["clf"]
        if hasattr(clf, "decision_function"):
            return np.atleast_1d(self._pipe.decision_function([utterance])[0])
        return self._pipe.predict_proba([utterance])[0]

    def predict(self, utterance: str) -> str:
        """Return an intent label, or INTENT_UNKNOWN when not confident."""
        scores = self._scores(utterance)
        order = np.argsort(scores)[::-1]
        top, second = scores[order[0]], scores[order[1]]
        if top < self.config.min_score or (top - second) < self.config.min_margin:
            return UNKNOWN
        return str(self._labels[order[0]])

    def predict_raw(self, utterance: str) -> tuple[str, float, float]:
        """(argmax label, top score, margin) — ignores the abstain rule."""
        scores = self._scores(utterance)
        order = np.argsort(scores)[::-1]
        return str(self._labels[order[0]]), float(scores[order[0]]), float(scores[order[0]] - scores[order[1]])
