from fastapi.testclient import TestClient

from app.api import create_app
from app.auth import hash_password
from app.config import Settings


def make_client(tmp_path):
    settings = Settings(
        _env_file=None,
        memory_path=tmp_path / "memory.db",
        memory_key="secret",
        app_admin_token="admin-token",
        owner_username="owner",
        owner_password_hash=hash_password("pass"),
        whatsapp_enabled=False,
    )
    return TestClient(create_app(settings), base_url="https://testserver")


def test_dashboard_login_and_protected_overview(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/dashboard/overview").status_code == 401
    login = client.post("/auth/login", json={"username": "owner", "password": "pass"})
    assert login.status_code == 200
    assert client.get("/auth/session").status_code == 200
    assert client.get("/dashboard/overview").json()["status"] == "ready"


def test_dashboard_provider_secret_is_not_returned(tmp_path):
    client = make_client(tmp_path)
    client.post("/auth/login", json={"username": "owner", "password": "pass"})
    response = client.post(
        "/dashboard/providers",
        json={
            "id": "p1",
            "type": "ollama",
            "name": "Ollama",
            "base_url": "https://ollama.com",
            "model": "gemma",
            "secret": "hidden",
        },
    )
    assert response.status_code == 200
    assert "hidden" not in response.text
