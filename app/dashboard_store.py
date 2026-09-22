import hashlib
import sqlite3
from pathlib import Path

from app.dashboard_models import (
    AgentConfig,
    AuditEvent,
    ProviderConfig,
    RuntimeEvent,
    SessionRecord,
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
