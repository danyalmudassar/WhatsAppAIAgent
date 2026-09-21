from langchain_ollama import ChatOllama

from app.config import Settings


class ProviderUnavailableError(RuntimeError):
    pass


def create_ollama_chat_model(settings: Settings) -> ChatOllama:
    if not settings.ollama_api_key:
        raise ValueError("OLLAMA_API_KEY is required")
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        client_kwargs={"headers": {"Authorization": f"Bearer {settings.ollama_api_key.get_secret_value()}"}},
    )
