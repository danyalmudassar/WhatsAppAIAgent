import pytest
from pydantic import ValidationError

from app.dashboard_models import AgentConfig, ProviderConfig, ProviderType


def test_provider_and_agent_contracts_are_typed():
    provider = ProviderConfig(
        id="ollama-main",
        type=ProviderType.ollama,
        name="Ollama Cloud",
        base_url="https://ollama.com",
        model="gemma4:31b",
    )
    agent = AgentConfig(id="assistant", name="Assistant", provider_ids=[provider.id])
    assert agent.provider_ids == ["ollama-main"]


def test_blank_agent_name_is_rejected():
    with pytest.raises(ValidationError):
        AgentConfig(id="assistant", name=" ")
