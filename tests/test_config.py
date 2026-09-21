from app.config import Settings


def test_settings_use_safe_local_defaults(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    settings = Settings(memory_path="data/memory.db", memory_key="test-key", whatsapp_enabled=False)
    assert settings.ollama_model == "nemotron-3-nano:30b-cloud"
    assert settings.response_language == "roman_urdu"
    assert settings.whatsapp_enabled is False
