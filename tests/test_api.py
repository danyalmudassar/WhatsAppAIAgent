from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings


def test_duplicate_webhook_is_not_processed_twice(tmp_path):
    settings = Settings(
        _env_file=None,
        memory_path=tmp_path / "memory.db",
        memory_key="secret",
        whatsapp_enabled=False,
        ollama_api_key=None,
    )
    app = create_app(settings)
    client = TestClient(app)
    payload = {"id": "w-1", "from": "self", "text": "meri tasks dikhao"}
    assert client.post("/webhooks/whatsapp", json=payload).status_code == 200
    assert client.post("/webhooks/whatsapp", json=payload).json()["status"] == "duplicate"


def test_local_message_returns_response(tmp_path):
    settings = Settings(
        _env_file=None,
        memory_path=tmp_path / "memory.db",
        memory_key="secret",
        whatsapp_enabled=False,
        ollama_api_key=None,
    )
    app = create_app(settings)
    response = TestClient(app).post(
        "/messages",
        json={"message_id": "local-1", "sender_id": "self", "text": "meri profile batao"},
    )
    assert response.status_code == 200
    assert response.json()["message_id"] == "local-1"


def test_admin_endpoints_require_bearer_token(tmp_path):
    settings = Settings(_env_file=None, memory_path=tmp_path / "memory.db", memory_key="secret")
    client = TestClient(create_app(settings))
    assert client.get("/memory/export").status_code == 401
    assert client.get("/memory/export", headers={"Authorization": "Bearer local-dev-token"}).status_code == 200
