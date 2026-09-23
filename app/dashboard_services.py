import secrets
from collections.abc import Callable
from dataclasses import dataclass

from app.dashboard_models import AgentConfig, ProviderConfig
from app.dashboard_store import DashboardStore
from app.providers import ChatProvider, ProviderError, provider_from_config


@dataclass(frozen=True)
class ChatResult:
    conversation_id: str
    text: str
    provider_id: str


class ProviderService:
    def __init__(
        self,
        store: DashboardStore,
        factory: Callable[[ProviderConfig], ChatProvider] | None = None,
    ):
        self.store = store
        self.factory = factory or (lambda config: provider_from_config(store, config))

    def save(self, provider: ProviderConfig, secret: str | None, expected_revision: int | None = None):
        return self.store.save_provider(provider, secret, expected_revision)

    def ordered(self, agent: AgentConfig) -> list[ProviderConfig]:
        providers = {provider.id: provider for provider in self.store.list_providers() if provider.enabled}
        ordered: list[ProviderConfig] = []
        for provider_id in agent.provider_ids:
            provider = providers.pop(provider_id, None)
            if provider:
                ordered.append(provider)
        ordered.extend(sorted(providers.values(), key=lambda provider: (provider.priority, provider.id)))
        return ordered

    def provider(self, config: ProviderConfig) -> ChatProvider:
        return self.factory(config)


class AgentService:
    def __init__(self, store: DashboardStore):
        self.store = store

    def save(self, agent: AgentConfig, expected_revision: int | None = None):
        return self.store.save_agent(agent, expected_revision)

    def delete(self, agent_id: str, expected_revision: int | None = None):
        return self.store.delete_agent(agent_id, expected_revision)


class ChatService:
    def __init__(self, store: DashboardStore, providers: ProviderService):
        self.store = store
        self.providers = providers

    def _agent(self, agent_id: str | None) -> AgentConfig:
        agents = self.store.list_agents()
        if agent_id:
            for agent in agents:
                if agent.id == agent_id:
                    return agent
            raise KeyError("agent not found")
        for agent in agents:
            if agent.enabled:
                return agent
        raise RuntimeError("no enabled agent configured")

    async def generate(
        self, actor: str, text: str, conversation_id: str | None, agent_id: str | None
    ) -> ChatResult:
        agent = self._agent(agent_id)
        if conversation_id is None:
            conversation_id = f"conversation-{secrets.token_urlsafe(8)}"
            self.store.create_conversation(conversation_id, actor, agent.id)
        conversation = self.store.get_conversation(conversation_id)
        if conversation is None or conversation.actor != actor:
            raise KeyError("conversation not found")
        self.store.append_message(
            f"message-{secrets.token_urlsafe(8)}", conversation_id, "user", text
        )
        messages = [{"role": "system", "content": agent.system_prompt}, {"role": "user", "content": text}]
        last_error: ProviderError | None = None
        for config in self.providers.ordered(agent):
            try:
                result = await self.providers.provider(config).generate(messages)
                self.store.append_message(
                    f"message-{secrets.token_urlsafe(8)}",
                    conversation_id,
                    "assistant",
                    result,
                    provider_id=config.id,
                )
                return ChatResult(conversation_id, result, config.id)
            except ProviderError as exc:
                last_error = exc
        raise RuntimeError(last_error.safe_detail if last_error else "no provider configured")
