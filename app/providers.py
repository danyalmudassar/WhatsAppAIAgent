from typing import Protocol

import httpx

from app.dashboard_models import ProviderConfig, ProviderType
from app.dashboard_store import DashboardStore


class ChatProvider(Protocol):
    async def generate(self, messages: list[dict[str, str]]) -> str: ...


class ProviderError(RuntimeError):
    def __init__(self, provider_id: str, retryable: bool, safe_detail: str):
        super().__init__(safe_detail)
        self.provider_id = provider_id
        self.retryable = retryable
        self.safe_detail = safe_detail


class OllamaProvider:
    def __init__(self, config: ProviderConfig, secret: str | None):
        self.config, self.secret = config, secret

    async def generate(self, messages: list[dict[str, str]]) -> str:
        headers = {"Authorization": "Bearer " + self.secret} if self.secret else {}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}/api/chat",
                headers=headers,
                json={"model": self.config.model, "messages": messages, "stream": False},
            )
        if response.status_code >= 500:
            raise ProviderError(f"provider returned HTTP {response.status_code}")
        response.raise_for_status()
        return str(response.json().get("message", {}).get("content", ""))


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig, secret: str | None):
        self.config, self.secret = config, secret

    async def generate(self, messages: list[dict[str, str]]) -> str:
        headers = {"Authorization": "Bearer " + self.secret} if self.secret else {}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={"model": self.config.model, "messages": messages, "stream": False},
            )
        if response.status_code >= 500:
            raise ProviderError(f"provider returned HTTP {response.status_code}")
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])


def provider_from_config(store: DashboardStore, config: ProviderConfig) -> ChatProvider:
    secret = store.get_provider_secret(config.id)
    if config.type == ProviderType.ollama:
        return OllamaProvider(config, secret)
    return OpenAICompatibleProvider(config, secret)
