from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.agent_client import AgentClient
from web.dependencies import get_templates, get_agent_client

from web.runtime import (
    _create_job,
    _run_summary_job,
    _schedule_background_task,
)

router = APIRouter()


@router.post("/summaries", response_class=HTMLResponse)
async def summarize(
    request: Request,
    url: str = Form(...),
    agent_client: AgentClient = Depends(get_agent_client),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    job = _create_job(request.app, "summary", "Summarizing article...")
    _schedule_background_task(
        request.app, _run_summary_job(request.app, job.job_id, url, agent_client)
    )
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )
