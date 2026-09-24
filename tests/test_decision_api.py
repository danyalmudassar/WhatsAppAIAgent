from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.decision_models import DecisionAnswer, DecisionResponse


def settings(tmp_path):
    return Settings(
        _env_file=None,
        memory_path=tmp_path / "memory.db",
        memory_key="secret",
        whatsapp_enabled=False,
        ollama_api_key=None,
    )


def valid_request_json():
    return {
        "state": {"body": "fix login"},
        "questions": {
            "risk": {
                "type": "noul",
                "instructions": "Is this high risk?",
            }
        },
    }


class FakeRouter:
    async def decide(self, request):
        return DecisionResponse(
            answers={"risk": DecisionAnswer(value=False, probability=0.95)},
            confidence=0.95,
            backend="laya",
            latency_ms=1.0,
            review_required=False,
            reason_code="ok",
        )


def test_decide_requires_admin_or_session(tmp_path):
    response = TestClient(create_app(settings(tmp_path))).post(
        "/decide",
        json=valid_request_json(),
    )

    assert response.status_code == 401


def test_decide_returns_typed_router_result(tmp_path):
    client = TestClient(create_app(settings(tmp_path), decision_router=FakeRouter()))

    response = client.post(
        "/decide",
        headers={"Authorization": "******"},
        json=valid_request_json(),
    )

    assert response.status_code == 200
    assert response.json()["backend"] == "laya"


def test_decide_rejects_unknown_question_type(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post(
        "/decide",
        headers={"Authorization": "******"},
        json={
            "state": "x",
            "questions": {"q": {"type": "unknown", "instructions": "?"}},
        },
    )

    assert response.status_code == 422


def test_decide_reports_disabled_router_explicitly(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post(
        "/decide",
        headers={"Authorization": "******"},
        json=valid_request_json(),
    )

    assert response.status_code == 200
    assert response.json()["reason_code"] == "backend_unavailable"
    assert response.json()["review_required"] is True
