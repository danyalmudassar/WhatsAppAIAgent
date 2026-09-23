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


def test_conversation_and_messages_survive_store_restart(tmp_path):
    first = DashboardStore(tmp_path / "memory.db", "secret")
    conversation = first.create_conversation("c1", "owner", "agent-1")
    first.append_message("m1", "c1", "user", "salam")
    first.append_message("m2", "c1", "assistant", "Walaikum salam")

    second = DashboardStore(tmp_path / "memory.db", "secret")
    restored = second.get_conversation("c1")
    assert restored is not None
    assert restored.id == conversation.id
    assert restored.actor == conversation.actor
    assert restored.agent_id == conversation.agent_id
    messages, _ = second.list_messages("c1")
    assert [message.id for message in messages] == ["m1", "m2"]


def test_message_pagination_returns_next_cursor(tmp_path):
    store = DashboardStore(tmp_path / "memory.db", "secret")
    store.create_conversation("c1", "owner", None)
    for index in range(3):
        store.append_message(f"m{index}", "c1", "user", str(index))

    page, cursor = store.list_messages("c1", after=0, limit=2)
    assert [message.id for message in page] == ["m0", "m1"]
    assert cursor == 2


def test_settings_are_encrypted_and_round_trip(tmp_path):
    store = DashboardStore(tmp_path / "memory.db", "secret")
    store.set_setting("default_agent_id", "agent-1")
    assert store.get_setting("default_agent_id") == "agent-1"
    assert b"agent-1" not in (tmp_path / "memory.db").read_bytes()
