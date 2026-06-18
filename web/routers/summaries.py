from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from web.runtime import (
    _create_job,
    _run_summary_job,
    _schedule_background_task,
    templates,
)

router = APIRouter()


@router.post("/summaries", response_class=HTMLResponse)
async def summarize(request: Request, url: str = Form(...)) -> HTMLResponse:
    job = _create_job("summary", "Summarizing article...")
    _schedule_background_task(_run_summary_job(job.job_id, url))
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )
