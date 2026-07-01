"""Orchestrates the infographic generation pipeline using mock, heuristic, or Gemini-powered workflows.

Not responsible for: parsing network packets, rendering raw SVGs, or direct GCS uploads.
Depends on: agent.tools.gemini_client, agent.tools.schemas, agent.tools.svg_renderer (and prompts).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from agent.tools import gemini_client
from agent.tools.gemini_client import (
    display_model_name,
    has_gemini_credentials,
    image_model_name,
    is_mock_mode,
    text_model_name,
)
from agent.tools.schemas import (
    ArticleSummary,
    GeneratedImage,
    StyleDecision,
    SummaryToolResult,
    VisualPlan,
)
from agent.tools import prompts
from agent.tools.svg_renderer import _render_image_svg, _style_image_directive

logger = logging.getLogger(__name__)

_DEFAULT_PLAN_ITEMS = [
    "Place a short article title at the top",
    "Place a 3-line summary prominently on the left",
    "Place key points as nodes with icons on the right",
    "Organize the relationship between the summary and key points with arrows or lines",
]


async def summarize_article(title: str, article_text: str) -> SummaryToolResult:
    """Create an English three-line summary and key points from article text.

    Args:
        title: Article title.
        article_text: Cleaned article body text.

    Returns:
        A SummaryToolResult model.
    """
    if is_mock_mode():
        return SummaryToolResult(
            summary_lines=[
                "The Agent proceeds from article retrieval to summarization and image generation as a sequence of workflows.",
                "In ADK, we implement separated tools such as fetch / summarize / plan / render.",
                "Phase 1 verifies the demo experience without external APIs, using mock mode and fallback SVG.",
            ],
            key_points=[
                "Article retrieval, summarization, composition plan creation, and image generation are handled as a single flow, allowing users to check the results just by entering a URL.",
                "By splitting ADK tools into smaller pieces, we make it easier to track responsibilities like article retrieval, summarization, drawing, and saving.",
                "With mock mode and fallback SVG, you can confirm screen transitions and experience early on, even when external APIs are unavailable.",
                "Generated images are saved as artifacts, which can be expanded later to use Cloud Storage or signed URLs.",
            ],
            backend="mock",
        )

    prompt = prompts.build_summary_prompt(title, article_text)
    try:
        summary = await gemini_client._generate_structured_content(
            prompt, ArticleSummary
        )
    except Exception as exc:
        logger.warning("Gemini summarize failed, falling back to heuristic: %s", exc)
        return _heuristic_summary(title, article_text, reason=str(exc))

    return SummaryToolResult(
        summary_lines=summary.summary_lines[:3],
        key_points=summary.key_points[:6],
        backend=f"gemini:{text_model_name()}",
    )


async def decide_style(
    summary_lines: list[str],
    key_points: list[str],
    feedback: str = "",
) -> StyleDecision:
    """Choose the visual style that best fits the article summary.

    Args:
        summary_lines: Three summary lines.
        key_points: Important points extracted from the article.
        feedback: Optional user feedback from regeneration.

    Returns:
        Style decision with a style name and concise reason.
    """
    if is_mock_mode():
        return _heuristic_style_decision(
            summary_lines, key_points, feedback, reason_prefix="mock"
        )

    prompt = prompts.build_style_prompt(summary_lines, key_points, feedback)
    try:
        return await gemini_client._generate_structured_content(prompt, StyleDecision)
    except Exception as exc:
        logger.warning(
            "Gemini style decision failed, falling back to heuristic: %s", exc
        )
        return _heuristic_style_decision(
            summary_lines,
            key_points,
            feedback,
            reason_prefix=f"fallback: {str(exc)[:80]}",
        )


async def create_visual_plan(
    summary_lines: list[str], key_points: list[str], feedback: str = ""
) -> list[str]:
    """Create composition instructions for an infographic image.

    Args:
        summary_lines: Three summary lines to visualize.
        key_points: Important points to include in the composition.
        feedback: Optional user feedback from regeneration.

    Returns:
        A list of English visual composition instructions.
    """
    return await create_visual_plan_for_style(
        summary_lines, key_points, feedback, style="business"
    )


async def create_visual_plan_for_style(
    summary_lines: list[str],
    key_points: list[str],
    feedback: str = "",
    style: str = "business",
) -> list[str]:
    """Create composition instructions for an infographic image using the selected style.

    Args:
        summary_lines: Three summary lines to visualize.
        key_points: Important points to include in the composition.
        feedback: Optional user feedback from regeneration.
        style: Selected visual style. Expected values are `business`, `pop`, or `minimal`.

    Returns:
        A list of English visual composition instructions.
    """
    if is_mock_mode():
        plan = _default_plan_items_for_style(style)
        if feedback.strip():
            plan.append(f"Feedback reflection: {feedback.strip()[:80]}")
        return plan

    prompt = prompts.build_visual_plan_prompt(
        summary_lines, key_points, feedback, style
    )
    try:
        visual_plan = await gemini_client._generate_structured_content(
            prompt, VisualPlan
        )
        return visual_plan.plan_items[:6]
    except Exception as exc:
        logger.warning(
            "Gemini visual plan failed, falling back to default plan: %s", exc
        )
        plan = _default_plan_items_for_style(style)
        if feedback.strip():
            plan.append(f"Feedback reflection: {feedback.strip()[:80]}")
        return plan


async def generate_image(
    visual_plan: list[str],
    summary_lines: Optional[list[str]] = None,
    key_points: Optional[list[str]] = None,
) -> str:
    """Generate an infographic image and return SVG-compatible markup.

    Args:
        visual_plan: Composition instructions for the image model.
        summary_lines: Article summary lines allowed as rendered text.
        key_points: Article key points allowed as rendered text.

    Returns:
        SVG markup wrapping the generated image, or an empty string on fallback.
    """
    image = await generate_image_artifact(
        visual_plan,
        summary_lines=summary_lines,
        key_points=key_points,
    )
    if not image.data:
        return ""
    return _render_image_svg(image.data, image.mime_type)


async def generate_image_artifact(
    visual_plan: list[str],
    style: str = "business",
    summary_lines: Optional[list[str]] = None,
    key_points: Optional[list[str]] = None,
) -> GeneratedImage:
    """Generate an infographic image with Gemini image model for artifact storage.

    Args:
        visual_plan: Composition instructions for the image model.
        style: Selected visual style used to tune the image prompt.
        summary_lines: Article summary lines allowed as rendered text.
        key_points: Article key points allowed as rendered text.

    Returns:
        Generated image bytes and metadata, or an empty payload that signals SVG fallback.
    """
    if is_mock_mode():
        return GeneratedImage(b"", "", "fallback-svg:mock-mode")
    if not has_gemini_credentials():
        message = "credentials are not configured"
        logger.warning("Gemini image generation skipped: %s", message)
        return GeneratedImage(b"", "", f"fallback-svg:{message}")

    prompt = prompts.build_image_prompt(
        style,
        summary_lines,
        key_points,
        visual_plan,
        _style_image_directive(style),
    )
    try:
        image_bytes, mime_type = await gemini_client._generate_image_data(prompt)
    except Exception as exc:
        logger.warning("Gemini image generation failed, falling back to SVG: %s", exc)
        return GeneratedImage(b"", "", f"fallback-svg:{str(exc)[:120]}")

    if not image_bytes:
        message = "no image parts returned"
        logger.warning("Gemini image generation returned %s", message)
        return GeneratedImage(b"", "", f"fallback-svg:{message}")

    return GeneratedImage(
        image_bytes,
        mime_type,
        f"gemini:{display_model_name(image_model_name())}",
    )


def _heuristic_summary(
    title: str, article_text: str, reason: str = ""
) -> SummaryToolResult:
    sentences = re.split(r"(?<=[。.!?])\s*", article_text)
    compact = [s.strip() for s in sentences if s.strip()]
    summary = compact[:3] or [title]
    while len(summary) < 3:
        summary.append(title)
    key_points = _heuristic_key_points(compact[3:9] or summary)
    # Guarantee the 4-6 key-point contract (mirrors ArticleSummary) even for
    # short articles where the sentence pool is thin.
    backfill = _heuristic_key_points(summary) or [f"{title.strip()}."]
    while len(key_points) < 4:
        key_points.append(backfill[len(key_points) % len(backfill)])
    return SummaryToolResult(
        summary_lines=summary[:3],
        key_points=key_points[:6],
        backend=f"heuristic:{reason[:80]}" if reason else "heuristic",
    )


def _heuristic_key_points(sentences: list[str]) -> list[str]:
    points: list[str] = []
    for sentence in sentences[:6]:
        cleaned = sentence.strip().rstrip("。.!?")
        if not cleaned:
            continue
        if len(cleaned) > 110:
            cleaned = f"{cleaned[:109]}..."
        points.append(f"{cleaned}.")
    return points


def _heuristic_style_decision(
    summary_lines: list[str],
    key_points: list[str],
    feedback: str = "",
    reason_prefix: str = "heuristic",
) -> StyleDecision:
    text = " ".join(summary_lines + key_points + [feedback]).lower()
    if any(word in text for word in ["pop", "friendly", "general", "reader", "career"]):
        return StyleDecision(
            style="pop",
            reason=f"{reason_prefix}: Friendly expression for general readers fits well.",
        )
    if any(word in text for word in ["minimal", "simple", "whitespace", "concise"]):
        return StyleDecision(
            style="minimal",
            reason=f"{reason_prefix}: Quiet presentation with limited information fits well.",
        )
    return StyleDecision(
        style="business",
        reason=f"{reason_prefix}: Diagrams that structure and present the article content fit well.",
    )


def _default_plan_items_for_style(style: str) -> list[str]:
    if style == "pop":
        return [
            "Place the article title brightly at the top",
            "Place the 3-line summary in the center in a large sticky-note style speech bubble",
            "Place key points as colorful nodes on the right",
            "Draw the connection between the summary and key points with friendly arrows",
        ]
    if style == "minimal":
        return [
            "Place the article title and 3-line summary at the top with plenty of whitespace",
            "Organize only the main concepts of the article with thin lines in the center",
            "Place key points on the right with a few simple labels",
            "Do not add supplementary elements; show only the relationship between the summary and key points modestly",
        ]
    return list(_DEFAULT_PLAN_ITEMS)
