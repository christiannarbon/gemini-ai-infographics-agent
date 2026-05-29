from __future__ import annotations

import os
from typing import Any

from agent.actions import (
    generate_infographics,
    regenerate_infographics,
    summarize_url,
)
from agent.runtime_contract import (
    RuntimeInfographicsPayload,
    RuntimeSummaryPayload,
    RuntimeWorkflowResponse,
)


async def dispatch_runtime_operation(
    payload: dict[str, Any],
) -> RuntimeWorkflowResponse:
    """Dispatch one runtime operation without involving an LLM routing step."""
    operation = payload.get("operation")
    if operation == "summarize_url":
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("summarize_url requires a non-empty url")
        return await runtime_summarize_url(url)
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
        summary=RuntimeSummaryPayload.from_result(summary),
    )


async def runtime_generate_infographics(
    summary: dict[str, Any],
) -> RuntimeWorkflowResponse:
    """Generate an infographics artifact from a summary payload."""
    _assert_runtime_artifact_store()
    summary_result = RuntimeSummaryPayload.model_validate(summary).to_result()
    infographics = await generate_infographics(summary_result)
    return RuntimeWorkflowResponse(
        operation="generate_infographics",
        infographics=RuntimeInfographicsPayload.from_result(infographics),
    )


async def runtime_regenerate_infographics(
    summary: dict[str, Any], feedback: str = ""
) -> RuntimeWorkflowResponse:
    """Regenerate an infographics artifact from a summary payload and feedback."""
    _assert_runtime_artifact_store()
    summary_result = RuntimeSummaryPayload.model_validate(summary).to_result()
    infographics = await regenerate_infographics(summary_result, feedback)
    return RuntimeWorkflowResponse(
        operation="regenerate_infographics",
        infographics=RuntimeInfographicsPayload.from_result(infographics),
    )


def _assert_runtime_artifact_store() -> None:
    if not os.getenv("GCS_BUCKET"):
        raise RuntimeError(
            "GCS_BUCKET is required for Agent Runtime infographics generation because "
            "Cloud Run cannot serve files from the Agent Runtime filesystem."
        )
