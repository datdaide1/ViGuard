"""Production HTTP transports for supported model providers."""

from __future__ import annotations

from collections.abc import Mapping
import threading
import time
from typing import Any

import requests


class RetryableTransportError(RuntimeError):
    pass


class RateLimitedTransport:
    """Serialize provider calls and enforce a process-local RPM ceiling."""

    def __init__(
        self, transport, requests_per_minute: float = 12.0, max_attempts: int = 2
    ) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        self._transport = transport
        if max_attempts not in {1, 2}:
            raise ValueError("max_attempts must be 1 or 2")
        self._max_attempts = max_attempts
        self._minimum_interval = 60.0 / requests_per_minute
        self._last_started: float | None = None
        self._lock = threading.Lock()

    def __call__(self, payload: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]:
        with self._lock:
            for attempt in range(self._max_attempts):
                now = time.monotonic()
                if self._last_started is not None:
                    remaining = self._minimum_interval - (now - self._last_started)
                    if remaining > 0:
                        time.sleep(remaining)
                self._last_started = time.monotonic()
                try:
                    return self._transport(payload, timeout_seconds)
                except (RetryableTransportError, TimeoutError):
                    if attempt + 1 == self._max_attempts:
                        raise
            raise AssertionError("unreachable")


class GeminiRestTransport:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        self._api_key = api_key
        self._session = session or requests.Session()

    def __call__(self, payload: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]:
        body = dict(payload)
        model = body.pop("model")
        try:
            response = self._session.post(
                self.URL.format(model=model),
                params={"key": self._api_key},
                json=body,
                timeout=timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise TimeoutError("Gemini request timed out") from exc
        except requests.exceptions.ConnectionError as exc:
            raise RetryableTransportError("Gemini connection failed") from exc
        if response.status_code != 200:
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableTransportError(
                    f"Gemini API returned retryable HTTP {response.status_code}"
                )
            raise RuntimeError(f"Gemini API returned HTTP {response.status_code}")
        return response.json()


class OpenAIRestTransport:
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self._api_key = api_key
        self._session = session or requests.Session()

    def __call__(self, payload: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]:
        try:
            response = self._session.post(
                self.URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=dict(payload),
                timeout=timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise TimeoutError("OpenAI request timed out") from exc
        except requests.exceptions.ConnectionError as exc:
            raise RetryableTransportError("OpenAI connection failed") from exc
        if response.status_code != 200:
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableTransportError(
                    f"OpenAI API returned retryable HTTP {response.status_code}"
                )
            raise RuntimeError(f"OpenAI API returned HTTP {response.status_code}")
        return response.json()
