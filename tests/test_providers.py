from app.dashboard_models import ProviderConfig, ProviderType
from app.dashboard_store import DashboardStore
from app.providers import OpenAICompatibleProvider, provider_from_config


def test_provider_registry_selects_openai_compatible_adapter(tmp_path):
    store = DashboardStore(tmp_path / "memory.db", "secret")
    config = store.save_provider(
        ProviderConfig(id="p1", type=ProviderType.openai_compatible, name="Gateway", base_url="https://example.com", model="x"),
        secret="key",
    )
    adapter = provider_from_config(store, config)
    assert isinstance(adapter, OpenAICompatibleProvider)
