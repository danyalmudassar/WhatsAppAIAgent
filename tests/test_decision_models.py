import pytest
from pydantic import ValidationError

from app.decision_models import (
    DecisionAnswer,
    DecisionErrorResponse,
    DecisionRequest,
    DecisionResponse,
)


def test_decision_request_accepts_json_state_and_typed_questions():
    request = DecisionRequest(
        state={"body": "charged twice"},
        questions={
            "department": {
                "type": "choice",
                "instructions": "Which team should handle this?",
                "criteria": {"billing": "payments", "technical": "bugs"},
            }
        },
    )

    assert request.state["body"] == "charged twice"
    assert request.questions["department"].type == "choice"


def test_decision_response_preserves_backend_latency_and_review_signal():
    response = DecisionResponse(
        answers={"department": DecisionAnswer(value="billing", probability=0.94)},
        confidence=0.94,
        backend="laya",
        latency_ms=31.2,
        review_required=False,
        reason_code="ok",
    )

    assert response.backend == "laya"
    assert response.answers["department"].probability == 0.94


def test_decision_error_distinguishes_timeout_from_unavailable():
    error = DecisionErrorResponse(
        answers={},
        confidence=None,
        backend=None,
        latency_ms=1000,
        review_required=True,
        reason_code="backend_timeout",
        error="Decision backend timed out",
    )

    assert error.reason_code == "backend_timeout"
    assert error.review_required is True


def test_decision_request_rejects_empty_questions():
    with pytest.raises(ValidationError):
        DecisionRequest(state="hello", questions={})


def test_decision_answer_rejects_invalid_probability():
    with pytest.raises(ValidationError):
        DecisionAnswer(value="billing", probability=1.1)
