from src.config import get_settings, mask_key


def test_provider_switch_defaults():
    s = get_settings()
    parts = s["provider"].split(",")
    assert any(p in ("openrouter", "groq", "gemini") for p in parts)
    assert "masked_keys" in s


def test_mask_key_hides_secret():
    assert mask_key("") == "(missing)"
    assert mask_key("short") == "(missing)"
    m = mask_key("sk-or-v1-abcdef1234567890XXXX4397")
    assert m.startswith("sk-or-")
    assert "abcdef" not in m
