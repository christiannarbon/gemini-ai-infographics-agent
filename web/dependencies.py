from __future__ import annotations

from typing import Any
from fastapi import Request
from agent.config import get_settings as _get_settings, Settings
from web.agent_client import AgentClient
from fastapi.templating import Jinja2Templates


def get_agent_client(request: Request) -> AgentClient:
    if (
        not hasattr(request.app.state, "agent_client")
        or request.app.state.agent_client is None
    ):
        from web.agent_client import build_agent_client

        request.app.state.agent_client = build_agent_client()
    return request.app.state.agent_client


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def get_settings() -> Settings:
    return _get_settings()


def get_job_store(request: Request) -> dict[str, Any]:
    return request.app.state.job_store


def get_session_store(request: Request) -> dict[str, Any]:
    return request.app.state.session_store


def get_infographics_cache(request: Request) -> dict[str, Any]:
    return request.app.state.infographics_cache


def get_background_tasks(request: Request) -> set:
    return request.app.state.background_tasks
