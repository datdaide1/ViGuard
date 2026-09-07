from __future__ import annotations

import pytest

from vehicle_agent.model_providers import (
    GeminiRestTransport,
    OpenAIRestTransport,
    RetryableTransportError,
)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response

    def post(self, *args, **kwargs):
        return self.response


@pytest.mark.parametrize(
    ("transport_cls", "payload"),
    ((GeminiRestTransport, {"model": "test"}), (OpenAIRestTransport, {})),
)
def test_non_retryable_provider_error_includes_bounded_redacted_detail(transport_cls, payload):
    secret = "AIzaTHIS_IS_A_SECRET_KEY"
    response = FakeResponse(
        400,
        {"error": {"status": "INVALID_ARGUMENT", "code": 400, "message": f"Invalid API key: {secret}"}},
    )
    transport = transport_cls("configured-secret", session=FakeSession(response))

    with pytest.raises(RuntimeError) as raised:
        transport(payload, 1.0)

    message = str(raised.value)
    assert "INVALID_ARGUMENT" in message
    assert "provider detail:" in message
    assert secret not in message
    assert "[REDACTED]" in message
    assert len(message) < 300


def test_retryable_provider_error_includes_safe_quota_detail():
    response = FakeResponse(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}})
    transport = GeminiRestTransport("configured-secret", session=FakeSession(response))

    with pytest.raises(RetryableTransportError, match="RESOURCE_EXHAUSTED.*Quota exceeded"):
        transport({"model": "test"}, 1.0)


def test_non_json_provider_body_is_not_copied_into_exception():
    raw_secret = "Bearer highly-sensitive-token"
    response = FakeResponse(500, ValueError(raw_secret))
    transport = OpenAIRestTransport("configured-secret", session=FakeSession(response))

    with pytest.raises(RetryableTransportError) as raised:
        transport({}, 1.0)

    assert raw_secret not in str(raised.value)
    assert "provider detail" not in str(raised.value)
