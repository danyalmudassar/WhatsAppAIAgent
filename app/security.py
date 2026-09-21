import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class DecryptionError(ValueError):
    pass


class EncryptedCodec:
    def __init__(self, secret: str):
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"personal-agent-v1", iterations=390_000)
        self._fernet = Fernet(__import__("base64").urlsafe_b64encode(kdf.derive(secret.encode())))

    def encrypt(self, value: bytes) -> bytes:
        return self._fernet.encrypt(value)

    def decrypt(self, value: bytes) -> bytes:
        try:
            return self._fernet.decrypt(value)
        except InvalidToken as exc:
            raise DecryptionError("memory decryption failed") from exc

    def dumps(self, value: Any) -> bytes:
        return self.encrypt(json.dumps(value, ensure_ascii=False).encode())

    def loads(self, value: bytes) -> Any:
        return json.loads(self.decrypt(value))


def redact_contact_fields(profile: dict[str, object]) -> dict[str, object]:
    protected = {"email", "phone", "whatsapp", "address"}
    return {key: "[protected]" if key.lower() in protected else value for key, value in profile.items()}


def require_confirmation(action: str, confirmed: bool) -> bool:
    return bool(action.strip()) and confirmed
