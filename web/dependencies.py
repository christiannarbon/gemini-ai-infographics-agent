from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.templating import Jinja2Templates

from web.agent_client import AgentClient, build_agent_client

if TYPE_CHECKING:
    from agent.models import GraphicResult
    from web.runtime import AgentJob


def get_agent_client(request: Request) -> AgentClient:
    # Lazily builds the client if missing, mirroring lifespan for lifespan-less TestClient usage in tests
    if (
        not hasattr(request.app.state, "agent_client")
        or request.app.state.agent_client is None
    ):
        request.app.state.agent_client = build_agent_client()
    return request.app.state.agent_client


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def get_jobs(request: Request) -> dict[str, AgentJob]:
    return request.app.state.jobs


def get_infographics_cache(request: Request) -> dict[str, GraphicResult]:
    return request.app.state.infographics_cache
