from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from web.runtime import _retarget_job_response

router = APIRouter()


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def poll_job(request: Request, job_id: str) -> HTMLResponse:
    job = request.app.state.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "done" and job.kind == "summary" and job.summary:
        return _retarget_job_response(
            request.app.state.templates.TemplateResponse(
                request,
                "partials/summary.html",
                {"summary": job.summary},
            ),
            job.job_id,
            request,
        )

    if (
        job.status == "done"
        and job.kind == "infographics"
        and job.summary
        and job.infographics
    ):
        return _retarget_job_response(
            request.app.state.templates.TemplateResponse(
                request,
                "partials/infographics.html",
                {
                    "summary": job.summary,
                    "infographics": job.infographics,
                    "feedback": job.feedback,
                },
            ),
            job.job_id,
            request,
        )

    if job.status == "failed":
        return _retarget_job_response(
            request.app.state.templates.TemplateResponse(
                request,
                "partials/job.html",
                {"job": job},
            ),
            job.job_id,
            request,
        )

    if request.headers.get("HX-Target") == f"{job.job_id}-content":
        return request.app.state.templates.TemplateResponse(
            request,
            "partials/job_content.html",
            {"job": job},
        )

    return request.app.state.templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )
