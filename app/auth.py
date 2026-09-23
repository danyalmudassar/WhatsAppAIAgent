import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from app.dashboard_models import SessionRecord
from app.dashboard_store import DashboardStore


def verify_password(password: str, encoded: str) -> bool:
    if not encoded:
        return hmac.compare_digest(password, "")
    try:
        algorithm, salt, expected = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except ValueError:
        return False


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()
    return f"scrypt${salt.hex()}${digest}"


def create_session(store: DashboardStore, actor: str, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(32)
    store.create_session(
        SessionRecord(
            id=token,
            actor=actor,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
    )
    return token


def active_session(store: DashboardStore, token: str | None) -> SessionRecord | None:
    if not token:
        return None
    record = store.get_session(token)
    if not record or record.revoked or record.expires_at <= datetime.now(UTC):
        return None
    return record
