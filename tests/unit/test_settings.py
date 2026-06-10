import pytest
from agent.config import get_settings


@pytest.mark.unit
@pytest.mark.parametrize(
    "env_val,expected",
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("TRUE", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("", False),
    ],
)
def test_settings_truthy_parsing(monkeypatch, env_val, expected):
    monkeypatch.setenv("MOCK_MODE", env_val)
    get_settings.cache_clear()
    s = get_settings()
    assert s.mock_mode is expected


@pytest.mark.unit
def test_settings_invalid_integer_fallback(monkeypatch):
    monkeypatch.setenv("ARTICLE_FETCH_MAX_BYTES", "notanumber")
    get_settings.cache_clear()
    s = get_settings()
    assert s.article_fetch_max_bytes == 2_000_000


@pytest.mark.unit
def test_settings_clamp_boundary(monkeypatch):
    monkeypatch.setenv("ARTICLE_FETCH_MAX_BYTES", "10")
    get_settings.cache_clear()
    s = get_settings()
    assert s.article_fetch_max_bytes == 1024


@pytest.mark.unit
@pytest.mark.parametrize(
    "env_vars,expected",
    [
        ({"GEMINI_API_KEY": "somekey"}, True),
        ({"GOOGLE_API_KEY": "somekey"}, True),
        ({"GOOGLE_GENAI_USE_VERTEXAI": "true"}, True),
        ({}, False),
    ],
)
def test_settings_has_gemini_credentials(monkeypatch, env_vars, expected):
    # Clear credentials env variables first to avoid test runner env pollution
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    for k, v in env_vars.items():
        monkeypatch.setenv(k, v)

    get_settings.cache_clear()
    s = get_settings()
    assert s.has_gemini_credentials is expected
