from __future__ import annotations

from web.app import create_app
from web.runtime import (
    AgentJob,  # noqa: F401
    _display_error,  # noqa: F401
)

app = create_app()

jobs = app.state.jobs
infographics_cache = app.state.infographics_cache
