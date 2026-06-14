from __future__ import annotations

import logging
import re
from typing import Optional

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
    VisualPlan,
)
from agent.tools.svg_renderer import _render_image_svg, _style_image_directive

logger = logging.getLogger(__name__)

_DEFAULT_PLAN_ITEMS = [
    "Place a short article title at the top",
    "Place a 3-line summary prominently on the left",
    "Place key points as nodes with icons on the right",
    "Organize the relationship between the summary and key points with arrows or lines",
]


async def summarize_article(title: str, article_text: str) -> dict[str, list[str]]:
    """Create an English three-line summary and key points from article text.

    Args:
        title: Article title.
        article_text: Cleaned article body text.

    Returns:
        A dictionary containing `summary_lines`, `key_points`, and `backend`.
    """
    if is_mock_mode():
        return {
            "summary_lines": [
                "The Agent proceeds from article retrieval to summarization and image generation as a sequence of workflows.",
                "In ADK, we implement separated tools such as fetch / summarize / plan / render.",
                "Phase 1 verifies the demo experience without external APIs, using mock mode and fallback SVG.",
            ],
            "key_points": [
                "Article retrieval, summarization, composition plan creation, and image generation are handled as a single flow, allowing users to check the results just by entering a URL.",
                "By splitting ADK tools into smaller pieces, we make it easier to track responsibilities like article retrieval, summarization, drawing, and saving.",
                "With mock mode and fallback SVG, you can confirm screen transitions and experience early on, even when external APIs are unavailable.",
                "Generated images are saved as artifacts, which can be expanded later to use Cloud Storage or signed URLs.",
            ],
            "backend": "mock",
        }

    prompt = f"""Summarize the following article in English, and create an article understanding memo to be used for an infographic.

Constraints:
- summary_lines MUST be exactly 3 lines
- summary_lines summarizes the main point and story of the article in 3 lines of natural explanatory text
- key_points must be 4 to 6 items
- key_points should not be a simple paraphrase of summary_lines, but supplementary notes that show how to read the article
- key_points should express background, flow, author's assertions, impressive techniques, concrete examples, and post-reading implications in natural text
- key_points should be about 60 to 120 characters per item, avoiding becoming just classification labels or measure names by being too short
- Do not mechanically attach classification labels like "Technology:", "Solution:", "Metric:" to key_points. Use them naturally only when necessary
- Include proper nouns and numbers only when they are effective for understanding the article or its atmosphere
- Use only the content written in the article, expressing it in a way that retains both the general point and concrete examples
- Output must strictly follow the specified schema
- ALWAYS respond in English regardless of the input language

Title:
{title}

Text:
{article_text[:12000]}
"""
    try:
        from agent import tools

        summary = await tools._generate_structured_content(prompt, ArticleSummary)
    except Exception as exc:
        logger.warning("Gemini summarize failed, falling back to heuristic: %s", exc)
        return _heuristic_summary(title, article_text, reason=str(exc))

    return {
        "summary_lines": summary.summary_lines[:3],
        "key_points": summary.key_points[:6],
        "backend": f"gemini:{text_model_name()}",
    }


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

    prompt = f"""Choose one infographic style that best fits the following summary and key points.

Options:
- business: for enterprises, calm colors, structured diagrams
- pop: for general readers, bright colors, friendly icons
- minimal: limited information, lots of whitespace, quiet presentation style

3-line Summary:
{chr(10).join(summary_lines)}

Key Points:
{chr(10).join(key_points)}

User Feedback:
{feedback or "None"}

Constraints:
- style must be one of business / pop / minimal
- reason must be one English sentence
- Output must strictly follow the specified schema
- ALWAYS respond in English regardless of the input language
"""
    try:
        from agent import tools

        return await tools._generate_structured_content(prompt, StyleDecision)
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

    prompt = f"""Create an infographic composition plan in English.

3-line Summary:
{chr(10).join(summary_lines)}

Key Points:
{chr(10).join(key_points)}

User Feedback:
{feedback or "None"}

Selected Style:
{style}

Constraints:
- plan_items must be 4 to 6 items
- Instructions should clarify placement on the screen, concepts to emphasize, and eye movement guidance
- Use color tones, density, and icon expressions that fit the selected style
- Use the 3-line summary as the overall story of the article, for top headings, central flows, or short explanatory bands
- Read key points as article understanding memos, and summarize them as short labels, sticky notes, speech bubbles, or annotations next to icons in the image
- Do not treat key points as a categorized list of measures, but make a composition that conveys the article's atmosphere, assertions, flow, and concrete examples
- Do not place the 3-line summary and key points side by side as text boxes of the same granularity
- Limit the text displayed in the image to only the contents of the 3-line summary and key points
- Do not include processing steps of the app, generation infrastructure, or explanatory context that is not part of the article content
- Output must strictly follow the specified schema
- ALWAYS respond in English regardless of the input language
"""
    try:
        from agent import tools

        visual_plan = await tools._generate_structured_content(prompt, VisualPlan)
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

    allowed_summary = summary_lines or []
    allowed_points = key_points or []
    prompt = f"""Generate an English infographic image.

Purpose:
- Express as a single easy-to-read infographic by using the article's 3-line summary as the overall story and the key points as diagram materials
- Diagram the article content itself, not an explanation of the application or generation system

Text allowed to be displayed in the image:
3-line Summary (materials for the overall story):
{chr(10).join(f"- {line}" for line in allowed_summary) or "- 3-line Summary"}

Key Points (article understanding memos. Summarize into short display text if necessary):
{chr(10).join(f"- {point}" for point in allowed_points) or "- Key Points"}

Composition Plan (for placement reference only. Do not write the composition plan text in the image):
{chr(10).join(f"- {item}" for item in visual_plan)}

Selected Style:
{style}

Style Directives:
{_style_image_directive(style)}

Expression:
- 16:9 landscape aspect ratio
- White background, easy-to-read thick lines, icons, arrows, sticky note-style memos
- English text should be short, large, and easy to read
- Treat the 3-line summary as a short story band at the top, or as a large central flow
- Use key points as article understanding memos, rephrasing them shortly as sticky notes, speech bubbles, keyword chips, or labels next to icons in the image
- Do not write out all key points as long sentences as they are, but compress them into short expressions conveying the main point, impressive examples, flow, and implications
- According to the selected style, 'business' should have clear structure, 'pop' should be friendly, and 'minimal' should express with whitespace and few elements
- Do not make a composition that just lines up the 3-line summary and key points in text boxes of the same size
- Do not lean too much towards a boxed layout like tables, long text cards, or presentation slides; make a composition where flow, relationships, contrast, and hierarchy are visible
- Do not add words to the image that are not in the article text, such as app processing steps, generation infrastructure, explanatory contexts, or composition plan labels
- Keep headings only to those that indicate article content, such as "3-line Summary" or "Key Points"
- Do not mix colors or decorations that contradict the selected style
- ALWAYS generate text in English regardless of the input language
"""
    try:
        from agent import tools

        image_bytes, mime_type = await tools._generate_image_data(prompt)
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
) -> dict[str, list[str]]:
    sentences = re.split(r"(?<=[。.!?])\s*", article_text)
    compact = [s.strip() for s in sentences if s.strip()]
    summary = compact[:3] or [title]
    while len(summary) < 3:
        summary.append(title)
    key_points = _heuristic_key_points(compact[3:9] or summary)
    return {
        "summary_lines": summary[:3],
        "key_points": key_points[:6],
        "backend": f"heuristic:{reason[:80]}" if reason else "heuristic",
    }


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
