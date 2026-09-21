from app.memory import MemoryStore


def test_profile_is_encrypted_and_contact_fields_are_protected(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", "memory-secret")
    store.save_profile({"name": "Danyal", "email": "danyal@example.com"})
    assert store.get_profile(include_contacts=False) == {"name": "Danyal", "email": "[protected]"}
    assert b"danyal@example.com" not in (tmp_path / "memory.db").read_bytes()


def test_memory_can_be_forgotten_and_exported(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", "memory-secret")
    store.save_preference("language", "roman_urdu")
    assert store.export_json()["preferences"]["language"] == "roman_urdu"
    store.forget("preferences")
    assert store.export_json()["preferences"] == {}


def test_whatsapp_offset_is_encrypted_and_persistent(tmp_path):
    path = tmp_path / "memory.db"
    first = MemoryStore(path, "memory-secret")
    first.save_offset(42)
    second = MemoryStore(path, "memory-secret")
    assert second.get_offset() == 42
    assert b"42" not in path.read_bytes()
