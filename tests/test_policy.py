import pytest

from app.policy import apply_response_policy


def test_policy_does_not_add_an_artificial_prefix():
    assert apply_response_policy("The deployment is ready.") == "The deployment is ready."


def test_policy_preserves_natural_roman_urdu():
    text = "Aap ka deployment ready hai. Logs check karne ke liye command chalayein."
    assert apply_response_policy(text) == text


def test_policy_preserves_technical_values_and_citations():
    text = "Service restart ho gayi hai: railway service restart --service svc-123"
    result = apply_response_policy(text, ("https://example.com/status",))
    assert "railway service restart --service svc-123" in result
    assert "https://example.com/status" in result


def test_policy_truncates_at_word_boundary():
    result = apply_response_policy("Aap ka service status ready hai aur worker bhi chal raha hai.", max_chars=32)
    assert len(result) <= 35
    assert result.endswith("...")
    assert not result[:-3].endswith(" ")


@pytest.mark.parametrize("text", ["Yeh theek hai.", "Roman Urdu mein jawab dein."])
def test_policy_keeps_latin_script_output(text):
    result = apply_response_policy(text)
    assert not any("\u0600" <= character <= "\u06ff" for character in result)


def test_policy_preserves_citations():
    text = apply_response_policy("Aap ka jawab tayyar hai.", ("https://example.com",))
    assert "https://example.com" in text
