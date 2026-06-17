from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from web.main import (
    _apply_summary_edits,
    _create_job,
    _download_filename,
    _get_summary,
    _run_infographics_job,
    _schedule_background_task,
    infographics_cache,
    templates,
)

router = APIRouter()


@router.post("/infographics", response_class=HTMLResponse)
async def create_infographics(
    request: Request,
    session_id: str = Form(...),
    summary_text: str = Form(""),
    key_points_text: str = Form(""),
) -> HTMLResponse:
    summary = _get_summary(session_id)
    _apply_summary_edits(summary, summary_text, key_points_text)
    job = _create_job("infographics", "Generating infographics...")
    _schedule_background_task(_run_infographics_job(job.job_id, summary, feedback=""))
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
) -> HTMLResponse:
    summary = _get_summary(session_id)
    job = _create_job("infographics", "Applying feedback...", feedback=feedback)
    _schedule_background_task(
        _run_infographics_job(job.job_id, summary, feedback=feedback)
    )
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )


@router.get("/infographics/{session_id}/download")
async def download_infographics(session_id: str) -> FileResponse:
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
