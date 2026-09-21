import pytest

from app.config import Settings
from app.llm import create_ollama_chat_model


def test_model_factory_requires_key():
    settings = Settings(_env_file=None, memory_key="test-key", ollama_api_key=None)
    with pytest.raises(ValueError, match="OLLAMA_API_KEY"):
        create_ollama_chat_model(settings)
