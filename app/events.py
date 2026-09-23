import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

from app.dashboard_models import RuntimeEvent
from app.dashboard_store import DashboardStore


class EventRecorder:
    def __init__(self, store: DashboardStore, max_payload_chars: int = 2000):
        self.store = store
        self.max_payload_chars = max_payload_chars
        self._subscribers: set[asyncio.Queue[tuple[int, RuntimeEvent]]] = set()

    def record(self, event_type: str, correlation_id: str, payload: dict[str, object] | None = None) -> RuntimeEvent:
        safe_payload: dict[str, object] = {}
        for key, value in (payload or {}).items():
            if any(secret in key.lower() for secret in ("key", "token", "password", "authorization")):
                safe_payload[key] = "[redacted]"
            else:
                safe_payload[key] = str(value)[: self.max_payload_chars]
        from datetime import UTC, datetime

        event = RuntimeEvent(
            id=str(uuid4()),
            timestamp=datetime.now(UTC),
            type=event_type,
            correlation_id=correlation_id,
            payload=safe_payload,
        )
        sequence = self.store.append_event(event)
        for subscriber in list(self._subscribers):
            subscriber.put_nowait((sequence, event))
        return event

    async def subscribe(self, cursor: int = 0) -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[int, RuntimeEvent]] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            for sequence, event in self.store.events_after(cursor):
                yield self._format(sequence, event)
            while True:
                sequence, event = await queue.get()
                yield self._format(sequence, event)
        finally:
            self._subscribers.discard(queue)

    @staticmethod
    def _format(sequence: int, event: RuntimeEvent) -> str:
        return f"id: {sequence}\nevent: {event.type}\ndata: {json.dumps(event.model_dump(mode='json'))}\n\n"
