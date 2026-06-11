from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent.config import get_settings
from agent.models import GraphicResult, ProgressStep, SummaryResult
from agent.tools import close_genai_client
from web.auth import (
    AUTH_COOKIE_NAME,
    assert_auth_config,
    auth_enabled,
    cookie_max_age,
    create_auth_cookie,
    password_matches,
    request_is_authenticated,
)
from web.agent_client import build_agent_client
from web.logging_config import configure_logging


BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
JobKind = Literal["summary", "infographics"]
JobStatus = Literal["running", "done", "failed"]


@dataclass
class AgentJob:
    job_id: str
    kind: JobKind
    title: str
    status: JobStatus = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    progress: list = field(default_factory=list)
    summary: Optional[SummaryResult] = None
    infographics: Optional[GraphicResult] = None
    feedback: str = ""
    error: str = ""

    @property
    def elapsed_seconds(self) -> int:
        return max(
            0, int((datetime.now(timezone.utc) - self.started_at).total_seconds())
        )

    @property
    def wait_hint(self) -> str:
        if self.kind == "infographics":
            return "Image generation may take 1 to 3 minutes. The screen will automatically refresh."
        return "Article retrieval and summarization may take 30 to 90 seconds. The screen will automatically refresh."

    @property
    def slow_after_seconds(self) -> int:
        if self.kind == "infographics":
            return 240
        return 120

    @property
    def is_slow(self) -> bool:
        return (
            self.status == "running" and self.elapsed_seconds >= self.slow_after_seconds
        )

    @property
    def slow_message(self) -> str:
        if self.kind == "infographics":
            return "Image generation is taking longer than usual. If this continues for a few minutes, check the Agent Runtime logs and Gemini image model quota."
        return "Summarization is taking longer than usual. If this continues for a few minutes, check if the URL content can be retrieved and check the Agent Runtime logs."

    @property
    def show_estimated_progress(self) -> bool:
        return self.status == "running" and len(self.progress) <= 1

    @property
    def estimated_progress(self) -> list[ProgressStep]:
        if not self.show_estimated_progress:
            return []
        if self.kind == "infographics":
            milestones = [
                (0, "Sending summary to Agent Runtime"),
                (10, "Agent deciding style and layout plan"),
                (30, "Generating image with Gemini"),
                (80, "Saving artifacts to Cloud Storage"),
                (105, "Preparing signed URL and returning response"),
            ]
        else:
            milestones = [
                (0, "Sending summarization workflow to Agent Runtime"),
                (12, "Retrieving article body"),
                (35, "Generating 3-line summary and key points"),
                (60, "Verifying JSON contract and returning response"),
            ]
        return _estimated_progress_steps(self.elapsed_seconds, milestones)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_client
    configure_logging()
    assert_auth_config()
    agent_client = build_agent_client()
    yield
    close_genai_client()
    agent_client = None


app = FastAPI(title="Infographics Agent Demo", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount(
    "/artifacts",
    StaticFiles(directory=Path(get_settings().artifact_dir)),
    name="artifacts",
)

templates = Jinja2Templates(directory=BASE_DIR / "templates")
agent_client = None

sessions: dict[str, SummaryResult] = {}
infographics_cache: dict[str, GraphicResult] = {}
jobs: dict[str, AgentJob] = {}
background_tasks: set[asyncio.Task] = set()


@app.middleware("http")
async def require_password_auth(request: Request, call_next) -> Response:
    if _is_auth_exempt_path(request.url.path) or request_is_authenticated(request):
        return await call_next(request)

    if request.method == "GET":
        return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)
    return PlainTextResponse(
        "Authentication required",
        status_code=401,
        headers={"HX-Redirect": "/login"},
    )


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    return "ok"


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = "/") -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_path": _safe_next_path(next), "error": ""},
    )


@app.post("/login")
async def login(
    request: Request,
    password: str = Form(...),
    next_path: str = Form("/"),
) -> Response:
    next_url = _safe_next_path(next_path)
    if not auth_enabled():
        return RedirectResponse(url=next_url, status_code=303)
    if not password_matches(password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next_path": next_url,
                "error": "Incorrect password.",
            },
            status_code=401,
        )

    response = RedirectResponse(url=next_url, status_code=303)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        create_auth_cookie(),
        max_age=cookie_max_age(),
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return response


@app.post("/logout")
async def logout() -> Response:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"auth_enabled": auth_enabled()},
    )


@app.post("/summaries", response_class=HTMLResponse)
async def summarize(request: Request, url: str = Form(...)) -> HTMLResponse:
    job = _create_job("summary", "Summarizing article...")
    _schedule_background_task(_run_summary_job(job.job_id, url))
    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )


@app.post("/infographics", response_class=HTMLResponse)
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


@app.post("/infographics/regenerate", response_class=HTMLResponse)
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


@app.get("/infographics/{session_id}/download")
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


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def poll_job(request: Request, job_id: str) -> HTMLResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "done" and job.kind == "summary" and job.summary:
        return _retarget_job_response(
            templates.TemplateResponse(
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
            templates.TemplateResponse(
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
            templates.TemplateResponse(
                request,
                "partials/job.html",
                {"job": job},
            ),
            job.job_id,
            request,
        )

    if request.headers.get("HX-Target") == f"{job.job_id}-content":
        return templates.TemplateResponse(
            request,
            "partials/job_content.html",
            {"job": job},
        )

    return templates.TemplateResponse(
        request,
        "partials/job.html",
        {"job": job},
    )


def _get_summary(session_id: str) -> SummaryResult:
    summary = sessions.get(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Session not found")
    return summary


def _create_job(kind: JobKind, title: str, feedback: str = "") -> AgentJob:
    job_id = f"{kind}-{uuid4().hex}"
    job = AgentJob(job_id=job_id, kind=kind, title=title, feedback=feedback)
    jobs[job_id] = job
    return job


def _retarget_job_response(
    response: HTMLResponse, job_id: str, request: Request
) -> HTMLResponse:
    if request.headers.get("HX-Request") == "true":
        response.headers["HX-Retarget"] = f"#{job_id}"
        response.headers["HX-Reswap"] = "outerHTML"
    return response


def _download_filename(infographics: GraphicResult) -> str:
    suffix = Path(infographics.artifact_path).suffix or ".bin"
    return f"infographics-{infographics.session_id[:8]}{suffix}"


def _schedule_background_task(coro) -> None:
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def _run_summary_job(job_id: str, url: str) -> None:
    job = jobs[job_id]
    started = time.perf_counter()

    async def update_progress(progress: list) -> None:
        job.progress = progress

    try:
        summary = await _agent_client().summarize_url(url, on_progress=update_progress)
    except Exception as exc:
        logger.exception("Summary job failed: job_id=%s url=%s", job_id, url)
        job.status = "failed"
        job.error = _display_error(exc)
        return

    sessions[summary.session_id] = summary
    job.summary = summary
    job.progress = summary.progress
    job.status = "done"
    _log_job_duration("summary", job_id, started)


async def _run_infographics_job(
    job_id: str, summary: SummaryResult, feedback: str
) -> None:
    job = jobs[job_id]
    job.summary = summary
    started = time.perf_counter()

    async def update_progress(progress: list) -> None:
        job.progress = progress

    try:
        if feedback:
            infographics = await _agent_client().regenerate_infographics(
                summary,
                feedback,
                on_progress=update_progress,
            )
        else:
            infographics = await _agent_client().generate_infographics(
                summary,
                on_progress=update_progress,
            )
    except Exception as exc:
        logger.exception(
            "Infographics job failed: job_id=%s session_id=%s",
            job_id,
            summary.session_id,
        )
        job.status = "failed"
        job.error = _display_error(exc)
        return

    infographics_cache[summary.session_id] = infographics
    job.infographics = infographics
    job.progress = infographics.progress
    job.status = "done"
    _log_job_duration("infographics", job_id, started)


def _apply_summary_edits(
    summary: SummaryResult, summary_text: str, key_points_text: str
) -> None:
    summary_lines = [line.strip() for line in summary_text.splitlines() if line.strip()]
    key_points = [line.strip() for line in key_points_text.splitlines() if line.strip()]
    if summary_lines:
        summary.summary_lines = summary_lines[:3]
    if key_points:
        summary.key_points = key_points[:6]


def _display_error(exc: Exception) -> str:
    raw_message = str(exc).strip()
    technical_detail = raw_message or f"{type(exc).__name__}: {exc!r}"
    friendly_message = _friendly_error_message(technical_detail)
    if friendly_message == technical_detail:
        return friendly_message
    return f"{friendly_message}\nTechnical Details: {technical_detail}"


def _friendly_error_message(message: str) -> str:
    normalized = message.lower()
    if "project_number" in normalized or "resource_id" in normalized:
        return "A placeholder remains in the Agent Runtime resource name. Set AGENT_RUNTIME_RESOURCE_NAME to the actual projects/.../reasoningEngines/... value and redeploy Cloud Run."
    if "publisher model" in normalized or (
        "model" in normalized and "404" in normalized
    ):
        return "Gemini model not found. Check the model ID and GOOGLE_CLOUD_LOCATION=global settings."
    if (
        "signed url" in normalized
        or "signblob" in normalized
        or "serviceaccounttokencreator" in normalized
    ):
        return "Insufficient permissions to generate the signed URL for the image. Please re-run scripts/runtime-iam-config.sh."
    if "permission" in normalized or "403" in normalized or "denied" in normalized:
        return "Insufficient Google Cloud permissions. Check IAM configurations for Cloud Run, Agent Runtime, and Cloud Storage."
    if (
        "agent runtime returned no workflow response" in normalized
        or "assertionerror" in normalized
    ):
        return "Agent Runtime did not return the expected response format. Check the Runtime logs."
    if "gcs_bucket is required" in normalized:
        return "The destination bucket for generated images is not set. Set GCS_BUCKET and redeploy Runtime."
    if "exceeds" in normalized and "bytes" in normalized:
        return "Retrieving stopped because the article body is too large. Try another article URL."
    if "url" in normalized or "fetch" in normalized or "article" in normalized:
        return "Could not retrieve the article body. Try a publicly accessible article URL, or another URL."
    return message


def _estimated_progress_steps(
    elapsed_seconds: int, milestones: list[tuple[int, str]]
) -> list[ProgressStep]:
    steps: list[ProgressStep] = []
    for index, (starts_at, label) in enumerate(milestones):
        next_starts_at = (
            milestones[index + 1][0] if index + 1 < len(milestones) else None
        )
        if elapsed_seconds < starts_at:
            status = "pending"
        elif next_starts_at is not None and elapsed_seconds >= next_starts_at:
            status = "done"
        else:
            status = "running"
        detail = "Estimated step. The actual result will be reflected after Agent Runtime completes."
        steps.append(ProgressStep(label, status, detail))
    return steps


def _is_auth_exempt_path(path: str) -> bool:
    return path in {"/login", "/healthz"} or path.startswith("/static/")


def _safe_next_path(path: str) -> str:
    # Minimal open redirect guard: only same-origin absolute paths are allowed.
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/"
    if path.startswith("/login"):
        return "/"
    return path


def _agent_client():
    global agent_client
    if agent_client is None:
        agent_client = build_agent_client()
    return agent_client


def _log_job_duration(kind: JobKind, job_id: str, started: float) -> None:
    logger.info(
        "job_duration kind=%s job_id=%s elapsed_seconds=%.3f",
        kind,
        job_id,
        time.perf_counter() - started,
    )
