from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web.dependencies import get_templates, get_job_runner

if TYPE_CHECKING:
    from web.services.runner import JobRunner

router = APIRouter()


@router.post("/summaries", response_class=HTMLResponse)
async def summarize(
    request: Request,
    url: str = Form(...),
    job_runner: JobRunner = Depends(get_job_runner),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    job = job_runner.start_summary(url)
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )
