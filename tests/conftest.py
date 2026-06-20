import sys
from pathlib import Path

# Add project root directory to sys.path
root_dir = str(Path(__file__).parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import pytest  # noqa: E402
from agent.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch):
    """Autouse fixture to automatically clear Settings cache between tests and on env modifications."""
    get_settings.cache_clear()

    orig_setenv = monkeypatch.setenv
    orig_delenv = monkeypatch.delenv

    def setenv_wrapper(*args, **kwargs):
        orig_setenv(*args, **kwargs)
        get_settings.cache_clear()

    def delenv_wrapper(*args, **kwargs):
        orig_delenv(*args, **kwargs)
        get_settings.cache_clear()

    monkeypatch.setenv = setenv_wrapper
    monkeypatch.delenv = delenv_wrapper

    # 1. Isolate environment
    env_vars_to_del = [
        "APP_PASSWORD",
        "APP_SECRET_KEY",
        "GCS_BUCKET",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
    ]
    for var in env_vars_to_del:
        monkeypatch.delenv(var, raising=False)

    import os

    for var in list(os.environ.keys()):
        if var.startswith("AGENT_RUNTIME_"):
            monkeypatch.delenv(var, raising=False)

    # 2. Set safe defaults
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("AGENT_BACKEND", "local")
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")

    yield
    get_settings.cache_clear()
