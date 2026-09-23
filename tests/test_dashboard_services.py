import pytest

from app.dashboard_models import AgentConfig, ProviderConfig, ProviderType
from app.dashboard_services import ChatService, ProviderService
from app.dashboard_store import DashboardStore
from app.providers import ProviderError


class FakeProvider:
    def __init__(self, provider_id: str, text: str | None = None, error: bool = False):
        self.provider_id = provider_id
        self.text = text
        self.error = error

    async def generate(self, messages):
        if self.error:
            raise ProviderError(self.provider_id, retryable=True, safe_detail="unavailable")
        return self.text or ""


@pytest.mark.asyncio
async def test_chat_service_uses_next_provider_after_failure(tmp_path):
    store = DashboardStore(tmp_path / "memory.db", "secret")
    store.save_provider(ProviderConfig(id="primary", type=ProviderType.ollama, name="Primary", base_url="https://a", model="x", priority=0))
    store.save_provider(ProviderConfig(id="backup", type=ProviderType.ollama, name="Backup", base_url="https://b", model="x", priority=1))
    store.save_agent(AgentConfig(id="agent-1", name="Assistant", provider_ids=["primary", "backup"]))
    providers = {
        "primary": FakeProvider("primary", error=True),
        "backup": FakeProvider("backup", text="fallback reply"),
    }
    service = ChatService(store, ProviderService(store, lambda config: providers[config.id]))

    result = await service.generate("owner", "hello", None, "agent-1")

    assert result.text == "fallback reply"
    assert result.provider_id == "backup"
    messages, _ = store.list_messages(result.conversation_id)
    assert [message.role for message in messages] == ["user", "assistant"]
