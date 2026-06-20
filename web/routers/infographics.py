from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from web.agent_client import AgentClient
from web.dependencies import get_templates, get_agent_client, get_infographics_cache

from web.runtime import (
    _apply_summary_edits,
    _create_job,
    _download_filename,
    _get_summary,
    _run_infographics_job,
    _schedule_background_task,
)

router = APIRouter()


@router.post("/infographics", response_class=HTMLResponse)
async def create_infographics(
    request: Request,
    session_id: str = Form(...),
    summary_text: str = Form(""),
    key_points_text: str = Form(""),
    agent_client: AgentClient = Depends(get_agent_client),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    summary = _get_summary(request.app, session_id)
    _apply_summary_edits(summary, summary_text, key_points_text)
    job = _create_job(request.app, "infographics", "Generating infographics...")
    _schedule_background_task(
        request.app,
        _run_infographics_job(
            request.app, job.job_id, summary, feedback="", agent_client=agent_client
        ),
    )
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )


@router.post("/infographics/regenerate", response_class=HTMLResponse)
async def regenerate_infographics(
    request: Request,
    session_id: str = Form(...),
    feedback: str = Form(""),
    agent_client: AgentClient = Depends(get_agent_client),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    summary = _get_summary(request.app, session_id)
    job = _create_job(
        request.app, "infographics", "Applying feedback...", feedback=feedback
    )
    _schedule_background_task(
        request.app,
        _run_infographics_job(
            request.app,
            job.job_id,
            summary,
            feedback=feedback,
            agent_client=agent_client,
        ),
    )
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )


@router.get("/infographics/{session_id}/download")
async def download_infographics(
    request: Request,
    session_id: str,
    infographics_cache: dict = Depends(get_infographics_cache),
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
