from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from web.dependencies import (
    get_templates,
    get_infographics_cache,
    get_job_runner,
    get_sessions,
)
from web.runtime import (
    _apply_summary_edits,
    _download_filename,
    _get_summary,
)
from web.views.progress import JobView

if TYPE_CHECKING:
    from web.services.runner import JobRunner
    from web.services.sessions import (
        SessionInfographicsDictWrapper,
        SessionSummaryDictWrapper,
    )

router = APIRouter()


@router.post("/infographics", response_class=HTMLResponse)
async def create_infographics(
    request: Request,
    session_id: str = Form(...),
    summary_text: str = Form(""),
    key_points_text: str = Form(""),
    job_runner: JobRunner = Depends(get_job_runner),
    templates: Jinja2Templates = Depends(get_templates),
    sessions: SessionSummaryDictWrapper = Depends(get_sessions),
) -> HTMLResponse:
    summary = _get_summary(sessions, session_id)
    _apply_summary_edits(summary, summary_text, key_points_text)
    job = job_runner.start_infographics(summary, feedback="")
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": JobView(job)},
    )


@router.post("/infographics/regenerate", response_class=HTMLResponse)
async def regenerate_infographics(
    request: Request,
    session_id: str = Form(...),
    feedback: str = Form(""),
    job_runner: JobRunner = Depends(get_job_runner),
    templates: Jinja2Templates = Depends(get_templates),
    sessions: SessionSummaryDictWrapper = Depends(get_sessions),
) -> HTMLResponse:
    summary = _get_summary(sessions, session_id)
    job = job_runner.start_infographics(summary, feedback=feedback)
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": JobView(job)},
    )


@router.get("/infographics/{session_id}/download")
async def download_infographics(
    request: Request,
    session_id: str,
    infographics_cache: SessionInfographicsDictWrapper = Depends(
        get_infographics_cache
    ),
) -> FileResponse:
    infographics = infographics_cache.get(session_id)
    if not infographics:
        raise HTTPException(status_code=404, detail="Infographics not found")

    artifact_path = Path(infographics.artifact_path)
    if not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(
        artifact_path,
        media_type=infographics.artifact_mime_type,
        filename=_download_filename(infographics),
    )
