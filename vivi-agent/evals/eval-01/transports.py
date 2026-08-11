"""EVAL-01 — live ``ProviderTransport`` implementations.

Backend-only HTTP seam (matches ``model_providers/adapters.py``'s own
``ProviderTransport`` Protocol docstring): owns the real SDK/HTTP call,
authentication header, and one-attempt timeout boundary below the adapter.
Never imported by ``dataset.py``/``scoring.py``/``runner.py`` — those stay
network-free and offline-testable; only ``run_live_eval.py`` wires a real
transport in.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class GeminiRestTransport:
    """Real Gemini REST transport (``models.generateContent``).

    ``GeminiAdapter._proposal_payload`` includes ``"model"`` as a top-level
    payload key (convenient for offline tests), but the real REST API takes
    the model in the URL path, not the request body — this transport moves
    it there and never sends it in the JSON body.
    """

    def __init__(self, api_key: str, *, session: "requests.Session | None" = None) -> None:
        if not api_key:
            raise ValueError("GeminiRestTransport requires a non-empty api_key")
        self._api_key = api_key
        self._session = session or requests.Session()

    def __call__(self, payload: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]:
        body = dict(payload)
        model = body.pop("model")
        url = GEMINI_GENERATE_CONTENT_URL.format(model=model)
        try:
            response = self._session.post(
                url,
                params={"key": self._api_key},
                json=body,
                timeout=timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(str(exc)) from exc
        if response.status_code != 200:
            raise RuntimeError(
                f"Gemini API returned HTTP {response.status_code}: {response.text[:500]}"
            )
        return response.json()


class OpenAIRestTransport:
    """Real OpenAI REST transport (``chat.completions``)."""

    def __init__(self, api_key: str, *, session: "requests.Session | None" = None) -> None:
        if not api_key:
            raise ValueError("OpenAIRestTransport requires a non-empty api_key")
        self._api_key = api_key
        self._session = session or requests.Session()

    def __call__(self, payload: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]:
        try:
            response = self._session.post(
                OPENAI_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=dict(payload),
                timeout=timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(str(exc)) from exc
        if response.status_code != 200:
            raise RuntimeError(
                f"OpenAI API returned HTTP {response.status_code}: {response.text[:500]}"
            )
        return response.json()
