from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from typing import TYPE_CHECKING

from agent.models import GraphicResult, SummaryResult

if TYPE_CHECKING:
    from web.services.sessions import SessionSummaryDictWrapper


def _get_summary(sessions: SessionSummaryDictWrapper, session_id: str) -> SummaryResult:
    summary = sessions.get(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Session not found")
    return summary


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


def _apply_summary_edits(
    summary: SummaryResult, summary_text: str, key_points_text: str
) -> None:
    summary_lines = [line.strip() for line in summary_text.splitlines() if line.strip()]
    key_points = [line.strip() for line in key_points_text.splitlines() if line.strip()]
    if summary_lines:
        summary.summary_lines = summary_lines[:3]
    if key_points:
        summary.key_points = key_points[:6]


def _is_auth_exempt_path(path: str) -> bool:
    return path in {"/login", "/healthz"} or path.startswith("/static/")


def _safe_next_path(path: str) -> str:
    # Minimal open redirect guard: only same-origin absolute paths are allowed.
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/"
    if path.startswith("/login"):
        return "/"
    return path
