from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from agent.models import GraphicResult, ProgressStep, SummaryResult
from web.agent_client import AgentClient

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


def _get_summary(app: FastAPI, session_id: str) -> SummaryResult:
    summary = app.state.sessions.get(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Session not found")
    return summary


def _create_job(
    app: FastAPI, kind: JobKind, title: str, feedback: str = ""
) -> AgentJob:
    job_id = f"{kind}-{uuid4().hex}"
    job = AgentJob(job_id=job_id, kind=kind, title=title, feedback=feedback)
    app.state.jobs[job_id] = job
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


def _schedule_background_task(app: FastAPI, coro) -> None:
    task = asyncio.create_task(coro)
    app.state.background_tasks.add(task)
    task.add_done_callback(app.state.background_tasks.discard)


async def _run_summary_job(
    app: FastAPI, job_id: str, url: str, agent_client: AgentClient
) -> None:
    job = app.state.jobs[job_id]
    started = time.perf_counter()

    async def update_progress(progress: list) -> None:
        job.progress = progress

    try:
        summary = await agent_client.summarize_url(url, on_progress=update_progress)
    except Exception as exc:
        logger.exception("Summary job failed: job_id=%s url=%s", job_id, url)
        job.status = "failed"
        job.error = _display_error(exc)
        return

    app.state.sessions[summary.session_id] = summary
    job.summary = summary
    job.progress = summary.progress
    job.status = "done"
    _log_job_duration("summary", job_id, started)


async def _run_infographics_job(
    app: FastAPI,
    job_id: str,
    summary: SummaryResult,
    feedback: str,
    agent_client: AgentClient,
) -> None:
    job = app.state.jobs[job_id]
    job.summary = summary
    started = time.perf_counter()

    async def update_progress(progress: list) -> None:
        job.progress = progress

    try:
        if feedback:
            infographics = await agent_client.regenerate_infographics(
                summary,
                feedback,
                on_progress=update_progress,
            )
        else:
            infographics = await agent_client.generate_infographics(
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

    app.state.infographics_cache[summary.session_id] = infographics
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


def _log_job_duration(kind: JobKind, job_id: str, started: float) -> None:
    logger.info(
        "job_duration kind=%s job_id=%s elapsed_seconds=%.3f",
        kind,
        job_id,
        time.perf_counter() - started,
    )
