import pytest
from agent.config import get_settings


@pytest.mark.unit
def test_conftest_client_healthz(client):
    """Smoke test to verify client fixture can communicate with the app."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"


@pytest.mark.unit
def test_conftest_set_env(set_env):
    """Verify that the set_env fixture correctly overrides settings and clears cache."""
    set_env("MOCK_MODE", "false")
    assert get_settings().mock_mode is False

    set_env("MOCK_MODE", "true")
    assert get_settings().mock_mode is True
