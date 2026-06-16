import importlib
import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "mod",
    [
        "agent.tools.schemas",
        "agent.tools.gemini_client",
        "agent.tools.fetcher",
        "agent.tools.storage",
        "agent.tools.svg_renderer",
        "agent.tools.pipeline",
        "agent.tools.prompts",
    ],
)
def test_imports(mod):
    assert importlib.import_module(mod) is not None
