from app.memory import MemoryStore
from app.tools import build_tool_registry


def test_profile_tool_masks_contact_fields_by_default(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db", "secret")
    memory.save_profile({"email": "x@example.com"})
    result = build_tool_registry(memory)["profile_lookup"].invoke({"field": "email", "confirmed": False})
    assert result.content == "[protected]"


def test_github_write_requires_confirmation(tmp_path):
    registry = build_tool_registry(MemoryStore(tmp_path / "memory.db", "secret"))
    result = registry["github_write"].invoke({"operation": "comment", "payload": "hello", "confirmed": False})
    assert result.error_code == "confirmation_required"
