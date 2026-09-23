import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.dashboard_models import (
    AgentConfig,
    AuditEvent,
    ConversationRecord,
    MessageRecord,
    ProviderConfig,
    RuntimeEvent,
    SessionRecord,
    SettingsRecord,
)
from app.security import EncryptedCodec


class DashboardStore:
    def __init__(self, path: Path, secret: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.codec = EncryptedCodec(secret)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS dashboard_providers (
                    id TEXT PRIMARY KEY, config BLOB NOT NULL, secret BLOB,
                    revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_agents (
                    id TEXT PRIMARY KEY, config BLOB NOT NULL, revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_sessions (
                    id_hash TEXT PRIMARY KEY, record BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, record BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, record BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_conversations (
                    id TEXT PRIMARY KEY, record BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
                    record BLOB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS dashboard_messages_conversation
                    ON dashboard_messages(conversation_id, sequence);
                CREATE TABLE IF NOT EXISTS dashboard_settings (
                    key TEXT PRIMARY KEY, record BLOB NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save_provider(self, provider: ProviderConfig, secret: str | None = None, expected_revision: int | None = None) -> ProviderConfig:
        with self._connect() as db:
            row = db.execute("SELECT revision FROM dashboard_providers WHERE id=?", (provider.id,)).fetchone()
            current = row[0] if row else 0
            if expected_revision is not None and current != expected_revision:
                raise ValueError("provider revision conflict")
            revision = current + 1
            stored = provider.model_copy(update={"revision": revision, "has_secret": bool(secret)})
            encrypted = self.codec.dumps(secret) if secret else None
            db.execute(
                "INSERT OR REPLACE INTO dashboard_providers VALUES (?, ?, ?, ?)",
                (provider.id, self.codec.dumps(stored.model_dump()), encrypted, revision),
            )
        return stored

    def get_provider_secret(self, provider_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT secret FROM dashboard_providers WHERE id=?", (provider_id,)).fetchone()
        return self.codec.loads(row[0]) if row and row[0] else None

    def save_agent(self, agent: AgentConfig, expected_revision: int | None = None) -> AgentConfig:
        with self._connect() as db:
            row = db.execute("SELECT revision FROM dashboard_agents WHERE id=?", (agent.id,)).fetchone()
            current = row[0] if row else 0
            if expected_revision is not None and current != expected_revision:
                raise ValueError("agent revision conflict")
            stored = agent.model_copy(update={"revision": current + 1})
            db.execute(
                "INSERT OR REPLACE INTO dashboard_agents VALUES (?, ?, ?)",
                (agent.id, self.codec.dumps(stored.model_dump()), stored.revision),
            )
        return stored

    def list_providers(self) -> list[ProviderConfig]:
        with self._connect() as db:
            rows = db.execute("SELECT config FROM dashboard_providers ORDER BY id").fetchall()
        return [ProviderConfig.model_validate(self.codec.loads(row[0])) for row in rows]

    def list_agents(self) -> list[AgentConfig]:
        with self._connect() as db:
            rows = db.execute("SELECT config FROM dashboard_agents ORDER BY id").fetchall()
        return [AgentConfig.model_validate(self.codec.loads(row[0])) for row in rows]

    def delete_agent(self, agent_id: str, expected_revision: int | None = None) -> None:
        with self._connect() as db:
            row = db.execute("SELECT revision FROM dashboard_agents WHERE id=?", (agent_id,)).fetchone()
            if not row:
                raise KeyError("agent not found")
            if expected_revision is not None and row[0] != expected_revision:
                raise ValueError("agent revision conflict")
            db.execute("DELETE FROM dashboard_agents WHERE id=?", (agent_id,))

    def delete_provider(self, provider_id: str, expected_revision: int | None = None) -> None:
        with self._connect() as db:
            row = db.execute("SELECT revision FROM dashboard_providers WHERE id=?", (provider_id,)).fetchone()
            if not row:
                raise KeyError("provider not found")
            if expected_revision is not None and row[0] != expected_revision:
                raise ValueError("provider revision conflict")
            db.execute("DELETE FROM dashboard_providers WHERE id=?", (provider_id,))

    def audit_after(self, sequence: int = 0, limit: int = 100) -> list[tuple[int, AuditEvent]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT sequence, record FROM dashboard_audit WHERE sequence>? ORDER BY sequence LIMIT ?",
                (sequence, limit),
            ).fetchall()
        return [(sequence, AuditEvent.model_validate(self.codec.loads(record))) for sequence, record in rows]

    def create_session(self, record: SessionRecord) -> None:
        key = hashlib.sha256(record.id.encode()).hexdigest()
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO dashboard_sessions VALUES (?, ?)", (key, self.codec.dumps(record.model_dump(mode="json"))))

    def get_session(self, session_id: str) -> SessionRecord | None:
        key = hashlib.sha256(session_id.encode()).hexdigest()
        with self._connect() as db:
            row = db.execute("SELECT record FROM dashboard_sessions WHERE id_hash=?", (key,)).fetchone()
        return SessionRecord.model_validate(self.codec.loads(row[0])) if row else None

    def revoke_session(self, session_id: str) -> None:
        key = hashlib.sha256(session_id.encode()).hexdigest()
        record = self.get_session(session_id)
        if record:
            with self._connect() as db:
                db.execute(
                    "UPDATE dashboard_sessions SET record=? WHERE id_hash=?",
                    (self.codec.dumps(record.model_copy(update={"revoked": True}).model_dump(mode="json")), key),
                )

    def append_event(self, event: RuntimeEvent) -> int:
        with self._connect() as db:
            cursor = db.execute("INSERT INTO dashboard_events(record) VALUES (?)", (self.codec.dumps(event.model_dump(mode="json")),))
            return int(cursor.lastrowid)

    def events_after(self, sequence: int = 0, limit: int = 100) -> list[tuple[int, RuntimeEvent]]:
        with self._connect() as db:
            rows = db.execute("SELECT sequence, record FROM dashboard_events WHERE sequence>? ORDER BY sequence LIMIT ?", (sequence, limit)).fetchall()
        return [(sequence, RuntimeEvent.model_validate(self.codec.loads(record))) for sequence, record in rows]

    def append_audit(self, event: AuditEvent) -> int:
        with self._connect() as db:
            cursor = db.execute("INSERT INTO dashboard_audit(record) VALUES (?)", (self.codec.dumps(event.model_dump(mode="json")),))
            return int(cursor.lastrowid)

    def create_conversation(self, conversation_id: str, actor: str, agent_id: str | None) -> ConversationRecord:
        now = datetime.now(UTC)
        conversation = ConversationRecord(
            id=conversation_id,
            actor=actor,
            agent_id=agent_id,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO dashboard_conversations(id, record) VALUES (?, ?)",
                (conversation.id, self.codec.dumps(conversation.model_dump(mode="json"))),
            )
        return conversation

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT record FROM dashboard_conversations WHERE id=?", (conversation_id,)
            ).fetchone()
        return ConversationRecord.model_validate(self.codec.loads(row[0])) if row else None

    def list_conversations(self, actor: str, limit: int = 100) -> list[ConversationRecord]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT record FROM dashboard_conversations ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            conversation
            for row in rows
            if (conversation := ConversationRecord.model_validate(self.codec.loads(row[0]))).actor == actor
        ]

    def append_message(
        self,
        message_id: str,
        conversation_id: str,
        role: Literal["user", "assistant", "system"],
        content: str,
        provider_id: str | None = None,
        complete: bool = True,
    ) -> MessageRecord:
        message = MessageRecord(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            provider_id=provider_id,
            created_at=datetime.now(UTC),
            complete=complete,
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO dashboard_messages(conversation_id, record) VALUES (?, ?)",
                (conversation_id, self.codec.dumps(message.model_dump(mode="json"))),
            )
            db.execute(
                "UPDATE dashboard_conversations SET record=? WHERE id=?",
                (
                    self.codec.dumps(
                        self.get_conversation(conversation_id)
                        .model_copy(update={"updated_at": message.created_at})
                        .model_dump(mode="json")
                    ),
                    conversation_id,
                ),
            )
        return message

    def list_messages(
        self, conversation_id: str, after: int = 0, limit: int = 100
    ) -> tuple[list[MessageRecord], int]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT sequence, record FROM dashboard_messages "
                "WHERE conversation_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (conversation_id, after, limit),
            ).fetchall()
        return (
            [MessageRecord.model_validate(self.codec.loads(record)) for _, record in rows],
            rows[-1][0] if rows else after,
        )

    def set_setting(self, key: str, value: str) -> SettingsRecord:
        setting = SettingsRecord(key=key, value=value)
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO dashboard_settings(key, record) VALUES (?, ?)",
                (key, self.codec.dumps(setting.model_dump(mode="json"))),
            )
        return setting

    def get_setting(self, key: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT record FROM dashboard_settings WHERE key=?", (key,)
            ).fetchone()
        return SettingsRecord.model_validate(self.codec.loads(row[0])).value if row else None
