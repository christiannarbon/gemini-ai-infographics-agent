from __future__ import annotations

from typing import Any

from agent.actions import (
    generate_infographics,
    regenerate_infographics,
    summarize_url,
)
from agent.errors import ConfigError
from agent.config import get_settings
from agent.models import SummaryResult
from agent.runtime_contract import (
    RuntimeInfographicsPayload,
    RuntimeSummaryPayload,
    RuntimeWorkflowResponse,
    convert_model,
)


async def dispatch_runtime_operation(
    payload: dict[str, Any],
) -> RuntimeWorkflowResponse:
    """Routing entry point for GCP Agent Runtime workflow orchestration."""
    operation = payload.get("operation", "unknown")
    if operation == "summarize_url":
        url = payload.get("url")
        if not url:
            raise ValueError("summarize_url requires a url parameter")
        return await runtime_summarize_url(str(url))
    if operation == "generate_infographics":
        summary = payload.get("summary")
        if not isinstance(summary, dict):
            raise ValueError("generate_infographics requires a summary payload")
        return await runtime_generate_infographics(summary)
    if operation == "regenerate_infographics":
        summary = payload.get("summary")
        if not isinstance(summary, dict):
            raise ValueError("regenerate_infographics requires a summary payload")
        feedback = str(payload.get("feedback") or "")
        return await runtime_regenerate_infographics(summary, feedback)
    raise ValueError(f"Unsupported runtime operation: {operation!r}")


async def runtime_summarize_url(url: str) -> RuntimeWorkflowResponse:
    """Run the deterministic summary workflow and return the runtime JSON contract."""
    summary = await summarize_url(url)
    return RuntimeWorkflowResponse(
        operation="summarize_url",
        summary=convert_model(summary, RuntimeSummaryPayload),
    )


async def runtime_generate_infographics(
    summary: dict[str, Any],
) -> RuntimeWorkflowResponse:
    """Generate an infographics artifact from a summary payload."""
    _assert_runtime_artifact_store()
    # Note: Double-validation via RuntimeSummaryPayload is deliberate to supply permissive defaults for partial payloads.
    summary_result = convert_model(
        RuntimeSummaryPayload.model_validate(summary), SummaryResult
    )
    infographics = await generate_infographics(summary_result)
    return RuntimeWorkflowResponse(
        operation="generate_infographics",
        infographics=convert_model(infographics, RuntimeInfographicsPayload),
    )


async def runtime_regenerate_infographics(
    summary: dict[str, Any], feedback: str = ""
) -> RuntimeWorkflowResponse:
    """Regenerate an infographics artifact from a summary payload and feedback."""
    _assert_runtime_artifact_store()
    # Note: Double-validation via RuntimeSummaryPayload is deliberate to supply permissive defaults for partial payloads.
    summary_result = convert_model(
        RuntimeSummaryPayload.model_validate(summary), SummaryResult
    )
    infographics = await regenerate_infographics(summary_result, feedback)
    return RuntimeWorkflowResponse(
        operation="regenerate_infographics",
        infographics=convert_model(infographics, RuntimeInfographicsPayload),
    )


def _assert_runtime_artifact_store() -> None:
    if not get_settings().gcs_bucket:
        raise ConfigError(
            "GCS_BUCKET is required for Agent Runtime infographics generation because "
            "Cloud Run cannot serve files from the Agent Runtime filesystem."
        )
