import httpx
import pytest

from app.decision_backends import (
    BackendAuthError,
    BackendProtocolError,
    JevBackend,
    OpenJevBackend,
)
from app.decision_models import DecisionRequest


def valid_request() -> DecisionRequest:
    return DecisionRequest(
        state={"body": "charged twice"},
        questions={
            "department": {
                "type": "choice",
                "instructions": "Which team should handle this?",
                "criteria": {"billing": "payments", "technical": "bugs"},
            }
        },
    )


@pytest.mark.asyncio
async def test_openjev_adapter_normalizes_typed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/decide"
        return httpx.Response(
            200,
            json={
                "answers": {"department": {"choice": "billing", "probability": 0.91}},
                "confidence": 0.91,
            },
        )

    backend = OpenJevBackend(
        "http://openjev.test",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )
    result = await backend.decide(valid_request())

    assert result.answers["department"].value == "billing"
    assert result.backend == "openjev"


@pytest.mark.asyncio
async def test_jev_adapter_returns_auth_failure_without_exposing_key():
    backend = JevBackend(
        "https://jev.test",
        "secret-value",
        timeout=1,
        transport=httpx.MockTransport(lambda request: httpx.Response(401)),
    )

    with pytest.raises(BackendAuthError) as exc_info:
        await backend.decide(valid_request())

    assert "secret-value" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_openjev_adapter_rejects_missing_answers():
    backend = OpenJevBackend(
        "http://openjev.test",
        timeout=1,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )

    with pytest.raises(BackendProtocolError, match="answers"):
        await backend.decide(valid_request())
