from __future__ import annotations

import asyncio
import base64
import gzip
import html
import ipaddress
import logging
import os
import re
import socket
import zlib
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Literal, Optional, Union
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, Field

try:
    import trafilatura
except ImportError:
    trafilatura = None


logger = logging.getLogger(__name__)

DEFAULT_ARTICLE_FETCH_MAX_BYTES = 2_000_000
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_GENAI_CLIENT = None

_DEFAULT_PLAN_ITEMS = [
    "Place a short article title at the top",
    "Place a 3-line summary prominently on the left",
    "Place key points as nodes with icons on the right",
    "Organize the relationship between the summary and key points with arrows or lines",
]


class ArticleSummary(BaseModel):
    summary_lines: list[str] = Field(
        description="Exactly three concise English lines that summarize the article's story.",
        min_length=3,
        max_length=3,
    )
    key_points: list[str] = Field(
        description="Four to six English article-reading notes for infographic material.",
        min_length=4,
        max_length=6,
    )


class VisualPlan(BaseModel):
    plan_items: list[str] = Field(
        description="Four to six English composition instructions for an infographic.",
        min_length=4,
        max_length=6,
    )


class StyleDecision(BaseModel):
    style: Literal["business", "pop", "minimal"] = Field(
        description="Best visual style for this article."
    )
    reason: str = Field(
        description="One concise English sentence explaining the style choice."
    )


@dataclass
class GeneratedImage:
    data: bytes
    mime_type: str
    backend: str
    error: str = ""


def is_mock_mode() -> bool:
    return os.getenv("MOCK_MODE", "true").lower() in {"1", "true", "yes", "on"}


def text_model_name() -> str:
    return os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash")


def image_model_name() -> str:
    return os.getenv("GEMINI_IMAGE_MODEL", "gemini-3-pro-image")


async def fetch_article(url: str) -> dict[str, str]:
    """Fetch a public article URL and return its title plus cleaned article text.

    Args:
        url: Public HTTP or HTTPS article URL to fetch.

    Returns:
        A dictionary with `title` and cleaned `text` keys.
    """
    if is_mock_mode():
        host = urlparse(url).netloc or "example.com"
        title = f"Learning Agent Runtime from {host}'s Article"
        body = (
            "This article introduces how to embed AI Agents into enterprise business applications. "
            "The Agent retrieves information from a URL, and executes summarization, structuring, and artifact generation as a sequence of actions. "
            "Using Google ADK, you can define the Agent's behavior while separating the responsibilities of tools, "
            "and deploy it to Agent Runtime to be called stably from a Web App. "
            "Cloud Run runs the FastAPI Web frontend, and Cloud Storage saves the generated images or SVGs. "
            "In the demo, we first verify the UX and processing order in mock mode without depending on external APIs, "
            "and then replace it with Gemini text model and Nano Banana Pro / Gemini image model."
        )
        return {"title": title, "text": body}

    response = await _fetch_public_url(url)

    title, text = await _extract_article_text(response.text, str(response.url))
    return {"title": title, "text": text[:12000]}


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
        summary = await _generate_structured_content(prompt, ArticleSummary)
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
        return await _generate_structured_content(prompt, StyleDecision)
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
        visual_plan = await _generate_structured_content(prompt, VisualPlan)
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
        image_bytes, mime_type = await _generate_image_data(prompt)
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


async def render_svg(
    title: str,
    summary_lines: list[str],
    key_points: list[str],
    visual_plan: list[str],
    feedback: str = "",
    style: str = "business",
) -> str:
    """Render a deterministic fallback SVG infographic.

    Args:
        title: Article title.
        summary_lines: Three summary lines to render.
        key_points: Important points to render.
        visual_plan: Kept for workflow API symmetry; not rendered in the fallback SVG.
        feedback: Optional user feedback from regeneration.
        style: Selected visual style.

    Returns:
        SVG markup for the generated fallback artifact.
    """
    palette = _style_palette(style, feedback)
    accent = palette["accent"]
    title_node = _title_node(title)
    summary_items = "".join(
        _summary_node(i, line) for i, line in enumerate(summary_lines)
    )
    point_items = "".join(
        _point_node(i, point, accent) for i, point in enumerate(key_points[:6])
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="680" viewBox="0 0 1100 680" role="img" aria-label="Infographic">
  <style>
    .bg {{ fill: #f8fafc; }}
    .panel {{ fill: #ffffff; stroke: #cbd5e1; stroke-width: 2; }}
    .title {{ font: 800 30px sans-serif; fill: #ffffff; }}
    .label {{ font: 700 16px sans-serif; fill: #475569; }}
    .summary {{ font: 600 18px sans-serif; fill: #0f172a; }}
    .small {{ font: 500 14px sans-serif; fill: #334155; }}
    .arrow {{ stroke: #64748b; stroke-width: 3; fill: none; marker-end: url(#arrow); }}
  </style>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="#64748b" />
    </marker>
  </defs>
  <rect width="1100" height="680" rx="0" fill="{palette["background"]}" />
  <rect x="40" y="36" width="1020" height="92" rx="8" fill="{accent}" />
  {title_node}

  <rect class="panel" x="54" y="150" width="640" height="410" rx="8" />
  <text x="78" y="180" class="label">3-line Summary</text>
  {summary_items}

  <rect class="panel" x="732" y="150" width="314" height="410" rx="8" />
  <text x="758" y="184" class="label">Key Points</text>
  {point_items}
</svg>"""


async def save_artifact(session_id: str, svg: str) -> str:
    """Save a generated SVG artifact locally and optionally mirror it to Cloud Storage.

    Args:
        session_id: Stable session identifier used as the artifact filename.
        svg: SVG markup to save.

    Returns:
        Local artifact path.
    """
    path, _signed_url = await save_artifact_with_url(session_id, svg)
    return path


async def save_artifact_with_url(session_id: str, svg: str) -> tuple[str, str]:
    """Save a generated SVG artifact and return a browser URL when available."""
    artifact_dir = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{session_id}.svg"
    path.write_text(svg, encoding="utf-8")
    signed_url = await _upload_artifact_to_gcs(path, "image/svg+xml")
    return str(path), signed_url


async def save_binary_artifact(session_id: str, data: bytes, mime_type: str) -> str:
    """Save a generated binary artifact locally and optionally mirror it to Cloud Storage.

    Args:
        session_id: Stable session identifier used as the artifact filename.
        data: Binary artifact bytes.
        mime_type: MIME type for file extension and Cloud Storage metadata.

    Returns:
        Local artifact path.
    """
    path, _signed_url = await save_binary_artifact_with_url(session_id, data, mime_type)
    return path


async def save_binary_artifact_with_url(
    session_id: str,
    data: bytes,
    mime_type: str,
) -> tuple[str, str]:
    """Save a generated binary artifact and return a browser URL when available."""
    artifact_dir = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{session_id}{_extension_for_mime_type(mime_type)}"
    path.write_bytes(data)
    signed_url = await _upload_artifact_to_gcs(path, mime_type)
    return str(path), signed_url


def artifact_url_for_path(artifact_path: str) -> str:
    return f"/artifacts/{Path(artifact_path).name}"


async def _upload_artifact_to_gcs(path: Path, content_type: str) -> str:
    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        return ""

    def upload() -> str:
        from google.cloud import storage

        prefix = os.getenv("GCS_ARTIFACT_PREFIX", "artifacts").strip("/")
        object_name = f"{prefix}/{path.name}" if prefix else path.name
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(object_name)
        blob.upload_from_filename(str(path), content_type=content_type)
        return _generate_signed_artifact_url(blob)

    try:
        return await asyncio.to_thread(upload)
    except Exception as exc:
        logger.warning("Cloud Storage artifact upload failed: %s", exc)
        return ""


def _generate_signed_artifact_url(blob) -> str:
    ttl_seconds = signed_artifact_url_ttl_seconds()
    credentials, service_account_email = _signed_url_credentials()
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=ttl_seconds),
        method="GET",
        credentials=credentials,
        service_account_email=service_account_email,
        access_token=credentials.token,
    )


def signed_artifact_url_ttl_seconds() -> int:
    value = os.getenv("GCS_SIGNED_URL_TTL_SECONDS", "28800")
    try:
        return max(60, int(value))
    except ValueError:
        return 28800


def _signed_url_credentials():
    import google.auth
    from google.auth.transport.requests import Request

    credentials, _project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_request = Request()
    credentials.refresh(auth_request)

    service_account_email = os.getenv("GCS_SIGNING_SERVICE_ACCOUNT") or getattr(
        credentials,
        "service_account_email",
        "",
    )
    if not service_account_email:
        raise RuntimeError(
            "Could not determine the service account email for signed URL generation. "
            "Set GCS_SIGNING_SERVICE_ACCOUNT to the Agent Runtime service account."
        )
    return credentials, service_account_email


async def _fetch_public_url(url: str) -> httpx.Response:
    current_url = url
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "User-Agent": "GeminiEnterpriseAgentWorkshop/1.0",
    }
    async with httpx.AsyncClient(
        follow_redirects=False, timeout=15, headers=headers
    ) as client:
        for _ in range(5):
            await _assert_public_http_url(current_url)
            async with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        break
                    current_url = urljoin(str(response.url), location)
                    continue
                response.raise_for_status()
                raw_content = await _read_limited_response(
                    response, article_fetch_max_bytes()
                )
                content = _decode_response_content(raw_content, response.headers)
                headers = httpx.Headers(response.headers)
                headers.pop("content-encoding", None)
                headers["content-length"] = str(len(content))
                return httpx.Response(
                    response.status_code,
                    headers=headers,
                    content=content,
                    request=response.request,
                    extensions=response.extensions,
                )
    raise ValueError("Too many redirects while fetching article")


async def _read_limited_response(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_raw():
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"Article response exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_response_content(raw_content: bytes, headers: httpx.Headers) -> bytes:
    encoding = headers.get("content-encoding", "").lower().strip()
    if not encoding or encoding == "identity":
        return raw_content

    try:
        if encoding == "gzip":
            return gzip.decompress(raw_content)
        if encoding == "deflate":
            return zlib.decompress(raw_content)
    except (OSError, zlib.error) as exc:
        logger.warning(
            "Ignoring invalid Content-Encoding=%s while fetching article: %s",
            encoding,
            exc,
        )
        return raw_content

    logger.warning(
        "Ignoring unsupported Content-Encoding=%s while fetching article", encoding
    )
    return raw_content


async def _extract_article_text(raw_html: str, url: str) -> tuple[str, str]:
    title = _extract_title(raw_html) or url

    if trafilatura:
        extracted = await asyncio.to_thread(
            trafilatura.extract,
            raw_html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if extracted and extracted.strip():
            return title, _normalize_text(extracted)

    return title, _clean_html(raw_html)


async def _generate_structured_content(prompt: str, schema_model):
    if not has_gemini_credentials():
        raise RuntimeError(
            "GEMINI_API_KEY, GOOGLE_API_KEY, or Vertex AI Gemini environment settings are required"
        )

    async_client = _get_genai_client().aio
    response = await _call_with_retries(
        lambda: async_client.models.generate_content(
            model=text_model_name(),
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema_model,
            },
        ),
        operation="gemini-structured-content",
    )
    if response.parsed is not None:
        return response.parsed
    return schema_model.model_validate_json(response.text)


async def _generate_image_data(prompt: str) -> tuple[bytes, str]:
    from google.genai import types

    async_client = _get_genai_client().aio
    response = await _call_with_retries(
        lambda: async_client.models.generate_content(
            model=image_model_name(),
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
                candidate_count=1,
            ),
        ),
        operation="gemini-image-generation",
    )
    if not response.candidates:
        return b"", "image/png"
    parts = (
        response.candidates[0].content.parts if response.candidates[0].content else []
    )
    for part in parts:
        if part.inline_data and part.inline_data.data:
            data = part.inline_data.data
            if isinstance(data, str):
                data = base64.b64decode(data)
            return data, part.inline_data.mime_type or "image/png"
    return b"", "image/png"


def _get_genai_client():
    global _GENAI_CLIENT
    if _GENAI_CLIENT is None:
        _GENAI_CLIENT = _build_genai_client()
    return _GENAI_CLIENT


def _build_genai_client():
    from google import genai

    return genai.Client()


def close_genai_client() -> None:
    global _GENAI_CLIENT
    if _GENAI_CLIENT is None:
        return
    close = getattr(_GENAI_CLIENT, "close", None)
    if close:
        close()
    _GENAI_CLIENT = None


async def _call_with_retries(operation_factory, operation: str):
    max_attempts = max(1, int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")))
    base_delay = max(0.1, float(os.getenv("GEMINI_RETRY_BASE_DELAY_SECONDS", "0.6")))
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation_factory()
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts or not _is_retryable_exception(exc):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "%s failed with retryable error on attempt %s/%s; retrying in %.1fs: %s",
                operation,
                attempt,
                max_attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"{operation} failed") from last_error


def _is_retryable_exception(exc: Exception) -> bool:
    status_code = _exception_status_code(exc)
    if status_code in RETRYABLE_STATUS_CODES:
        return True
    message = str(exc)
    return any(str(code) in message for code in RETRYABLE_STATUS_CODES)


def _exception_status_code(exc: Exception) -> Optional[int]:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, int):
            return enum_value

    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def has_gemini_credentials() -> bool:
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return True
    return _use_vertex_ai()


def _use_vertex_ai() -> bool:
    return os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def article_fetch_max_bytes() -> int:
    try:
        return max(
            1024,
            int(
                os.getenv(
                    "ARTICLE_FETCH_MAX_BYTES", str(DEFAULT_ARTICLE_FETCH_MAX_BYTES)
                )
            ),
        )
    except ValueError:
        return DEFAULT_ARTICLE_FETCH_MAX_BYTES


def display_model_name(model_name: str) -> str:
    labels = {
        "gemini-2.5-flash-image": "gemini-2.5-flash-image (Nano Banana)",
        "gemini-3-pro-image-preview": "gemini-3-pro-image-preview (Nano Banana Pro)",
        "gemini-3-pro-image": "gemini-3-pro-image (Nano Banana Pro)",
    }
    return labels.get(model_name, model_name)


async def _assert_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL host is required")

    host = parsed.hostname
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    if literal_ip:
        _reject_private_address(literal_ip)
        return

    addresses = await _resolve_host(host)
    if not addresses:
        raise ValueError("URL host could not be resolved")

    for address in addresses:
        _reject_private_address(ipaddress.ip_address(address))


async def _resolve_host(host: str) -> set[str]:
    def resolve() -> set[str]:
        return {
            result[4][0]
            for result in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        }

    return await asyncio.to_thread(resolve)


def _reject_private_address(
    address: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
) -> None:
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError(
            "Private, local, or reserved network addresses are not allowed"
        )


def _clean_html(raw_html: str) -> str:
    without_scripts = re.sub(
        r"<(script|style).*?</\1>", " ", raw_html, flags=re.I | re.S
    )
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    unescaped = html.unescape(without_tags)
    return _normalize_text(unescaped)


def _extract_title(raw_html: str) -> Optional[str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.I | re.S)
    return _clean_html(title_match.group(1)) if title_match else None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


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


def _style_palette(style: str, feedback: str = "") -> dict[str, str]:
    if feedback.strip():
        return {"accent": "#0f766e", "soft": "#ccfbf1", "background": "#f8fafc"}
    if style == "pop":
        return {"accent": "#ea580c", "soft": "#ffedd5", "background": "#fff7ed"}
    if style == "minimal":
        return {"accent": "#475569", "soft": "#e2e8f0", "background": "#f8fafc"}
    return {"accent": "#2563eb", "soft": "#dbeafe", "background": "#f8fafc"}


def _style_image_directive(style: str) -> str:
    directives = {
        "business": "Colors: Calm blue/gray. Lines: Thin and orderly. Icons: Corporate presentation style. Whitespace: Standard.",
        "pop": "Colors: Vivid yellow, orange, turquoise. Lines: Thick hand-drawn style. Icons: Round and friendly. Expression: Bright and active.",
        "minimal": "Colors: Monotone + 1 accent color. Lines: Thin and sharp. Whitespace: Plenty. Element count: Kept low. Atmosphere: Quiet.",
    }
    return directives.get(style, directives["business"])


def _render_image_svg(image_bytes: bytes, mime_type: str = "image/png") -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="680" viewBox="0 0 1100 680" role="img" aria-label="Infographic">
  <rect width="1100" height="680" fill="#ffffff" />
  <image href="data:{html.escape(mime_type)};base64,{encoded}" x="0" y="0" width="1100" height="680" preserveAspectRatio="xMidYMid meet" />
</svg>"""


def _extension_for_mime_type(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type, ".bin")


def _title_node(title: str) -> str:
    tspans = _svg_tspans(
        title, x=72, first_y=76, max_chars=34, max_lines=2, line_gap=34
    )
    return f'<text class="title">{tspans}</text>'


def _summary_node(index: int, line: str) -> str:
    y = 224 + index * 108
    text = f"{index + 1}. {line}"
    tspans = _svg_tspans(text, x=78, first_y=y, max_chars=29, max_lines=3, line_gap=22)
    return f'<text class="summary">{tspans}</text>'


def _point_node(index: int, point: str, accent: str) -> str:
    y = 220 + index * 56
    tspans = _svg_tspans(
        point, x=808, first_y=y - 14, max_chars=13, max_lines=2, line_gap=16
    )
    return f"""
  <circle cx="774" cy="{y}" r="18" fill="{accent}" opacity="0.9" />
  <text x="768" y="{y + 6}" font-family="sans-serif" font-size="17" font-weight="800" fill="#ffffff">{index + 1}</text>
  <text class="small">{tspans}</text>"""


def _svg_tspans(
    text: str, x: int, first_y: int, max_chars: int, max_lines: int, line_gap: int
) -> str:
    lines = _wrap_svg_text(text, max_chars=max_chars, max_lines=max_lines)
    return "".join(
        f'<tspan x="{x}" y="{first_y + i * line_gap}">{html.escape(line)}</tspan>'
        for i, line in enumerate(lines)
    )


def _wrap_svg_text(text: str, max_chars: int, max_lines: int) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return [""]

    lines: list[str] = []
    remaining = compact
    while remaining and len(lines) < max_lines:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            remaining = ""
            break
        split_at = remaining.rfind(" ", 0, max_chars + 1)
        if split_at < max_chars // 2:
            split_at = max_chars
        lines.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining and lines:
        lines[-1] = lines[-1].rstrip("。,.、") + "..."
    return lines
