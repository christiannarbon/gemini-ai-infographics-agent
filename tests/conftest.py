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

    yield
    get_settings.cache_clear()
