from typing import Any, Protocol

import httpx

from app.config import Settings
from app.contracts import IncomingMessage, OutgoingMessage
from app.memory import MemoryStore


class WhatsAppAdapter(Protocol):
    def parse(self, payload: dict[str, object]) -> IncomingMessage: ...
    async def send(self, message: OutgoingMessage) -> dict[str, object]: ...


class MockWhatsAppAdapter:
    def parse(self, payload: dict[str, object]) -> IncomingMessage:
        return IncomingMessage(message_id=str(payload["id"]), sender_id=str(payload["from"]), text=str(payload["text"]), source="whatsapp")

    def serialize(self, message: OutgoingMessage) -> dict[str, object]:
        return message.model_dump()

    async def send(self, message: OutgoingMessage) -> dict[str, object]:
        return self.serialize(message)


class OfficialWhatsAppAdapter:
    def __init__(self, settings: Settings, memory: MemoryStore | None = None):
        if not settings.whatsapp_enabled:
            raise ValueError("WHATSAPP_ENABLED must be true")
        if not settings.whatsapp_api_key:
            raise ValueError("WHATSAPP_API_KEY is required")
        self.settings = settings
        self.memory = memory
        self.offset = memory.get_offset() if memory else 0

    def _headers(self) -> dict[str, str]:
        token = self.settings.whatsapp_api_key.get_secret_value()
        scheme = self.settings.whatsapp_auth_scheme.strip()
        return {
            self.settings.whatsapp_auth_header: f"{scheme} {token}".strip(),
            "Content-Type": "application/json",
        }

    def parse(self, payload: dict[str, object]) -> IncomingMessage:
        message_id = payload.get("id")
        sender_id = payload.get("from")
        message_type = payload.get("type")
        text_payload = payload.get("text")
        text = text_payload.get("body") if isinstance(text_payload, dict) else None
        if message_type != "text" or not all(
            isinstance(value, str) and value for value in (message_id, sender_id, text)
        ):
            raise ValueError("only official text messages are supported")
        return IncomingMessage(
            message_id=message_id,
            sender_id=sender_id,
            text=text,
            source="whatsapp",
            raw_id=message_id,
        )

    async def receive(self, limit: int = 50, timeout: int = 15) -> list[IncomingMessage]:
        params = {"offset": self.offset, "limit": min(max(limit, 1), 100), "timeout": min(max(timeout, 0), 25)}
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            response = await client.get(f"{self.settings.whatsapp_endpoint}/updates", headers=self._headers(), params=params)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return []
        body: dict[str, Any] = response.json()
        messages: list[IncomingMessage] = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    messages.append(self.parse(message))
        if isinstance(body.get("next_offset"), int):
            self.offset = body["next_offset"]
            if self.memory:
                self.memory.save_offset(self.offset)
        return messages

    def update_offset(self, offset: int) -> None:
        self.offset = offset
        if self.memory:
            self.memory.save_offset(offset)

    async def send(self, message: OutgoingMessage) -> dict[str, object]:
        if not message.recipient_id:
            raise ValueError("recipient_id is required for an official WhatsApp reply")
        payload = {
            "messaging_product": "whatsapp",
            "to": message.recipient_id,
            "type": "text",
            "text": {"body": message.text},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.settings.whatsapp_endpoint}/messages",
                headers=self._headers(),
                json=payload,
            )
        response.raise_for_status()
        return response.json()
