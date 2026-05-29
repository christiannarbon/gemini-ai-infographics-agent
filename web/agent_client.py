from __future__ import annotations

import json
import logging
import os
import re
import asyncio
import time
from typing import Optional
from typing import Protocol
from uuid import uuid4

from agent.actions import (
    ProgressCallback,
    generate_infographics,
    regenerate_infographics,
    summarize_url,
)
from agent.adk_agent import run_narration_turn
from agent.models import GraphicResult, SummaryResult
from agent.models import ProgressStep
from agent.runtime_contract import RuntimeSummaryPayload, RuntimeWorkflowResponse

logger = logging.getLogger(__name__)


class AgentClient(Protocol):
    async def summarize_url(
        self,
        url: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> SummaryResult: ...

    async def generate_infographics(
        self,
        summary: SummaryResult,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GraphicResult: ...

    async def regenerate_infographics(
        self,
        summary: SummaryResult,
        feedback: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GraphicResult: ...


class LocalAgentClient:
    async def summarize_url(
        self,
        url: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> SummaryResult:
        return await summarize_url(url, on_progress=on_progress)

    async def generate_infographics(
        self,
        summary: SummaryResult,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GraphicResult:
        return await generate_infographics(summary, on_progress=on_progress)

    async def regenerate_infographics(
        self,
        summary: SummaryResult,
        feedback: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GraphicResult:
        return await regenerate_infographics(summary, feedback, on_progress=on_progress)


class RuntimeAgentClient:
    """Calls the deployed Agent Runtime workflow and validates its JSON contract."""

    def __init__(self) -> None:
        self._remote_agent = None

    async def summarize_url(
        self,
        url: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> SummaryResult:
        await _emit_runtime_status(
            "Sending summarization workflow to Agent Runtime", on_progress
        )
        response = await self._run_runtime_operation(
            {"operation": "summarize_url", "url": url}
        )
        if not response.summary:
            raise RuntimeError("Agent Runtime response did not include summary")
        return response.summary.to_result()

    async def generate_infographics(
        self,
        summary: SummaryResult,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GraphicResult:
        await _emit_runtime_status(
            "Sending infographics generation workflow to Agent Runtime", on_progress
        )
        response = await self._run_runtime_operation(
            {
                "operation": "generate_infographics",
                "summary": RuntimeSummaryPayload.from_result(summary).model_dump(
                    mode="json"
                ),
            }
        )
        if not response.infographics:
            raise RuntimeError("Agent Runtime response did not include infographics")
        return response.infographics.to_result()

    async def regenerate_infographics(
        self,
        summary: SummaryResult,
        feedback: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GraphicResult:
        await _emit_runtime_status(
            "Sending infographics regeneration workflow to Agent Runtime", on_progress
        )
        response = await self._run_runtime_operation(
            {
                "operation": "regenerate_infographics",
                "summary": RuntimeSummaryPayload.from_result(summary).model_dump(
                    mode="json"
                ),
                "feedback": feedback,
            }
        )
        if not response.infographics:
            raise RuntimeError("Agent Runtime response did not include infographics")
        return response.infographics.to_result()

    async def _run_runtime_operation(self, payload: dict) -> RuntimeWorkflowResponse:
        remote_agent = self._get_remote_agent()
        return await asyncio.to_thread(
            self._run_runtime_operation_sync, remote_agent, payload
        )

    def _run_runtime_operation_sync(
        self, remote_agent, payload: dict
    ) -> RuntimeWorkflowResponse:
        started = time.perf_counter()
        operation = str(payload.get("operation", "unknown"))
        runtime_response = None
        final_text = ""
        event_count = 0
        first_event_seconds = None
        event_shapes: list[str] = []
        for event in remote_agent.stream_query(
            user_id=os.getenv("AGENT_RUNTIME_USER_ID", "workshop-user"),
            message=json.dumps(payload, ensure_ascii=False),
        ):
            event_count += 1
            if first_event_seconds is None:
                first_event_seconds = time.perf_counter() - started
            event_payload = _event_to_plain_data(event)
            if len(event_shapes) < 8:
                event_shapes.append(_event_shape(event_payload))
            candidate = _runtime_response_from_event(event_payload)
            if candidate:
                runtime_response = candidate
            final_text = _last_text_from_event(event_payload) or final_text

        elapsed_seconds = time.perf_counter() - started
        logger.info(
            "runtime_call_duration operation=%s event_count=%s first_event_seconds=%.3f elapsed_seconds=%.3f",
            operation,
            event_count,
            first_event_seconds if first_event_seconds is not None else -1,
            elapsed_seconds,
        )
        if runtime_response:
            return _validated_runtime_response(runtime_response)
        if final_text:
            return _validated_runtime_response(_runtime_response_from_text(final_text))
        logger.warning(
            "runtime_no_workflow_response operation=%s event_count=%s event_shapes=%s",
            operation,
            event_count,
            event_shapes,
        )
        raise RuntimeError("Agent Runtime returned no workflow response")

    def _get_remote_agent(self):
        if self._remote_agent is not None:
            return self._remote_agent

        resource_name = os.getenv("AGENT_RUNTIME_RESOURCE_NAME")
        if not resource_name:
            raise RuntimeError(
                "Set AGENT_RUNTIME_RESOURCE_NAME when AGENT_BACKEND=runtime."
            )
        if _looks_like_placeholder(resource_name):
            raise RuntimeError(
                "AGENT_RUNTIME_RESOURCE_NAME still contains a placeholder. "
                "Set it to the exact projects/.../locations/.../reasoningEngines/... value "
                "printed by scripts/deploy-agent-runtime.py."
            )

        import vertexai

        client = vertexai.Client(
            project=os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID"),
            location=os.getenv("AGENT_RUNTIME_LOCATION")
            or _location_from_resource_name(resource_name),
        )
        self._remote_agent = client.agent_engines.get(name=resource_name)
        return self._remote_agent


class AdkAgentClient(LocalAgentClient):
    """Runs an ADK LlmAgent narration turn before the local tool pipeline."""

    async def summarize_url(
        self,
        url: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> SummaryResult:
        prefix = await self._adk_prefix(
            "ADK LlmAgent explaining summarize_url action",
            f"Explain the tool/action that the application will execute next to summarize URL {url}.",
            on_progress,
        )

        async def wrapped(progress: list[ProgressStep]) -> None:
            await _invoke_progress(on_progress, prefix + progress)

        summary = await summarize_url(url, on_progress=wrapped)
        summary.progress = prefix + summary.progress
        summary.text_backend = f"{summary.text_backend} / {prefix[0].detail}"
        return summary

    async def generate_infographics(
        self,
        summary: SummaryResult,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GraphicResult:
        prefix = await self._adk_prefix(
            "ADK LlmAgent explaining generate_infographics action",
            "Explain the steps to generate the infographics composition plan and image artifact from the verified summary.",
            on_progress,
        )

        async def wrapped(progress: list[ProgressStep]) -> None:
            await _invoke_progress(on_progress, prefix + progress)

        infographics = await generate_infographics(summary, on_progress=wrapped)
        infographics.progress = prefix + infographics.progress
        return infographics

    async def regenerate_infographics(
        self,
        summary: SummaryResult,
        feedback: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> GraphicResult:
        prefix = await self._adk_prefix(
            "ADK LlmAgent explaining regenerate_infographics action",
            f"Explain the steps to regenerate the infographics incorporating the user feedback: '{feedback}'.",
            on_progress,
        )

        async def wrapped(progress: list[ProgressStep]) -> None:
            await _invoke_progress(on_progress, prefix + progress)

        infographics = await regenerate_infographics(
            summary, feedback, on_progress=wrapped
        )
        infographics.progress = prefix + infographics.progress
        return infographics

    async def _adk_prefix(
        self,
        label: str,
        prompt: str,
        on_progress: Optional[ProgressCallback],
    ) -> list[ProgressStep]:
        running = [ProgressStep(label, "running")]
        await _invoke_progress(on_progress, running)

        try:
            detail = await run_narration_turn(prompt, session_id=uuid4().hex)
        except Exception as exc:
            detail = f"adk:fallback:{str(exc)[:120]}"

        done = [ProgressStep(label, "done", detail)]
        await _invoke_progress(on_progress, done)
        return done


def build_agent_client() -> AgentClient:
    backend = os.getenv("AGENT_BACKEND", "local").lower()
    if backend == "adk":
        return AdkAgentClient()
    if backend == "runtime":
        return RuntimeAgentClient()
    return LocalAgentClient()


async def _emit_runtime_status(
    label: str,
    on_progress: Optional[ProgressCallback],
) -> None:
    await _invoke_progress(on_progress, [ProgressStep(label, "running")])


async def _invoke_progress(
    on_progress: Optional[ProgressCallback],
    progress: list[ProgressStep],
) -> None:
    if on_progress:
        res = on_progress(progress)
        if res is not None:
            await res


def _location_from_resource_name(resource_name: str) -> str:
    match = re.search(r"/locations/([^/]+)/", resource_name)
    if not match:
        return "us-central1"
    return match.group(1)


def _looks_like_placeholder(value: str) -> bool:
    placeholders = (
        "PROJECT_NUMBER",
        "RESOURCE_ID",
        "SERVICE_AGENT_EMAIL_FROM_EFFECTIVE_IDENTITY",
        "YOUR_PROJECT_ID",
        "CHANGE_ME",
    )
    return any(placeholder in value for placeholder in placeholders)


def _event_to_plain_data(event):
    if isinstance(event, dict):
        return event
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json")
    if hasattr(event, "to_dict"):
        return event.to_dict()
    return {}


def _runtime_response_from_event(event: dict) -> Optional[RuntimeWorkflowResponse]:
    content = event.get("content") or {}
    for part in content.get("parts") or []:
        function_response = (
            part.get("function_response") or part.get("functionResponse") or {}
        )
        response = function_response.get("response")
        if isinstance(response, dict):
            try:
                return RuntimeWorkflowResponse.model_validate(response)
            except Exception:
                continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            try:
                return _runtime_response_from_text(text)
            except Exception:
                continue
    return None


def _validated_runtime_response(
    response: RuntimeWorkflowResponse,
) -> RuntimeWorkflowResponse:
    logger.info(
        "runtime_contract operation=%s has_summary=%s has_infographics=%s error=%s",
        response.operation,
        response.summary is not None,
        response.infographics is not None,
        bool(response.error),
    )
    if response.error:
        raise RuntimeError(response.error)
    return response


def _event_shape(event: dict) -> str:
    content = event.get("content") or {}
    part_shapes = []
    for part in content.get("parts") or []:
        keys = sorted(part.keys())
        if "text" in part and isinstance(part.get("text"), str):
            keys.append(f"text_len={len(part['text'])}")
        if "function_response" in part or "functionResponse" in part:
            function_response = (
                part.get("function_response") or part.get("functionResponse") or {}
            )
            keys.append(f"function={function_response.get('name', '')}")
        part_shapes.append(",".join(keys))
    return f"author={event.get('author', '')} parts={part_shapes}"


def _last_text_from_event(event: dict) -> str:
    content = event.get("content") or {}
    texts = []
    for part in content.get("parts") or []:
        text = part.get("text")
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


def _runtime_response_from_text(text: str) -> RuntimeWorkflowResponse:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = re.sub(r"^json\s*", "", stripped, flags=re.I).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        stripped = stripped[start : end + 1]
    return RuntimeWorkflowResponse.model_validate_json(stripped)
