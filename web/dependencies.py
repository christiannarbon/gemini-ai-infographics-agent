from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.templating import Jinja2Templates

from web.agent_client import AgentClient, build_agent_client

if TYPE_CHECKING:
    from web.services.jobs import JobStore
    from web.services.runner import JobRunner
    from web.services.sessions import (
        SessionInfographicsDictWrapper,
        SessionSummaryDictWrapper,
    )


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


def get_jobs(request: Request) -> JobStore:
    return request.app.state.job_store


def get_infographics_cache(request: Request) -> SessionInfographicsDictWrapper:
    return request.app.state.infographics_cache


def get_sessions(request: Request) -> SessionSummaryDictWrapper:
    return request.app.state.sessions


def get_job_runner(request: Request) -> JobRunner:
    if (
        not hasattr(request.app.state, "job_runner")
        or request.app.state.job_runner is None
    ):
        from web.services.runner import JobRunner

        agent_client = get_agent_client(request)
        request.app.state.job_runner = JobRunner(
            agent_client=agent_client,
            job_store=request.app.state.job_store,
            session_store=request.app.state.session_store,
        )
    return request.app.state.job_runner
