import pytest

from app.decision_models import DecisionAnswer, DecisionResponse
from app.mcp_decision_server import DecisionMcpServer


class FakeRouter:
    async def decide(self, request):
        return DecisionResponse(
            answers={"route": DecisionAnswer(value="developer", probability=0.95)},
            confidence=0.95,
            backend="laya",
            latency_ms=2.0,
            review_required=False,
            reason_code="ok",
        )


@pytest.mark.asyncio
async def test_mcp_decide_returns_contract_without_model_details():
    server = DecisionMcpServer(FakeRouter())

    result = await server.decide(
        {
            "state": {"body": "fix login"},
            "questions": {
                "route": {
                    "type": "choice",
                    "instructions": "Which workflow?",
                    "criteria": {"developer": "code"},
                }
            },
        }
    )

    assert result["backend"] == "laya"
    assert "api_key" not in str(result)


@pytest.mark.asyncio
async def test_mcp_route_uses_typed_route_question():
    server = DecisionMcpServer(FakeRouter())

    result = await server.route({"body": "fix login"})

    assert result["answers"]["route"]["value"] == "developer"


def test_mcp_review_required_is_true_for_low_confidence():
    server = DecisionMcpServer(FakeRouter())

    result = server.review_required(
        {
            "confidence": 0.41,
            "review_required": False,
            "reason_code": "low_confidence",
        }
    )

    assert result["review_required"] is True
