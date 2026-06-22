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


def _is_auth_exempt_path(path: str) -> bool:
    return path in {"/login", "/healthz"} or path.startswith("/static/")


def _safe_next_path(path: str) -> str:
    # Minimal open redirect guard: only same-origin absolute paths are allowed.
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/"
    if path.startswith("/login"):
        return "/"
    return path
