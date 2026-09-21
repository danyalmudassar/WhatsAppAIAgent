from app.security import EncryptedCodec, redact_contact_fields


def test_encrypted_codec_round_trips_and_hides_plaintext():
    codec = EncryptedCodec("unit-test-secret")
    token = codec.encrypt(b'{"phone":"03105287479"}')
    assert token != b'{"phone":"03105287479"}'
    assert codec.decrypt(token) == b'{"phone":"03105287479"}'


def test_contact_fields_are_redacted_by_default():
    assert redact_contact_fields({"name": "Danyal", "email": "x@example.com"}) == {
        "name": "Danyal",
        "email": "[protected]",
    }
