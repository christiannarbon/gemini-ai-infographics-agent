from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Optional
from uuid import uuid4

from agent.config import get_settings
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
        ProgressStep(label="URL received", status="done", detail=url),
        ProgressStep(label="Fetching article body", status="running"),
        ProgressStep(
            label="Generating 3-line summary and key points", status="pending"
        ),
    ]
    await _emit(progress, on_progress)
    await _mock_step_delay()

    started = time.perf_counter()
    article = await tools.fetch_article(url)
    _log_duration("summarize_url", "fetch_article", started, session_id=session_id)
    progress[1] = ProgressStep(
        label="Article body fetched", status="done", detail=article.title
    )
    progress[2] = ProgressStep(
        label="Generating 3-line summary and key points", status="running"
    )
    await _emit(progress, on_progress)
    await _mock_step_delay()

    started = time.perf_counter()
    summary = await tools.summarize_article(article.title, article.text)
    _log_duration("summarize_url", "summarize_article", started, session_id=session_id)
    text_backend = summary.backend
    progress[2] = ProgressStep(
        label="3-line summary and key points generated",
        status="done",
        detail=text_backend,
    )
    await _emit(progress, on_progress)

    _log_duration("summarize_url", "total", workflow_started, session_id=session_id)
    return SummaryResult(
        session_id=session_id,
        url=url,
        title=article.title,
        summary_lines=summary.summary_lines,
        key_points=summary.key_points,
        article_text=article.text,
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
        ProgressStep(label="Summary confirmation received", status="done"),
        ProgressStep(label="Agent deciding visual style", status="running"),
        ProgressStep(label="Creating infographics layout plan", status="pending"),
        ProgressStep(label="Generating image", status="pending"),
        ProgressStep(label="Saving artifact", status="pending"),
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
        label=f"Agent selected {style_decision.style} style",
        status="done",
        detail=style_decision.reason,
    )
    progress[2] = ProgressStep(
        label="Agent creating infographics layout plan", status="running"
    )
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
        label="Agent created infographics layout plan",
        status="done",
        detail=style_decision.style,
    )
    progress[3] = ProgressStep(label="Generating image", status="running")
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
    image_backend = generated_image.backend
    if generated_image.data:
        svg = ""
        progress[3] = ProgressStep(
            label="Image generated", status="done", detail=image_backend
        )
    else:
        svg = await tools.render_svg(
            summary.title,
            summary.summary_lines,
            summary.key_points,
            visual_plan,
            feedback,
            style=style_decision.style,
        )
        progress[3] = ProgressStep(
            label="Image generation completed with fallback SVG",
            status="done",
            detail=image_backend,
        )
    await _emit(progress, on_progress)
    await _mock_step_delay()

    progress[4] = ProgressStep(label="Saving artifact", status="running")
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
    progress[4] = ProgressStep(
        label="Artifact saved", status="done", detail=artifact_path
    )
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
    snapshot = [
        ProgressStep(label=step.label, status=step.status, detail=step.detail)
        for step in progress
    ]
    result = on_progress(snapshot)
    if result:
        await result


async def _mock_step_delay() -> None:
    if not tools.is_mock_mode():
        return
    delay = get_settings().mock_step_delay
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
