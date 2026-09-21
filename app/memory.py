import sqlite3
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.security import EncryptedCodec, redact_contact_fields


class MemoryStore:
    def __init__(self, path: Path, secret: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.codec = EncryptedCodec(secret)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv_memory (category TEXT PRIMARY KEY, value BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS summaries (thread_id TEXT PRIMARY KEY, value BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, value BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS processed_events (event_id TEXT PRIMARY KEY);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save_profile(self, profile: dict[str, object]) -> None:
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO kv_memory VALUES (?, ?)", ("profile", self.codec.dumps(profile)))

    def get_profile(self, include_contacts: bool = False) -> dict[str, object]:
        with self._connect() as db:
            row = db.execute("SELECT value FROM kv_memory WHERE category = 'profile'").fetchone()
        if not row:
            return {}
        profile = self.codec.loads(row[0])
        return profile if include_contacts else redact_contact_fields(profile)

    def save_preference(self, key: str, value: object) -> None:
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?)", (key, self.codec.dumps(value)))

    def save_summary(self, thread_id: str, summary: str) -> None:
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO summaries VALUES (?, ?)", (thread_id, self.codec.dumps(summary)))

    def create_task(self, title: str, due_at: str | None = None) -> str:
        task_id = str(uuid4())
        with self._connect() as db:
            db.execute("INSERT INTO tasks VALUES (?, ?)", (task_id, self.codec.dumps({"id": task_id, "title": title, "due_at": due_at, "status": "open"})))
        return task_id

    def list_tasks(self, status: str = "open") -> list[dict[str, object]]:
        with self._connect() as db:
            rows = db.execute("SELECT value FROM tasks").fetchall()
        return [task for row in rows if (task := self.codec.loads(row[0]))["status"] == status]

    def forget(self, category: Literal["profile", "preferences", "summaries", "tasks"]) -> None:
        table = {"profile": "kv_memory", "preferences": "preferences", "summaries": "summaries", "tasks": "tasks"}[category]
        with self._connect() as db:
            db.execute(f"DELETE FROM {table}")

    def export_json(self) -> dict[str, object]:
        with self._connect() as db:
            profile = db.execute("SELECT value FROM kv_memory WHERE category='profile'").fetchone()
            preferences = db.execute("SELECT key, value FROM preferences").fetchall()
            summaries = db.execute("SELECT thread_id, value FROM summaries").fetchall()
            tasks = db.execute("SELECT value FROM tasks").fetchall()
        return {
            "profile": self.codec.loads(profile[0]) if profile else {},
            "preferences": {key: self.codec.loads(value) for key, value in preferences},
            "summaries": {key: self.codec.loads(value) for key, value in summaries},
            "tasks": [self.codec.loads(value) for value in tasks],
        }

    def mark_event_if_new(self, event_id: str) -> bool:
        with self._connect() as db:
            try:
                db.execute("INSERT INTO processed_events VALUES (?)", (event_id,))
            except sqlite3.IntegrityError:
                return False
        return True

    def get_offset(self) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT value FROM kv_memory WHERE category = 'whatsapp_offset'"
            ).fetchone()
        return int(self.codec.loads(row[0])) if row else 0

    def save_offset(self, offset: int) -> None:
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("WhatsApp offset must be a non-negative integer")
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO kv_memory VALUES (?, ?)",
                ("whatsapp_offset", self.codec.dumps(offset)),
            )
