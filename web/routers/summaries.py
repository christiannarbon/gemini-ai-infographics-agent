from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from web.runtime import (
    _create_job,
    _run_summary_job,
    _schedule_background_task,
)

router = APIRouter()


@router.post("/summaries", response_class=HTMLResponse)
async def summarize(request: Request, url: str = Form(...)) -> HTMLResponse:
    job = _create_job(request.app, "summary", "Summarizing article...")
    _schedule_background_task(
        request.app, _run_summary_job(request.app, job.job_id, url)
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )
