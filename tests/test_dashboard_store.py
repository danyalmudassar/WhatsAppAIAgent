from datetime import UTC, datetime, timedelta

import pytest

from app.dashboard_models import (
    AgentConfig,
    AuditEvent,
    ProviderConfig,
    ProviderType,
    RuntimeEvent,
    SessionRecord,
)
from app.dashboard_store import DashboardStore


def test_dashboard_store_encrypts_and_persists_records(tmp_path):
    path = tmp_path / "memory.db"
    store = DashboardStore(path, "dashboard-secret")
    provider = store.save_provider(
        ProviderConfig(id="p1", type=ProviderType.ollama, name="Ollama", base_url="https://ollama.com", model="gemma"),
        secret="super-secret",
    )
    store.save_agent(AgentConfig(id="a1", name="Assistant", provider_ids=["p1"]))
    session = SessionRecord(id="raw-session", actor="admin", expires_at=datetime.now(UTC) + timedelta(hours=1))
    store.create_session(session)
    store.append_event(RuntimeEvent(id="e1", timestamp=datetime.now(UTC), type="message_received", correlation_id="c1"))
    store.append_audit(AuditEvent(id="audit-1", timestamp=datetime.now(UTC), actor="admin", action="create", resource="p1", result="ok"))
    assert provider.has_secret
    assert store.get_provider_secret("p1") == "super-secret"
    assert store.get_session("raw-session") is not None
    assert b"super-secret" not in path.read_bytes()


def test_revision_conflict_does_not_overwrite(tmp_path):
    store = DashboardStore(tmp_path / "memory.db", "dashboard-secret")
    saved = store.save_agent(AgentConfig(id="a1", name="Assistant"))
    with pytest.raises(ValueError, match="revision conflict"):
        store.save_agent(AgentConfig(id="a1", name="Changed"), expected_revision=99)
    assert saved.revision == 1
