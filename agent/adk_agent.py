from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import tools
from .runtime_contract import RuntimeWorkflowResponse

try:
    from google.adk.agents import BaseAgent
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events import Event
    from google.genai import types

    _ADK_IMPORT_ERROR: Optional[ImportError] = None
except ImportError as exc:
    BaseAgent = object
    InvocationContext = Any
    Event = None
    types = None
    _ADK_IMPORT_ERROR = exc


INFOGRAPHICS_AGENT_INSTRUCTION = """
You are an infographics agent for a Gemini Enterprise Agent Platform workshop demo.

Use the available tools to complete the workflow:
1. fetch_article retrieves public article text from a URL.
2. summarize_article creates an English three-line summary and key points.
3. create_visual_plan turns the summary into an infographics composition.
4. generate_image attempts Nano Banana Pro image generation and returns SVG-compatible markup when available.
5. render_svg is the readable fallback when image generation is unavailable or low quality.
6. save_artifact stores the generated SVG artifact.

Always keep the user in the loop: produce concise progress-friendly outputs and
fall back to SVG if the image model is unavailable.
"""

ORCHESTRATOR_INSTRUCTION = """
You are an ADK narrator agent for a Gemini Enterprise Agent Platform workshop demo.

Your job is not to perform the whole workflow yourself. Instead, briefly explain
which action/tool phase the application will run next and why:
- summarize_url: fetch_article, then summarize_article.
- generate_infographics: create_visual_plan, then generate_image_artifact, then save artifact.
- regenerate_infographics: apply feedback, then regenerate the visual plan and artifact.

Return one short English sentence. Do not use markdown.
"""


class RuntimeWorkflowAgent(BaseAgent):
    """ADK custom agent that dispatches runtime workflow JSON deterministically."""

    async def _run_async_impl(self, ctx: InvocationContext):
        from . import runtime_workflows

        payload: dict[str, Any] = {}
        try:
            payload = _runtime_payload_from_context(ctx)
            response = await runtime_workflows.dispatch_runtime_operation(payload)
        except Exception as exc:
            response = RuntimeWorkflowResponse(
                operation=_runtime_operation_from_payload(payload),
                error=f"{type(exc).__name__}: {exc}",
            )
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                role="model",
                parts=[types.Part(text=response.model_dump_json())],
            ),
        )


def build_infographics_agent(model: Optional[str] = None) -> Any:
    """Build the tools-enabled Google ADK LlmAgent planned for the next phase.

    This agent is intentionally not connected to the web flow yet. The current
    `AGENT_BACKEND=adk` path uses `build_narrator_agent` to demonstrate ADK
    Runner execution while preserving the deterministic action/tool pipeline.
    The next phase can wire this tools-enabled agent into the workflow once the
    tool docstrings and model behavior are tuned.
    """
    try:
        from google.adk.agents import LlmAgent
    except ImportError as exc:
        raise RuntimeError(
            "google-adk is not installed. Install the optional ADK dependency "
            "before using the ADK agent."
        ) from exc

    return LlmAgent(
        name="infographics_agent",
        model=model or os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash"),
        description="Summarizes blog URLs and creates infographics artifacts.",
        instruction=INFOGRAPHICS_AGENT_INSTRUCTION,
        tools=[
            tools.fetch_article,
            tools.summarize_article,
            tools.create_visual_plan,
            tools.generate_image,
            tools.render_svg,
            tools.save_artifact,
        ],
    )


def build_narrator_agent(model: Optional[str] = None) -> Any:
    """Build a small ADK LlmAgent used by the web app to show ADK execution."""
    try:
        from google.adk.agents import LlmAgent
    except ImportError as exc:
        raise RuntimeError(
            "google-adk is not installed. Install google-adk before using AGENT_BACKEND=adk."
        ) from exc

    return LlmAgent(
        name="infographics_narrator",
        model=model or os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash"),
        description="Explains the next action in the infographics workflow.",
        instruction=ORCHESTRATOR_INSTRUCTION,
    )


def build_runtime_workflow_agent(model: Optional[str] = None) -> Any:
    """Build the deterministic ADK agent deployed to Agent Runtime.

    The `model` argument is accepted for compatibility with earlier deploy
    scripts, but this runtime boundary does not call an LLM.
    """
    if _ADK_IMPORT_ERROR:
        raise RuntimeError(
            "google-adk is not installed. Install google-adk before deploying Agent Runtime."
        ) from _ADK_IMPORT_ERROR

    return RuntimeWorkflowAgent(
        name="infographics_runtime_workflow",
        description="Runs the infographics workflow and returns the JSON contract.",
    )


def _runtime_payload_from_context(ctx: Any) -> dict[str, Any]:
    user_content = getattr(ctx, "user_content", None)
    parts = getattr(user_content, "parts", None) or []
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            text = part.get("text")
        else:
            text = getattr(part, "text", None)
        if text:
            texts.append(text)
    message = "\n".join(texts).strip()
    payload = json.loads(message)
    if not isinstance(payload, dict):
        raise ValueError("Runtime user message must be a JSON object")
    return payload


def _runtime_operation_from_payload(payload: dict[str, Any]) -> str:
    operation = payload.get("operation")
    if operation in {
        "summarize_url",
        "generate_infographics",
        "regenerate_infographics",
    }:
        return str(operation)
    return "unknown"


async def run_narration_turn(
    prompt: str, session_id: str, user_id: str = "demo-user"
) -> str:
    """Run one ADK Runner turn and return a compact backend label for progress UI."""
    if tools.is_mock_mode():
        return "adk:dry-run:mock-mode"
    if not tools.has_gemini_credentials():
        return "adk:dry-run:no-gemini-credentials"

    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    app_name = "infographics_demo"
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    runner = Runner(
        agent=build_narrator_agent(),
        app_name=app_name,
        session_service=session_service,
    )

    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or ""

    model = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash")
    if final_text:
        return f"adk:{model}:{final_text[:80]}"
    return f"adk:{model}"
