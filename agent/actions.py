from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Optional
from uuid import uuid4

from .models import GraphicResult, ProgressStep, SummaryResult
from . import tools

ProgressCallback = Callable[[list[ProgressStep]], Optional[Awaitable[None]]]
logger = logging.getLogger(__name__)


async def summarize_url(
    url: str, on_progress: Optional[ProgressCallback] = None
) -> SummaryResult:
    workflow_started = time.perf_counter()
    session_id = uuid4().hex
    progress = [
        ProgressStep("URL received", "done", url),
        ProgressStep("Fetching article body", "running"),
        ProgressStep("Generating 3-line summary and key points", "pending"),
    ]
    await _emit(progress, on_progress)
    await _mock_step_delay()

    started = time.perf_counter()
    article = await tools.fetch_article(url)
    _log_duration("summarize_url", "fetch_article", started, session_id=session_id)
    progress[1] = ProgressStep("Article body fetched", "done", article["title"])
    progress[2] = ProgressStep("Generating 3-line summary and key points", "running")
    await _emit(progress, on_progress)
    await _mock_step_delay()

    started = time.perf_counter()
    summary = await tools.summarize_article(article["title"], article["text"])
    _log_duration("summarize_url", "summarize_article", started, session_id=session_id)
    text_backend = summary.get("backend", "unknown")
    progress[2] = ProgressStep(
        "3-line summary and key points generated", "done", text_backend
    )
    await _emit(progress, on_progress)

    _log_duration("summarize_url", "total", workflow_started, session_id=session_id)
    return SummaryResult(
        session_id=session_id,
        url=url,
        title=article["title"],
        summary_lines=summary["summary_lines"],
        key_points=summary["key_points"],
        article_text=article["text"],
        text_backend=text_backend,
        progress=progress,
    )


async def generate_infographics(
    summary: SummaryResult,
    on_progress: Optional[ProgressCallback] = None,
) -> GraphicResult:
    return await _build_infographics(summary, feedback="", on_progress=on_progress)


async def regenerate_infographics(
    summary: SummaryResult,
    feedback: str,
    on_progress: Optional[ProgressCallback] = None,
) -> GraphicResult:
    return await _build_infographics(
        summary, feedback=feedback, on_progress=on_progress
    )


async def _build_infographics(
    summary: SummaryResult,
    feedback: str,
    on_progress: Optional[ProgressCallback] = None,
) -> GraphicResult:
    workflow_started = time.perf_counter()
    progress = [
        ProgressStep("Summary confirmation received", "done"),
        ProgressStep("Agent deciding visual style", "running"),
        ProgressStep("Creating infographics layout plan", "pending"),
        ProgressStep("Generating image", "pending"),
        ProgressStep("Saving artifact", "pending"),
    ]
    await _emit(progress, on_progress)
    await _mock_step_delay()

    started = time.perf_counter()
    style_decision = await tools.decide_style(
        summary.summary_lines, summary.key_points, feedback
    )
    _log_duration(
        "generate_infographic", "decide_style", started, session_id=summary.session_id
    )
    progress[1] = ProgressStep(
        f"Agent selected {style_decision.style} style",
        "done",
        style_decision.reason,
    )
    progress[2] = ProgressStep("Agent creating infographics layout plan", "running")
    await _emit(progress, on_progress)
    await _mock_step_delay()

    started = time.perf_counter()
    visual_plan = await tools.create_visual_plan_for_style(
        summary.summary_lines,
        summary.key_points,
        feedback,
        style=style_decision.style,
    )
    _log_duration(
        "generate_infographic",
        "create_visual_plan",
        started,
        session_id=summary.session_id,
    )
    progress[2] = ProgressStep(
        "Agent created infographics layout plan", "done", style_decision.style
    )
    progress[3] = ProgressStep("Generating image", "running")
    await _emit(progress, on_progress)
    await _mock_step_delay()

    started = time.perf_counter()
    generated_image = await tools.generate_image_artifact(
        visual_plan,
        style=style_decision.style,
        summary_lines=summary.summary_lines,
        key_points=summary.key_points,
    )
    _log_duration(
        "generate_infographic", "generate_image", started, session_id=summary.session_id
    )
    artifact_url = ""
    artifact_mime_type = "image/svg+xml"
    if generated_image.data:
        svg = ""
        image_backend = generated_image.backend
        progress[3] = ProgressStep("Image generated", "done", image_backend)
    else:
        svg = await tools.render_svg(
            summary.title,
            summary.summary_lines,
            summary.key_points,
            visual_plan,
            feedback,
            style=style_decision.style,
        )
        image_backend = generated_image.backend
        progress[3] = ProgressStep(
            "Image generation completed with fallback SVG", "done", image_backend
        )
    await _emit(progress, on_progress)
    await _mock_step_delay()

    progress[4] = ProgressStep("Saving artifact", "running")
    await _emit(progress, on_progress)
    started = time.perf_counter()
    if generated_image.data:
        artifact_path, artifact_url = await tools.save_binary_artifact_with_url(
            summary.session_id,
            generated_image.data,
            generated_image.mime_type,
        )
        artifact_mime_type = generated_image.mime_type
        if not artifact_url:
            artifact_url = tools.artifact_url_for_path(artifact_path)
    else:
        artifact_path, artifact_url = await tools.save_artifact_with_url(
            summary.session_id, svg
        )
        if not artifact_url:
            artifact_url = tools.artifact_url_for_path(artifact_path)
    _log_duration(
        "generate_infographic", "save_artifact", started, session_id=summary.session_id
    )
    progress[4] = ProgressStep("Artifact saved", "done", artifact_path)
    await _emit(progress, on_progress)

    _log_duration(
        "generate_infographic", "total", workflow_started, session_id=summary.session_id
    )
    return GraphicResult(
        session_id=summary.session_id,
        visual_plan=visual_plan,
        svg=svg,
        artifact_path=artifact_path,
        image_backend=image_backend,
        artifact_url=artifact_url,
        artifact_mime_type=artifact_mime_type,
        visual_style=style_decision.style,
        style_reason=style_decision.reason,
        progress=progress,
    )


async def _emit(
    progress: list[ProgressStep], on_progress: Optional[ProgressCallback]
) -> None:
    if not on_progress:
        return
    snapshot = [ProgressStep(step.label, step.status, step.detail) for step in progress]
    result = on_progress(snapshot)
    if result:
        await result


async def _mock_step_delay() -> None:
    if not tools.is_mock_mode():
        return
    delay = float(os.getenv("MOCK_STEP_DELAY", "0.45"))
    if delay > 0:
        await asyncio.sleep(delay)


def _log_duration(operation: str, phase: str, started: float, session_id: str) -> None:
    logger.info(
        "workflow_duration operation=%s phase=%s session_id=%s elapsed_seconds=%.3f",
        operation,
        phase,
        session_id,
        time.perf_counter() - started,
    )
