import asyncio

import pytest

from app.decision_backends import BackendTimeoutError, BackendUnavailableError
from app.decision_models import DecisionAnswer, DecisionRequest, DecisionResponse
from app.decision_router import DecisionRouter


def valid_request() -> DecisionRequest:
    return DecisionRequest(
        state="charged twice",
        questions={
            "department": {
                "type": "choice",
                "instructions": "Which team should handle this?",
                "criteria": {"billing": "payments", "technical": "bugs"},
            }
        },
    )


def successful_response(backend: str = "laya", confidence: float = 0.91) -> DecisionResponse:
    return DecisionResponse(
        answers={"department": DecisionAnswer(value="billing", probability=confidence)},
        confidence=confidence,
        backend=backend,
        latency_ms=1.0,
        review_required=False,
        reason_code="ok",
    )


class FakeBackend:
    def __init__(self, name: str, result: DecisionResponse | Exception):
        self.name = name
        self.result = result
        self.calls = 0

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class SlowBackend:
    name = "laya"

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        await asyncio.sleep(0.1)
        return successful_response()


@pytest.mark.asyncio
async def test_router_uses_openjev_after_laya_failure():
    router = DecisionRouter(
        [
            FakeBackend("laya", BackendUnavailableError("offline")),
            FakeBackend("openjev", successful_response("openjev")),
        ],
        timeout_seconds=1,
        confidence_threshold=0.75,
    )

    result = await router.decide(valid_request())

    assert result.backend == "openjev"
    assert result.reason_code == "ok"


@pytest.mark.asyncio
async def test_router_marks_low_confidence_for_human_review():
    router = DecisionRouter(
        [FakeBackend("laya", successful_response("laya", confidence=0.41))],
        timeout_seconds=1,
        confidence_threshold=0.75,
    )

    result = await router.decide(valid_request())

    assert result.review_required is True
    assert result.reason_code == "low_confidence"


@pytest.mark.asyncio
async def test_router_returns_explicit_all_backends_failed_state():
    router = DecisionRouter(
        [
            FakeBackend("laya", BackendTimeoutError("timed out")),
            FakeBackend("openjev", BackendUnavailableError("offline")),
        ],
        timeout_seconds=1,
        confidence_threshold=0.75,
    )

    result = await router.decide(valid_request())

    assert result.backend is None
    assert result.reason_code == "all_backends_failed"
    assert result.review_required is True


@pytest.mark.asyncio
async def test_router_converts_slow_backend_to_timeout_and_tries_next():
    router = DecisionRouter(
        [SlowBackend(), FakeBackend("openjev", successful_response("openjev"))],
        timeout_seconds=0.01,
        confidence_threshold=0.75,
    )

    result = await router.decide(valid_request())

    assert result.backend == "openjev"


@pytest.mark.asyncio
async def test_router_opens_circuit_after_repeated_backend_failures():
    failing = FakeBackend("laya", BackendUnavailableError("offline"))
    router = DecisionRouter(
        [failing],
        timeout_seconds=1,
        confidence_threshold=0.75,
        failure_threshold=2,
        circuit_open_seconds=60,
    )

    await router.decide(valid_request())
    await router.decide(valid_request())
    await router.decide(valid_request())

    assert failing.calls == 2
