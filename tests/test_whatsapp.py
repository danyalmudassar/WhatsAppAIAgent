import httpx

from app.config import Settings
from app.contracts import OutgoingMessage
from app.whatsapp import MockWhatsAppAdapter, OfficialWhatsAppAdapter


def test_mock_adapter_round_trip():
    adapter = MockWhatsAppAdapter()
    incoming = adapter.parse({"id": "w-1", "from": "self", "text": "hello"})
    assert incoming.source == "whatsapp"
    assert adapter.serialize(OutgoingMessage(message_id="w-1", text="jawab"))["text"] == "jawab"


def test_official_adapter_parses_documented_text_message():
    settings = Settings(
        _env_file=None,
        memory_key="secret",
        whatsapp_enabled=True,
        whatsapp_api_key="key",
    )
    adapter = OfficialWhatsAppAdapter(settings)
    message = adapter.parse(
        {
            "id": "wamid.1",
            "from": "user:50972923564215",
            "timestamp": "1736844652",
            "type": "text",
            "text": {"body": "salam"},
        }
    )
    assert message.sender_id == "user:50972923564215"
    assert message.text == "salam"
    assert adapter._headers()["Authorization"].startswith("Bearer ")


def test_duplicate_message_response_is_idempotent():
    response = httpx.Response(
        409,
        json={"error": {"code": OfficialWhatsAppAdapter.DUPLICATE_REQUEST_CODE}},
    )
    OfficialWhatsAppAdapter._raise_for_unhandled_error(response)
