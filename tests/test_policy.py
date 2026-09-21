from app.policy import apply_response_policy


def test_policy_preserves_citations():
    text = apply_response_policy("Aap ka jawab tayyar hai.", ("https://example.com",))
    assert "https://example.com" in text
