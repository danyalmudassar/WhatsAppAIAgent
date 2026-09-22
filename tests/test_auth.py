from app.auth import active_session, create_session, hash_password, verify_password
from app.dashboard_store import DashboardStore


def test_password_hash_and_session_lifecycle(tmp_path):
    encoded = hash_password("correct")
    assert verify_password("correct", encoded)
    assert not verify_password("wrong", encoded)
    store = DashboardStore(tmp_path / "memory.db", "secret")
    token = create_session(store, "admin", 3600)
    assert active_session(store, token).actor == "admin"
