import sys
from pathlib import Path

# Add project root directory to sys.path
root_dir = str(Path(__file__).parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import pytest  # noqa: E402
from agent.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Autouse fixture to automatically clear Settings cache between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
