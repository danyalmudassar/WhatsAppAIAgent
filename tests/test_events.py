import asyncio

from app.dashboard_store import DashboardStore
from app.events import EventRecorder


def test_events_are_redacted_and_cursored(tmp_path):
    recorder = EventRecorder(DashboardStore(tmp_path / "memory.db", "secret"))
    event = recorder.record("config_changed", "c1", {"api_key": "secret", "message": "hello"})
    assert event.payload == {"api_key": "[redacted]", "message": "hello"}
    assert asyncio.run(anext(recorder.subscribe())) .startswith("id: 1")
